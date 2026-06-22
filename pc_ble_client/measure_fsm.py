# -*- coding: utf-8 -*-
"""
血压测量状态机（P0）：TV START_MEASURE → ACK → 测量 → PROGRESS/RESULT。

GUI「开始测量」与 TV 遥控共用本状态机，避免两套逻辑分叉。
"""

from __future__ import annotations

import asyncio
import time
from enum import Enum
from typing import Any, Callable, Optional, Tuple

from reading_format import BpPressureReading, BpResultReading, reset_bp_pressure_tracking
from tv_messages import ack, measure_error, measure_progress, measure_result


class MeasureState(Enum):
    IDLE = "idle"
    MEASURING = "measuring"


class MeasureFsm:
    """
    单次血压测量会话的状态机。

    用法::
        fsm = MeasureFsm(backend, tv_link, on_log=...)
        await fsm.handle_start_measure(msg)   # TV 触发
        await fsm.run_local_measure(...)      # GUI 触发
    """

    def __init__(
        self,
        backend: Any,
        tv_link: Any,
        *,
        get_config: Callable[[], Any],
        on_log: Optional[Callable[[str], None]] = None,
        on_state_changed: Optional[Callable[[MeasureState], None]] = None,
    ) -> None:
        self._backend = backend
        self._tv = tv_link
        self._get_config = get_config
        self._on_log = on_log or (lambda _m: None)
        self._on_state = on_state_changed or (lambda _s: None)

        self.state = MeasureState.IDLE
        self.request_id: str = ""
        self.reply_to: Tuple[str, int] = ("", 0)
        self._measuring_lock = asyncio.Lock()

    def _set_state(self, st: MeasureState) -> None:
        self.state = st
        self._on_state(st)

    def _reply_addr(self) -> Tuple[str, int]:
        """优先用 START_MEASURE 里的 reply_to；否则按模拟器/真机默认。"""
        if self.reply_to[0]:
            return self.reply_to
        return self._get_config().default_measure_reply_to()

    def _parse_reply_to(self, msg: dict, addr: tuple) -> Tuple[str, int]:
        """从 TV 消息解析 reply_to；缺字段时用 default_measure_reply_to 补全。"""
        cfg = self._get_config()
        default_ip, default_port = cfg.default_measure_reply_to(addr[0] if addr else "")
        reply = msg.get("reply_to")
        if isinstance(reply, dict):
            return (
                str(reply.get("ip", default_ip)),
                int(reply.get("port", default_port)),
            )
        return default_ip, default_port

    def _send_b(self, msg: dict) -> None:
        """
        P0：按 reply_to 回 TV。

        模拟器 reply_to 为 127.0.0.1:18500（勿 redir 18501，防回环）；
        真机为 TV_IP:18501。
        """
        cfg = self._get_config()
        if cfg.protocol_stage == "P0":
            target = self._reply_addr()
            need_a = target[1] == cfg.port_a
            need_b = target[1] == cfg.port_b
            if need_a and not self._tv.is_running:
                self._on_log("[FSM] 需信道 A(18500) 回包，当前未启动")
                return
            if need_b and not self._tv.is_channel_b_running:
                self._on_log("[FSM] 需信道 B(18501) 回包，当前未启动")
                return
            self._on_log(f"[FSM] 回包 → {target[0]}:{target[1]} type={msg.get('type')}")
            self._tv.send_measure_reply(msg, target)
            return
        # L0/T0 调试：走信道 A
        self._tv.send_json_a(msg)

    async def handle_start_measure(self, msg: dict, addr: tuple, channel: str) -> bool:
        """
        处理 TV 发来的 START_MEASURE（或 T0 下信道 A 的 START_MEASURE）。

        :return: True 表示已接受并开始测量；False 表示忙碌已拒绝
        """
        async with self._measuring_lock:
            if self.state != MeasureState.IDLE:
                rid = str(msg.get("request_id", ""))
                if rid:
                    self._send_b(
                        measure_error(
                            request_id=rid,
                            error_code="BUSY",
                            message="网关正在测量中",
                        )
                    )
                return False

            self.request_id = str(msg.get("request_id", "") or str(int(time.time() * 1000)))
            # 严格遵循 JSON 里的 reply_to（模拟器 v2.4：127.0.0.1:18500）
            self.reply_to = self._parse_reply_to(msg, addr)

            self._set_state(MeasureState.MEASURING)
            self._send_b(ack(request_id=self.request_id))
            self._on_log(
                f"[FSM] 收到 START_MEASURE request_id={self.request_id} "
                f"reply_to={self.reply_to[0]}:{self.reply_to[1]}"
            )

        asyncio.create_task(self._run_measurement(force=False, device_type_9000=False))
        return True

    def abort_if_measuring(self, reason: str) -> None:
        """蓝牙断开等场景：尽快释放 FSM，避免界面一直显示「测量中」。"""
        if self.state != MeasureState.MEASURING:
            return
        self._on_log(f"[FSM] 测量中止: {reason}")
        if self.request_id:
            self._send_b(
                measure_error(
                    request_id=self.request_id,
                    error_code="FAILED",
                    message=reason,
                )
            )
        self._set_state(MeasureState.IDLE)

    async def handle_cancel_measure(self, msg: dict) -> None:
        """处理 CANCEL_MEASURE。"""
        rid = str(msg.get("request_id", ""))
        if self.state != MeasureState.MEASURING:
            return
        if rid and rid != self.request_id:
            return
        self._on_log("[FSM] 收到 CANCEL_MEASURE，停止测量")
        try:
            await self._backend.send_stop()
        except Exception as e:  # noqa: BLE001
            self._on_log(f"[FSM] 停止指令异常: {e!r}")
        self._send_b(
            measure_error(
                request_id=self.request_id or rid,
                error_code="CANCELLED",
                message="用户取消测量",
            )
        )
        self._set_state(MeasureState.IDLE)

    async def run_local_measure(
        self,
        *,
        force: bool,
        device_type_9000: bool,
        wait_tv_start: bool = False,
        tv_timeout: float = 120.0,
    ) -> Tuple[bool, str]:
        """
        GUI「开始测量」入口。

        :param wait_tv_start: TV 联动模式为 True 时先发 READY 并等待 START
        """
        async with self._measuring_lock:
            if self.state != MeasureState.IDLE:
                return False, "已有测量在进行中"

        if wait_tv_start:
            try:
                msg = await self._tv.wait_for_start("bp", timeout=tv_timeout)
                self._on_log(f"[FSM] TV 授权: {msg.get('type')}")
                addr = msg.get("_addr") or ("", 0)
                self.reply_to = self._parse_reply_to(msg, addr)
            except asyncio.TimeoutError:
                return False, "等待 TV START 超时"

        async with self._measuring_lock:
            if self.state != MeasureState.IDLE:
                return False, "已有测量在进行中"
            self.request_id = str(int(time.time() * 1000))
            if not self.reply_to[0]:
                self.reply_to = ("", 0)
            self._set_state(MeasureState.MEASURING)

        try:
            await self._run_measurement(force=force, device_type_9000=device_type_9000)
            return True, "测量流程结束"
        except Exception as e:  # noqa: BLE001
            self._send_b(
                measure_error(
                    request_id=self.request_id,
                    error_code="FAILED",
                    message=str(e),
                )
            )
            self._set_state(MeasureState.IDLE)
            return False, str(e)

    async def _run_measurement(self, *, force: bool, device_type_9000: bool) -> None:
        reset_bp_pressure_tracking()
        try:
            await self._backend.run_full_measurement(
                force,
                device_type_9000,
                on_pressure=None,
            )
        except asyncio.TimeoutError:
            self._send_b(
                measure_error(
                    request_id=self.request_id,
                    error_code="TIMEOUT",
                    message="测量超时",
                )
            )
            raise
        except RuntimeError as e:
            code = "LOW_BATTERY" if "电量" in str(e) else "FAILED"
            self._send_b(
                measure_error(
                    request_id=self.request_id,
                    error_code=code,
                    message=str(e),
                )
            )
            raise
        finally:
            self._set_state(MeasureState.IDLE)

    def on_measurement_result(self, sys_: int, dia_: int, pulse: int) -> None:
        """测量结果帧到达时由 GatewayController 调用。"""
        if self.state != MeasureState.MEASURING:
            return
        result = BpResultReading(sys_, dia_, pulse)
        self._send_b(
            measure_result(
                request_id=self.request_id,
                systolic=result.systolic,
                diastolic=result.diastolic,
                pulse=result.pulse,
            )
        )

    def on_bp_pressure(self, mmhg: int, *, throttle_ms: int = 200) -> Optional[BpPressureReading]:
        """加压回调（带节流）；返回 reading 供 UI 使用。"""
        if self.state != MeasureState.MEASURING:
            return None
        now = time.time() * 1000
        last = getattr(self, "_last_progress_ms", 0.0)
        if now - last < throttle_ms:
            return None
        self._last_progress_ms = now
        reading = BpPressureReading.from_mmhg(mmhg)
        self._send_b(
            measure_progress(
                request_id=self.request_id,
                phase=reading.phase,
                progress=reading.progress,
                pressure_mmhg=reading.mmhg,
            )
        )
        return reading
