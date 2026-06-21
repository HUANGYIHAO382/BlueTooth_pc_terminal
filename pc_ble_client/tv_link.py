# -*- coding: utf-8 -*-
"""
TV 联动：基于 asyncio UDP 的 JSON 协议收发（与 qasync 同一事件循环）。

为什么用 UDP：
- TV 与 PC 同处一个局域网，UDP 简单、无需建连，支持广播一对多。
- 与 qasync 合并的 asyncio 循环里用 ``loop.create_datagram_endpoint`` 收发，
  不另起线程，回调天然在 UI 线程，可安全更新界面。

自定义 JSON 协议（本项目自定义，TV 端按此实现即可）：

  PC → TV：
    {"type": "READY",  "device": "bp",  "mac": "...", "name": "...", "ts": 169...}
    {"type": "RESULT", "device": "bp",  "mac": "...", "data": {"sys":120,"dia":80,"pulse":72}, "ts": ...}
    {"type": "HR",     "device": "band","mac": "...", "bpm": 72, "ts": ...}
    {"type": "PING",   "ts": ...}                 # 测试连接

  TV → PC：
    {"type": "START",  "device": "bp"}            # 触发测量（联动模式下解除阻塞）
    {"type": "PONG",   "ts": ...}                 # 回应 PING

默认端口 18500；支持广播(255.255.255.255)与单播(指定 IP)。
"""

from __future__ import annotations

import asyncio
import json
import socket
import time
from typing import Awaitable, Callable, Optional

DEFAULT_PORT = 18500
BROADCAST_ADDR = "255.255.255.255"

# 消息类型常量
MSG_READY = "READY"
MSG_RESULT = "RESULT"
MSG_HR = "HR"
MSG_PRESSURE = "PRESSURE"
MSG_PING = "PING"
MSG_PONG = "PONG"
MSG_START = "START"


def now_ts() -> int:
    """当前 Unix 秒（放进消息里便于 TV 端排序/去重）。"""
    return int(time.time())


def _ts_str() -> str:
    """当前时间 HH:MM:SS（与界面实时日志一致的展示用时间戳）。"""
    return time.strftime("%H:%M:%S")


class _UdpProtocol(asyncio.DatagramProtocol):
    """asyncio UDP 协议对象：把收到的数据报转交给 TvLink 处理。"""

    def __init__(self, on_datagram: Callable[[bytes, tuple], None]) -> None:
        self._on_datagram = on_datagram
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport) -> None:  # noqa: D401
        self.transport = transport  # type: ignore[assignment]

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        self._on_datagram(data, addr)

    def error_received(self, exc: Exception) -> None:  # noqa: D401
        # UDP 下偶发的 ICMP 端口不可达等错误，忽略即可，不影响后续收发
        pass


