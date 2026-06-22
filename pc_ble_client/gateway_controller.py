# -*- coding: utf-8 -*-
"""
网关编排层：BLE 事件 → UI 更新 + TV 推送 + 测量状态机。

把原先散落在 MainWindow 中的 TV/推送逻辑集中到此，主窗口只做面板接线。
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Callable, Optional

from gateway_config import GATEWAY_VERSION, GatewayConfig, GatewayConfigStore
from measure_fsm import MeasureFsm, MeasureState
from reading_format import BpPressureReading, BpResultReading, HrReading, format_bp_pressure
from tv_messages import device_offline, device_ready, script_ready
from tv_link import TvLink


class GatewayController:
    """TV 联动与测量编排（不依赖 Qt，通过回调与主窗口通信）。"""

    def __init__(
        self,
        config_store: GatewayConfigStore,
        tv: TvLink,
        backend: Any,
        *,
        on_run_log: Callable[[str], None],
        on_protocol_log: Callable[[str], None],
        on_status: Callable[[str], None],
    ) -> None:
        self._store = config_store
        self._tv = tv
        self._backend = backend
        self._on_run_log = on_run_log
        self._on_protocol_log = on_protocol_log
        self._on_status = on_status

        self.hr_push_enabled = False
        self.bp_push_enabled = False
        self.linkage_enabled = False

        self._ready_task: Optional[asyncio.Task] = None
        self._device_ready_task: Optional[asyncio.Task] = None
        self._last_hr_ms = 0.0
        self._last_progress_ms = 0.0
        self._bp_device_names: dict[str, str] = {}
        # 当前已连接、需周期刷新 DEVICE_READY 的血压计 MAC 集合
        self._bp_connected: set[str] = set()

        self.fsm = MeasureFsm(
            backend,
            tv,
            get_config=lambda: self._store.config,
            on_log=on_run_log,
        )
        self._tv.on_message = self._on_tv_message

    @property
    def config(self) -> GatewayConfig:
        return self._store.config

    def version_title_suffix(self) -> str:
        return f"阶段 {self.config.protocol_stage} | v{GATEWAY_VERSION}"

    def sync_config_from_ui(self, ui_cfg: dict) -> None:
        """从 GlobalBar 读取的配置写入 gateway.json。"""
        c = self._store.config
        if ui_cfg.get("protocol_stage"):
            c.protocol_stage = ui_cfg["protocol_stage"]  # type: ignore[assignment]
        if ui_cfg.get("mode"):
            c.tv_mode = ui_cfg["mode"]
        if ui_cfg.get("ip"):
            c.tv_ip = ui_cfg["ip"]
        if "unicast_ip" in ui_cfg:
            c.tv_unicast_ip = ui_cfg["unicast_ip"]
        if ui_cfg.get("port_a"):
            c.port_a = int(ui_cfg["port_a"])
        c.text_mode = bool(ui_cfg.get("text_mode", c.text_mode))
        c.json_mode = bool(ui_cfg.get("json_mode", c.json_mode))
        c.no_broadcast = bool(ui_cfg.get("no_broadcast", c.no_broadcast))
        if ui_cfg.get("script_ip") is not None:
            c.script_ip = str(ui_cfg.get("script_ip", ""))
        self._store.save()

    def apply_ui_to_bar(self, bar: Any) -> None:
        """启动时用 gateway.json 回填 GlobalBar（由主窗口调用）。"""
        c = self._store.config
        bar.set_gateway_config(c)

    async def ensure_tv(self) -> bool:
        """按当前配置启动 UDP：P0 时 A(18500)+B(18501) 双 bind。"""
        try:
            c = self._store.config
            if c.normalize_ports_for_stage():
                self._store.save()
                self._on_run_log(
                    f"[TV] 已校正 P0 端口：A={c.port_a} B={c.port_b}"
                )
            await self._tv.start(self._store.config)
            self._start_script_ready_loop()
            if c.protocol_stage == "P0":
                self.send_script_ready()
            self.sync_bp_ready_from_backend()
            return True
        except Exception as e:  # noqa: BLE001
            self._on_run_log(f"[TV] 启动失败: {e!r}")
            return False

    async def stop_tv(self) -> None:
        self._stop_script_ready_loop()
        self._stop_device_ready_loop()
        # 网关关闭时通知 TV 血压计离线（避免角标残留「可测量」）
        if self._bp_connected and self._tv.is_running:
            self._tv.send_json_a(
                device_offline(device="BP", reason="gateway_stopped")
            )
            self._on_protocol_log("[A→] DEVICE_OFFLINE gateway_stopped")
        self._bp_connected.clear()
        await self._tv.stop()

    def _start_script_ready_loop(self) -> None:
        self._stop_script_ready_loop()
        if self._store.config.protocol_stage == "L0":
            return

        async def _loop() -> None:
            while True:
                self.send_script_ready()
                await asyncio.sleep(max(5, self._store.config.script_ready_interval_sec))

        try:
            loop = asyncio.get_running_loop()
            self._ready_task = loop.create_task(_loop())
        except RuntimeError:
            pass

    def _stop_script_ready_loop(self) -> None:
        if self._ready_task is not None:
            self._ready_task.cancel()
            self._ready_task = None

    def _start_device_ready_loop(self) -> None:
        """血压计已连接时，每 device_ready_interval_sec 重发 DEVICE_READY（TV 45s 超时）。"""
        self._stop_device_ready_loop()
        c = self._store.config
        if c.protocol_stage == "L0" or not c.json_mode:
            return
        if not self._bp_connected:
            return

        async def _loop() -> None:
            while True:
                await asyncio.sleep(max(5, c.device_ready_interval_sec))
                if not self._bp_connected or not self._tv.is_running:
                    continue
                for mac in list(self._bp_connected):
                    self._send_device_ready(mac)

        try:
            loop = asyncio.get_running_loop()
            self._device_ready_task = loop.create_task(_loop())
        except RuntimeError:
            pass

    def _stop_device_ready_loop(self) -> None:
        if self._device_ready_task is not None:
            self._device_ready_task.cancel()
            self._device_ready_task = None

    def _send_device_ready(self, mac: str, name: str = "") -> None:
        """向信道 A 发送 DEVICE_READY（血压计可测量）。"""
        c = self._store.config
        if c.protocol_stage == "L0" or not c.json_mode:
            return
        if not self._tv.is_running:
            return
        mac = mac.upper()
        dn = name or self._bp_device_names.get(mac, "BP")
        self._bp_device_names[mac] = dn
        msg = device_ready(device="BP", device_name=dn)
        self._tv.send_json_a(msg)
        self._on_protocol_log(f"[A→] DEVICE_READY {dn}")

    def _send_device_offline(self, mac: str, *, reason: str = "bluetooth_disconnected") -> None:
        """向信道 A 发送 DEVICE_OFFLINE。"""
        c = self._store.config
        if c.protocol_stage == "L0" or not c.json_mode:
            return
        if not self._tv.is_running:
            return
        mac = mac.upper()
        self._tv.send_json_a(device_offline(device="BP", reason=reason))
        self._on_protocol_log(f"[A→] DEVICE_OFFLINE {mac} {reason}")

    def sync_bp_ready_from_backend(self) -> None:
        """
        网关启动或重连 TV 后，与 backend 已连接血压计对齐：
        补发 DEVICE_READY / 清理已断开设备。
        """
        if not hasattr(self._backend, "bp_addresses_connected"):
            return
        connected = {m.upper() for m in self._backend.bp_addresses_connected()}
        for mac in connected - self._bp_connected:
            name = self._bp_device_names.get(mac, "")
            self._bp_connected.add(mac)
            self._send_device_ready(mac, name)
        for mac in list(self._bp_connected - connected):
            self._bp_connected.discard(mac)
            self._send_device_offline(mac)
        if self._bp_connected:
            self._start_device_ready_loop()
        else:
            self._stop_device_ready_loop()

    def send_script_ready(self) -> None:
        """手动或周期发送 SCRIPT_READY。"""
        c = self._store.config
        if c.protocol_stage == "L0":
            return
        msg = script_ready(
            script_ip=c.effective_script_ip(),
            listen_port=c.listen_port_for_stage(),
        )
        self._tv.send_json_a(msg)
        self._on_protocol_log(f"[A→] SCRIPT_READY listen={c.listen_port_for_stage()}")

    def _on_tv_message(self, msg: dict, addr: tuple, channel: str) -> None:
        mtype = str(msg.get("type", "")).upper()
        cfg = self.config

        # P0 产品路径：控制指令必须走信道 B（18501）
        if cfg.protocol_stage == "P0" and channel != "B":
            if mtype in ("START", "START_MEASURE", "CANCEL_MEASURE"):
                self._on_run_log(
                    f"[TV] P0 忽略信道 {channel} 上的 {mtype}（应发往 PC:18501）"
                )
                return

        if mtype == "START":
            # Legacy START 转 START_MEASURE；reply_to 与 TV v2.4 / 真机规则一致
            rip, rport = cfg.default_measure_reply_to(addr[0])
            if cfg.protocol_stage != "P0":
                rip, rport = addr[0], cfg.port_a
            msg = {
                **msg,
                "type": "START_MEASURE",
                "request_id": str(msg.get("request_id") or int(time.time() * 1000)),
                "target_device": "BP",
                "reply_to": {"ip": rip, "port": rport},
            }
            mtype = "START_MEASURE"
        if mtype == "START_MEASURE":
            asyncio.create_task(self.fsm.handle_start_measure(msg, addr, channel))
        elif mtype == "CANCEL_MEASURE":
            asyncio.create_task(self.fsm.handle_cancel_measure(msg))

    def set_bp_device_name(self, mac: str, name: str) -> None:
        self._bp_device_names[mac.upper()] = name

    async def on_bp_connected(self, mac: str, name: str = "") -> None:
        """血压计连接成功 → 立即 DEVICE_READY，并启动 10s 周期刷新。"""
        mac = mac.upper()
        if name:
            self._bp_device_names[mac] = name
        self._bp_connected.add(mac)
        self._send_device_ready(mac, name)
        self._start_device_ready_loop()

    async def on_bp_disconnected(self, mac: str) -> None:
        """蓝牙断开 → 立即 DEVICE_OFFLINE，停止周期刷新。"""
        mac = mac.upper()
        self._bp_connected.discard(mac)
        self._send_device_offline(mac)
        if not self._bp_connected:
            self._stop_device_ready_loop()

    def on_heart_rate(
        self, mac: str, bpm: int
    ) -> tuple[str, HrReading]:
        """
        心率通知：返回 (带时间戳的日志行, HrReading) 供 UI 显示。
        """
        reading = HrReading(bpm)
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {reading.text}"
        self._on_status(reading.text)

        if self.hr_push_enabled and self._tv.is_running:
            c = self._store.config
            now = time.time() * 1000
            if now - self._last_hr_ms >= c.hr_throttle_ms:
                self._last_hr_ms = now
                from tv_messages import heart_rate_stream

                self._tv.send_json_a(
                    heart_rate_stream(heart_rate=bpm),
                    text=line if c.text_mode else "",
                )
        return line, reading

    def on_bp_pressure(self, mmhg: int, mac: str = "") -> Optional[str]:
        """加压过程；返回日志行（节流后）或 None。"""
        c = self._store.config
        ts = datetime.now().strftime("%H:%M:%S")

        if self.fsm.state == MeasureState.MEASURING and c.json_mode:
            reading = self.fsm.on_bp_pressure(mmhg, throttle_ms=c.progress_throttle_ms)
            if reading is None:
                return None
            line = f"[{ts}] {reading.text}"
        else:
            line = f"[{ts}] {format_bp_pressure(mmhg)}"

        push = (self.bp_push_enabled or self.linkage_enabled) and self._tv.is_running
        if push and self.fsm.state != MeasureState.MEASURING:
            # 非 FSM 测压时的加压预览（P0 产品路径不在 A 发 PROGRESS）
            if c.protocol_stage == "L0":
                self._tv.send_pressure(mac=mac, mmhg=mmhg, text=line)
            elif c.protocol_stage == "T0":
                reading = BpPressureReading.from_mmhg(mmhg)
                self._tv.send_pressure(
                    mac=mac,
                    mmhg=mmhg,
                    text=line if c.text_mode else "",
                    request_id="local",
                    phase=reading.phase,
                    progress=reading.progress,
                )
        elif push and self.fsm.state == MeasureState.MEASURING and c.text_mode:
            self._tv.send_on_channel_a({}, text=line)
        return line

    def on_measurement_result(self, mac: str, sys_: int, dia_: int, pulse: int) -> str:
        """测量结果；返回日志行。"""
        result = BpResultReading(sys_, dia_, pulse)
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {result.text}"
        c = self._store.config

        fsm_active = self.fsm.state == MeasureState.MEASURING
        if fsm_active:
            self.fsm.on_measurement_result(sys_, dia_, pulse)

        push = (self.bp_push_enabled or self.linkage_enabled) and self._tv.is_running
        if push and not fsm_active:
            self._tv.send_result(
                device="bp",
                mac=mac,
                sys_=sys_,
                dia_=dia_,
                pulse=pulse,
                text=line if c.text_mode else "",
                request_id=self.fsm.request_id,
            )
        elif push and fsm_active and c.text_mode:
            self._tv.send_on_channel_a({}, text=line)
        return line

    async def run_full_measure(
        self,
        *,
        force: bool,
        device_type_9000: bool,
        active_mac: str,
        device_name: str,
    ) -> tuple[bool, str]:
        """GUI 一键测量（含 TV 联动等待）。"""
        if not await self._ensure_tv_for_measure():
            return False, "TV UDP 未能启动"

        if self.linkage_enabled:
            c = self._store.config
            if c.protocol_stage == "P0":
                self._on_run_log(
                    "P0 联动：等待 TV 在 18501 发 START_MEASURE（无需先发 READY）…"
                )
            else:
                self._tv.send_ready(device="bp", mac=active_mac, name=device_name)
                self._on_run_log("已向 TV 发送 READY，等待 START…")

        return await self.fsm.run_local_measure(
            force=force,
            device_type_9000=device_type_9000,
            wait_tv_start=self.linkage_enabled,
        )

    async def _ensure_tv_for_measure(self) -> bool:
        if self._tv.is_running:
            return True
        if self.bp_push_enabled or self.linkage_enabled or self.hr_push_enabled:
            return await self.ensure_tv()
        return await self.ensure_tv()

    def send_ping(self) -> None:
        self._tv.send_ping()

    def simulate_start(self, *, use_p0: bool = False) -> None:
        """TV 联调 Tab：模拟 TV 发 START / START_MEASURE。"""
        c = self.config
        if use_p0 or c.protocol_stage == "P0":
            reply_ip, reply_port = c.default_measure_reply_to()
            msg = {
                "type": "START_MEASURE",
                "request_id": str(int(time.time() * 1000)),
                "target_device": "BP",
                "reply_to": {"ip": reply_ip, "port": reply_port},
            }
            self._tv.inject_inbound(msg, ("127.0.0.1", c.port_b), "B")
        else:
            self._tv.inject_inbound({"type": "START", "device": "bp"}, channel="A")
