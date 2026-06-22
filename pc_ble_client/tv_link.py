# -*- coding: utf-8 -*-
"""
TV 联动：双信道 UDP（A=18500 发现/遥测，B=18501 血压控制闭环）。

与 qasync 同一 asyncio 事件循环，不另起线程。
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import Awaitable, Callable, Optional, Tuple

from gateway_config import GatewayConfig, ProtocolStage

BROADCAST_ADDR = "255.255.255.255"

# TV→PC 控制类 type（大写比较）
_INBOUND_CONTROL = frozenset({
    "START",
    "START_MEASURE",
    "CANCEL_MEASURE",
    "PONG",
})

# Legacy L0 发送用
MSG_READY = "READY"
MSG_RESULT = "RESULT"
MSG_HR = "HR"
MSG_PRESSURE = "PRESSURE"
MSG_PING = "PING"


def now_ts() -> int:
    return int(time.time())


def _ts_str() -> str:
    return time.strftime("%H:%M:%S")


class _UdpProtocol(asyncio.DatagramProtocol):
    def __init__(self, on_datagram: Callable[[bytes, tuple, str], None], channel: str) -> None:
        self._on_datagram = on_datagram
        self._channel = channel
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:  # noqa: D401
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._on_datagram(data, addr, self._channel)

    def error_received(self, exc: Exception) -> None:  # noqa: D401
        pass


class TvLink:
    """
    双信道 TV UDP 通道。

    - 信道 A（port_a）：发现、遥测、T0 阶段也可收 Legacy START
    - 信道 B（port_b）：P0 血压控制闭环（仅 P0 阶段 bind）
    """

    def __init__(
        self,
        on_log: Optional[Callable[[str], None]] = None,
        on_protocol_log: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._on_log = on_log or (lambda _m: None)
        self._on_protocol_log = on_protocol_log or (lambda _m: None)
        self.on_message: Optional[Callable[[dict, tuple, str], None]] = None

        self._transport_a: Optional[asyncio.DatagramTransport] = None
        self._transport_b: Optional[asyncio.DatagramTransport] = None
        self._port_a = 18500
        self._port_b = 18501

        self._config = GatewayConfig()
        self._start_waiters: dict[str, asyncio.Future] = {}

        # 兼容旧代码：text_mode 属性映射到 config
        self.text_mode: bool = True

    @property
    def is_running(self) -> bool:
        return self._transport_a is not None

    @property
    def is_channel_b_running(self) -> bool:
        return self._transport_b is not None

    @property
    def protocol_stage(self) -> ProtocolStage:
        return self._config.protocol_stage

    def apply_config(self, config: GatewayConfig) -> None:
        """应用网关配置（发送目标、阶段、双发开关）。"""
        self._config = config
        self.text_mode = config.text_mode

    async def start(self, config: Optional[GatewayConfig] = None) -> None:
        """启动信道 A；P0 阶段同时启动信道 B。"""
        if config is not None:
            self.apply_config(config)
        await self.stop()
        await self._bind_channel("A", self._config.port_a)
        if self._config.protocol_stage == "P0":
            await self._bind_channel("B", self._config.port_b)

    async def _bind_channel(self, label: str, port: int) -> None:
        loop = asyncio.get_running_loop()
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as e:
            sock.close()
            self._on_log(f"[TV] 绑定信道 {label} 端口 {port} 失败: {e!r}")
            raise
        transport, _ = await loop.create_datagram_endpoint(
            lambda ch=label: _UdpProtocol(self._handle_datagram, ch),
            sock=sock,
        )
        if label == "A":
            self._transport_a = transport
            self._port_a = port
            self._on_log(f"[TV] 信道 A 已在 0.0.0.0:{port} 启动")
        else:
            self._transport_b = transport
            self._port_b = port
            self._on_log(f"[TV] 信道 B 已在 0.0.0.0:{port} 启动")

    async def stop(self) -> None:
        for fut in list(self._start_waiters.values()):
            if not fut.done():
                fut.cancel()
        self._start_waiters.clear()
        if self._transport_a is not None:
            self._transport_a.close()
            self._transport_a = None
        if self._transport_b is not None:
            self._transport_b.close()
            self._transport_b = None
        self._on_log("[TV] UDP 已关闭")

    def set_target(self, *, mode: str = "broadcast", ip: str = BROADCAST_ADDR) -> None:
        """兼容旧接口：更新 config 中的 TV 目标。"""
        self._config.tv_mode = mode
        self._config.tv_ip = ip

    def _unicast_targets(self) -> list[tuple[str, int]]:
        """单播目标列表（A 信道端口）。"""
        targets: list[tuple[str, int]] = []
        u = self._config.effective_unicast_ip()
        if u and u != BROADCAST_ADDR:
            targets.append((u, self._port_a))
        if self._config.tv_mode == "unicast":
            ip = self._config.tv_ip.strip()
            if ip and ip != BROADCAST_ADDR:
                t = (ip, self._port_a)
                if t not in targets:
                    targets.append(t)
        return targets

    def _send_raw(self, payload: bytes, addr: tuple, channel: str, log_hint: str) -> None:
        transport = self._transport_a if channel == "A" else self._transport_b
        if transport is None:
            self._on_log(f"[TV] 信道 {channel} 未启动，发送被忽略")
            return
        try:
            transport.sendto(payload, addr)
            self._on_protocol_log(f"[{channel}→{addr[0]}:{addr[1]}] {log_hint}")
        except OSError as e:
            self._on_log(f"[TV] 发送失败: {e!r}")

    def send_on_channel_a(self, msg: dict, *, text: str = "") -> None:
        """
        经信道 A 发送：按阶段决定 JSON / 文本 / 双发；广播 + 单播加固。
        """
        if self._transport_a is None:
            self._on_log("[TV] 信道 A 未启动，发送被忽略")
            return

        stage = self._config.protocol_stage
        payloads: list[tuple[bytes, str]] = []

        if stage == "L0":
            line = (text or "").strip()
            if line:
                payloads.append((line.encode("utf-8"), line))
        else:
            if self._config.json_mode and msg:
                js = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
                payloads.append((js.encode("utf-8"), js))
            if self._config.text_mode and (text or "").strip():
                line = text.strip()
                payloads.append((line.encode("utf-8"), line))

        if not payloads:
            return

        addrs: list[tuple[str, int]] = []
        if not self._config.no_broadcast:
            addrs.append((BROADCAST_ADDR, self._port_a))
        addrs.extend(self._unicast_targets())
        if not addrs:
            addrs.append((BROADCAST_ADDR, self._port_a))

        for payload, hint in payloads:
            for addr in addrs:
                self._send_raw(payload, addr, "A", hint[:120])

    def send_on_channel_b(self, msg: dict, reply_to: Tuple[str, int]) -> None:
        """P0 真机：经信道 B 单播回复 TV（目标一般为 TV_IP:18501）。"""
        if self._transport_b is None:
            self._on_log("[TV] 信道 B 未启动，B 信道发送被忽略（请切到 P0 阶段）")
            return
        js = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        self._send_raw(js.encode("utf-8"), reply_to, "B", js[:120])

    def send_measure_reply(self, msg: dict, reply_to: Tuple[str, int]) -> None:
        """
        按 START_MEASURE 里的 reply_to 回包（ACK / PROGRESS / RESULT / ERROR）。

        - reply_to.port == 18500：模拟器路径，单播到 127.0.0.1:18500（adb redir 进 TV）
        - reply_to.port == 18501：真机路径，走信道 B
        """
        js = json.dumps(msg, ensure_ascii=False, separators=(",", ":"))
        payload = js.encode("utf-8")
        ip, port = reply_to
        if port == self._port_a:
            if self._transport_a is None:
                self._on_log("[TV] 信道 A 未启动，无法按 reply_to 回包")
                return
            # 模拟器：只单播，不走广播，避免本机回环
            self._send_raw(payload, (ip, port), "A→reply", js[:120])
            return
        if self._transport_b is None:
            self._on_log("[TV] 信道 B 未启动，无法按 reply_to 回包")
            return
        self._send_raw(payload, (ip, port), "B", js[:120])

    # ---- Legacy L0 便捷方法（内部转 send_on_channel_a）----

    def send_ready(self, *, device: str, mac: str, name: str = "", text: str = "") -> None:
        line = text or f"[{_ts_str()}] {name or device} 就绪，等待开始测量"
        if self._config.protocol_stage == "L0":
            self.send_on_channel_a({}, text=line)
        else:
            from tv_messages import script_ready

            self.send_on_channel_a(
                script_ready(
                    script_ip=self._config.effective_script_ip(),
                    listen_port=self._config.listen_port_for_stage(),
                ),
                text=line,
            )

    def send_result(
        self, *, device: str, mac: str, sys_: int, dia_: int, pulse: int, text: str = "",
        request_id: str = "",
    ) -> None:
        from tv_messages import measure_result

        line = text or format_bp_result_legacy(sys_, dia_, pulse)
        if self._config.protocol_stage == "L0":
            obj = {
                "type": MSG_RESULT,
                "device": device,
                "mac": mac,
                "data": {"sys": sys_, "dia": dia_, "pulse": pulse},
                "ts": now_ts(),
            }
            self.send_on_channel_a(obj, text=line)
        else:
            rid = request_id or str(now_ts() * 1000)
            self.send_on_channel_a(
                measure_result(
                    request_id=rid,
                    systolic=sys_,
                    diastolic=dia_,
                    pulse=pulse,
                ),
                text=line,
            )

    def send_pressure(self, *, mac: str, mmhg: int, text: str = "", request_id: str = "",
                      phase: str = "inflating", progress: int = 0) -> None:
        from tv_messages import measure_progress

        line = text or f"加压中: {mmhg} mmHg"
        if self._config.protocol_stage == "L0":
            self.send_on_channel_a(
                {"type": MSG_PRESSURE, "device": "bp", "mac": mac, "mmhg": mmhg, "ts": now_ts()},
                text=line,
            )
        else:
            rid = request_id or "local"
            self.send_on_channel_a(
                measure_progress(
                    request_id=rid,
                    phase=phase,
                    progress=progress,
                    pressure_mmhg=mmhg,
                ),
                text=line,
            )

    def send_hr(self, *, mac: str, bpm: int, text: str = "") -> None:
        from tv_messages import heart_rate_stream

        line = text or f"心率: {bpm} BPM"
        if self._config.protocol_stage == "L0":
            self.send_on_channel_a(
                {"type": MSG_HR, "device": "band", "mac": mac, "bpm": bpm, "ts": now_ts()},
                text=line,
            )
        else:
            self.send_on_channel_a(heart_rate_stream(heart_rate=bpm), text=line)

    def send_ping(self) -> None:
        from tv_messages import ping_json

        line = f"[{_ts_str()}] PING 测试连接"
        if self._config.protocol_stage == "L0":
            self.send_on_channel_a({"type": MSG_PING, "ts": now_ts()}, text=line)
        else:
            self.send_on_channel_a(ping_json(), text=line)

    def send_json_a(self, msg: dict, *, text: str = "") -> None:
        """直接发任意 JSON 到信道 A（SCRIPT_READY 等）。"""
        self.send_on_channel_a(msg, text=text)

    # ---- 接收 ----

    def _handle_datagram(self, data: bytes, addr: tuple, channel: str) -> None:
        raw = ""
        try:
            raw = data.decode("utf-8", errors="replace").strip()
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                msg = {"type": raw}
        except ValueError:
            msg = {"type": raw}

        mtype = str(msg.get("type", "")).upper()
        if not mtype:
            return

        # 忽略自己发出的遥测回环
        if mtype in (
            "SCRIPT_READY", "DEVICE_READY", "DEVICE_OFFLINE", "HEART_RATE_STREAM",
            "MEASURE_PROGRESS", "MEASURE_RESULT", "MEASURE_ERROR", "ACK", "PING",
            MSG_READY, MSG_RESULT, MSG_HR, MSG_PRESSURE,
        ):
            return

        if mtype not in _INBOUND_CONTROL:
            return

        self._on_protocol_log(f"[{channel}←{addr[0]}:{addr[1]}] {raw[:200]}")
        self._on_log(f"[TV] 收到 {mtype}（信道 {channel}，来自 {addr[0]}:{addr[1]}）")

        if mtype in ("START", "START_MEASURE"):
            device = str(msg.get("device", "") or msg.get("target_device", "")).lower() or "bp"
            fut = self._start_waiters.get(device)
            if fut is not None and not fut.done():
                msg["_channel"] = channel
                msg["_addr"] = addr
                fut.set_result(msg)
                return

        if self.on_message is not None:
            self.on_message(msg, addr, channel)

    async def wait_for_start(self, device: str = "bp", timeout: Optional[float] = None) -> dict:
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._start_waiters[device.lower()] = fut
        try:
            if timeout is not None:
                return await asyncio.wait_for(fut, timeout=timeout)
            return await fut
        finally:
            key = device.lower()
            if self._start_waiters.get(key) is fut:
                del self._start_waiters[key]

    def inject_inbound(self, msg: dict, addr: tuple = ("127.0.0.1", 18500), channel: str = "A") -> None:
        """TV 联调 Tab：本地模拟 TV 发来的控制包。"""
        raw = json.dumps(msg, ensure_ascii=False).encode("utf-8")
        self._handle_datagram(raw, addr, channel)


def format_bp_result_legacy(sys_: int, dia_: int, pulse: int) -> str:
    return f"血压: {sys_}/{dia_} mmHg，脉搏 {pulse} BPM"