class TvLink:
    """
    TV 联动 UDP 通道。

    用法::

        link = TvLink(on_log=print)
        link.on_message = lambda msg, addr: ...   # 收到 TV→PC 消息
        await link.start(port=18500)
        link.set_target(mode="broadcast")         # 或 mode="unicast", ip="192.168.1.50"
        link.send_ready(device="bp", mac="...", name="...")
        ...
        await link.stop()
    """

    def __init__(self, on_log: Optional[Callable[[str], None]] = None) -> None:
        self._on_log = on_log or (lambda _m: None)
        # 收到 TV→PC 消息的回调：on_message(msg_dict, addr)
        self.on_message: Optional[Callable[[dict, tuple], None]] = None

        self._transport: Optional[asyncio.DatagramTransport] = None
        self._protocol: Optional[_UdpProtocol] = None
        self._port: int = DEFAULT_PORT
        # 发送目标
        self._mode: str = "broadcast"
        self._ip: str = BROADCAST_ADDR
        # 联动模式：等待 START 的 Future（按设备类型区分）
        self._start_waiters: dict[str, asyncio.Future] = {}
        # 纯文本模式：PC→TV 只发「一行处理后的文本」（TV 端直接呈现这条信息流）。
        # 关闭则回退为结构化 JSON（适合需要解析字段的 TV 端）。
        self.text_mode: bool = True

    # ---- 生命周期 ----

    @property
    def is_running(self) -> bool:
        return self._transport is not None

    async def start(self, port: int = DEFAULT_PORT) -> None:
        """绑定本地端口开始收发；重复调用会先停后起。"""
        if self._transport is not None:
            await self.stop()
        self._port = port
        loop = asyncio.get_running_loop()

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError as e:
            sock.close()
            self._on_log(f"[TV] 绑定 UDP 端口 {port} 失败: {e!r}（可能端口被占用）")
            raise

        self._transport, self._protocol = await loop.create_datagram_endpoint(
            lambda: _UdpProtocol(self._handle_datagram),
            sock=sock,
        )
        self._on_log(f"[TV] UDP 已在 0.0.0.0:{port} 启动（广播+单播均可收发）")

    async def stop(self) -> None:
        """关闭 UDP 通道并取消所有等待中的 START。"""
        for fut in list(self._start_waiters.values()):
            if not fut.done():
                fut.cancel()
        self._start_waiters.clear()
        if self._transport is not None:
            self._transport.close()
            self._transport = None
            self._protocol = None
            self._on_log("[TV] UDP 已关闭")

    # ---- 目标配置 ----

    def set_target(self, *, mode: str = "broadcast", ip: str = BROADCAST_ADDR) -> None:
        """设置发送目标：广播或单播 IP。"""
        self._mode = mode
        self._ip = BROADCAST_ADDR if mode == "broadcast" else (ip or BROADCAST_ADDR)

    def _target_addr(self) -> tuple:
        return (self._ip, self._port)

    # ---- 发送 ----

    def _send(self, obj: dict, *, text: str = "") -> None:
        """
        发送一条 PC→TV 消息。

        - text_mode=True ：只发 ``text`` 这一行纯文本（TV 端直接呈现）。
        - text_mode=False：发结构化 JSON（``obj``），适合需要解析字段的 TV 端。
        """
        if self._transport is None:
            self._on_log("[TV] 未启动 UDP，发送被忽略；请先在底部栏配置并启用。")
            return
        try:
            if self.text_mode:
                payload = (text or "").strip()
                if not payload:
                    return
                self._transport.sendto(payload.encode("utf-8"), self._target_addr())
                self._on_log(f"[TV] 已向 {self._ip}:{self._port} 发送：{payload}")
            else:
                data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                self._transport.sendto(data, self._target_addr())
                self._on_log(f"[TV] 已向 {self._ip}:{self._port} 发送 {obj.get('type')} {obj}")
        except OSError as e:
            self._on_log(f"[TV] 发送失败: {e!r}")

    def send_ready(self, *, device: str, mac: str, name: str = "", text: str = "") -> None:
        line = text or f"[{_ts_str()}] {name or device} 就绪，等待开始测量"
        self._send(
            {"type": MSG_READY, "device": device, "mac": mac, "name": name, "ts": now_ts()},
            text=line,
        )

    def send_result(
        self,
        *,
        device: str,
        mac: str,
        sys_: int,
        dia_: int,
        pulse: int,
        text: str = "",
    ) -> None:
        # text 为「处理后」的整行文本（含时间戳），TV 端直接呈现；JSON 模式下另带结构化 data
        self._send(
            {
                "type": MSG_RESULT,
                "device": device,
                "mac": mac,
                "data": {"sys": sys_, "dia": dia_, "pulse": pulse},
                "text": text or f"血压: {sys_}/{dia_} mmHg，脉搏 {pulse} BPM",
                "ts": now_ts(),
            },
            text=text or f"血压: {sys_}/{dia_} mmHg，脉搏 {pulse} BPM",
        )

    def send_pressure(self, *, mac: str, mmhg: int, text: str = "") -> None:
        """测量过程中的实时加压压力（让 TV 同步呈现「正在加压」）。"""
        self._send(
            {
                "type": MSG_PRESSURE,
                "device": "bp",
                "mac": mac,
                "mmhg": mmhg,
                "text": text or f"加压中: {mmhg} mmHg",
                "ts": now_ts(),
            },
            text=text or f"加压中: {mmhg} mmHg",
        )

    def send_hr(self, *, mac: str, bpm: int, text: str = "") -> None:
        self._send(
            {
                "type": MSG_HR,
                "device": "band",
                "mac": mac,
                "bpm": bpm,
                "text": text or f"心率: {bpm} BPM",
                "ts": now_ts(),
            },
            text=text or f"心率: {bpm} BPM",
        )

    def send_ping(self) -> None:
        self._send({"type": MSG_PING, "ts": now_ts()}, text=f"[{_ts_str()}] PING 测试连接")

    # ---- 接收 ----

    def _handle_datagram(self, data: bytes, addr: tuple) -> None:
        raw = ""
        try:
            raw = data.decode("utf-8", errors="replace").strip()
            msg = json.loads(raw)
            if not isinstance(msg, dict):
                msg = {"type": raw}
        except ValueError:
            # 纯文本入站：把整行当作 type 处理（兼容 TV 端也用纯文本回 START/PONG）
            msg = {"type": raw}
        mtype = str(msg.get("type", "")).upper()

        # 只处理 TV→PC 的控制指令（START / PONG）。
        # 其余（含自己发出的 HR/RESULT/READY/PING 回环）一律忽略，避免把自己的推送当成指令。
        if mtype not in (MSG_START, MSG_PONG):
            return

        self._on_log(f"[TV] 收到 TV 端 {mtype} 指令（来自 {addr[0]}:{addr[1]}）：{msg}")

        # START：解除对应设备类型的阻塞等待
        if mtype == MSG_START:
            device = str(msg.get("device", "")) or "bp"
            fut = self._start_waiters.get(device)
            if fut is not None and not fut.done():
                fut.set_result(msg)

        if self.on_message is not None:
            self.on_message(msg, addr)

    # ---- 联动：等待 START ----

    async def wait_for_start(self, device: str = "bp", timeout: Optional[float] = None) -> dict:
        """
        阻塞等待 TV 发来的 START（按设备类型区分）。

        :param device: 设备类型（bp / band）
        :param timeout: 超时秒数；None 表示一直等
        :return: TV 发来的 START 消息字典
        :raises asyncio.TimeoutError: 超时
        """
        loop = asyncio.get_running_loop()
        fut: asyncio.Future = loop.create_future()
        self._start_waiters[device] = fut
        try:
            if timeout is not None:
                return await asyncio.wait_for(fut, timeout=timeout)
            return await fut
        finally:
            # 清理，避免悬挂引用
            if self._start_waiters.get(device) is fut:
                del self._start_waiters[device]
