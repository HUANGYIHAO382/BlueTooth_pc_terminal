# -*- coding: utf-8 -*-
"""
心率手环 BLE 客户端（独立模块，与血压计代码完全解耦）。

核心原则（来自 HeartRateMonitor-1.3.8 可用实现 + v3_0613/docs/心率获取问题分析.md）：

  1. 「裸连接」：BleakClient(address) — 不加任何额外参数
     - 不加 services=[...]  →  加了会导致 Could not get GATT services: Unreachable
     - 不加 winrt={"use_cached_services": False}  →  同上，在很多手环上反而触发失败
     - 不加 pair=...  →  心率手环通常不需要配对
  2. 「连后查服务」：connect() 成功后再读 client.services 里有没有 0x180D
     - 绝大多数手环不会在广播包里声明 0x180D，必须连上才能看到
     - 连接前用广播包预判 = 误把正常设备判成「不支持心率」
  3. 服务枚举轮询：bleak 3.x 在 connect() 内已完成服务枚举，旧版可能抛出
     "Service Discovery has not been performed yet"，兼容两种情况

使用方式（初学者向）：
    client = HRBleClient("F8:3D:7E:09:BD:BB")
    client.on_heart_rate = lambda bpm: print(f"心率: {bpm} BPM")
    client.on_log        = lambda msg: print(msg)

    success, msg = await client.connect()
    if success:
        # 设备会持续推送心率，回调会被反复调用
        await asyncio.sleep(60)
    await client.disconnect()
"""

from __future__ import annotations

import asyncio
from typing import Callable, Optional

from bleak import BleakClient
from bleak.exc import BleakError

from hr_ble import (
    HEART_RATE_MEASUREMENT_UUID,
    HEART_RATE_SERVICE_UUID,
    parse_heart_rate_measurement,
)


def format_hr_error(exc: BaseException) -> str:
    """
    将 BLE 连接异常翻译成友好的中文提示。

    Python 3.11+ 的 TimeoutError.__str__() 返回空字符串，直接 str(e) 会让界面显示空白；
    必须单独捕获并给出有意义的说明。
    """
    name = type(exc).__name__
    detail = str(exc).strip()

    # TimeoutError / asyncio.TimeoutError 的 str() 为空，特殊处理
    if isinstance(exc, TimeoutError):
        return (
            "连接超时。常见原因：\n"
            "  1. 手环被手机占用 — 请在手机蓝牙设置里断开该手环，再重试\n"
            "  2. 手环未开启心率测量 — 请在手环上启动心率/运动模式\n"
            "  3. 距离太远或手环已休眠 — 请靠近并唤醒手环"
        )

    # BleakError 通常有描述，直接显示
    if detail:
        low = detail.lower()
        if "unreachable" in low:
            return (
                f"{detail}\n"
                "提示：Unreachable 通常表示手机仍在占用该手环，请先在手机上断开蓝牙连接。"
            )
        if "access" in low or "denied" in low:
            return f"{detail}\n提示：访问被拒绝，可尝试在 Windows 蓝牙设置里先配对该设备。"
        return f"{name}: {detail}"

    return name


async def _check_hr_service(client: BleakClient, max_wait_sec: int = 10) -> bool:
    """
    连接成功后，检查 GATT 服务里是否包含标准心率服务 0x180D。

    bleak 3.x 已在 connect() 内完成服务枚举，通常直接可查；
    旧版 bleak 或特殊情况下可能抛出 "Service Discovery has not been performed yet"，
    此时最多等 max_wait_sec 秒（每秒重试一次），与 1.3.8 的 check_service 逻辑对齐。
    """
    target = HEART_RATE_SERVICE_UUID.lower()

    for rtry in range(max_wait_sec + 1):
        try:
            # 注意：查的是 client.services（连接后的 GATT 服务列表），不是广播包
            return any(str(s.uuid).lower() == target for s in client.services)
        except BleakError as e:
            if "Service Discovery has not been performed yet" in str(e):
                # 服务还没枚举完，等 1 秒再试
                await asyncio.sleep(1)
            else:
                raise

    # 等了 max_wait_sec 秒仍未完成：超时
    raise TimeoutError("GATT 服务枚举超时")


class HRBleClient:
    """
    单台心率手环的 BLE 连接管理（独立封装）。

    设计原则：
    - 与血压计逻辑完全无关，可单独使用
    - 遵循 HeartRateMonitor-1.3.8 的极简裸连接：BleakClient(address) 不加任何额外参数
    - 通过回调函数向外传递心率数据和日志，不依赖 Qt Signal

    属性：
        address (str): 设备 MAC 地址（已规范化大写冒号格式）
        on_heart_rate: 心率回调 Callable[[int], None]，参数为 BPM 整数
        on_log: 日志回调 Callable[[str], None]，参数为日志文本

    示例::

        client = HRBleClient("F8:3D:7E:09:BD:BB")
        client.on_heart_rate = lambda bpm: print(f"心率: {bpm}")
        client.on_log = lambda msg: print(msg)
        ok, msg = await client.connect()
    """

    def __init__(self, address: str) -> None:
        # 规范化 MAC 地址：大写、用冒号分隔
        self.address: str = address.strip().upper().replace("-", ":")

        # 外部注入的回调，GUI 或命令行均可使用
        self.on_heart_rate: Optional[Callable[[int], None]] = None
        self.on_log: Optional[Callable[[str], None]] = None

        # 底层 BleakClient（连接后才不为 None）
        self._client: Optional[BleakClient] = None

    # ------------------------------------------------------------------ #
    # 公开属性
    # ------------------------------------------------------------------ #

    @property
    def is_connected(self) -> bool:
        """当前是否与设备保持连接。"""
        return self._client is not None and self._client.is_connected

    @property
    def bleak_client(self) -> Optional[BleakClient]:
        """暴露底层 BleakClient，供需要直接访问 GATT 的代码使用。"""
        return self._client

    # ------------------------------------------------------------------ #
    # 连接与断开
    # ------------------------------------------------------------------ #

    async def connect(self) -> tuple[bool, str]:
        """
        连接手环并订阅心率通知（0x2A37）。

        遵循「裸连接」原则：BleakClient(address) 不加任何额外参数。
        连接成功后立即查 client.services，有 0x180D 才算支持心率。

        Returns:
            (True, 成功提示) 或 (False, 失败原因)。
            注意：TimeoutError / BleakError 等异常不在此拦截，由调用方决定如何处理。
        """
        self._log(f"开始连接（裸连接，对齐 HeartRateMonitor-1.3.8）…")

        # 关键：只传地址字符串，不加 services/winrt/pair 等任何额外参数
        self._client = BleakClient(self.address)

        self._log("调用 BleakClient.connect()…")
        await self._client.connect()
        self._log("connect() 返回，检查 GATT 服务…")

        # 列出所有枚举到的服务，方便调试
        self._log_services()

        # 连接后才能看到完整 GATT 服务列表
        has_hr = await _check_hr_service(self._client)
        if not has_hr:
            svc_list = [str(s.uuid) for s in self._client.services]
            await self._safe_disconnect()
            return False, (
                f"{self.address} 已连接但未发现标准心率服务（0x180D）。\n"
                f"实际服务: {svc_list}\n"
                "该设备可能使用厂商私有协议（如华为手环需要官方 App），"
                "或需要在 Windows 蓝牙设置里配对后才能访问心率。"
            )

        # 订阅 0x2A37，设备会持续推送心率数据包
        await self._client.start_notify(
            HEART_RATE_MEASUREMENT_UUID,
            self._notify_handler,
        )
        self._log(f"已订阅心率特征 0x2A37，等待设备推送数据…")
        return True, f"已连接心率手环 {self.address}"

    async def disconnect(self) -> None:
        """断开 BLE 连接并停止通知。"""
        if self._client and self._client.is_connected:
            try:
                await self._client.stop_notify(HEART_RATE_MEASUREMENT_UUID)
            except Exception:  # noqa: BLE001
                pass
            await self._client.disconnect()
            self._log("BLE 连接已断开。")
        self._client = None

    # ------------------------------------------------------------------ #
    # 内部辅助
    # ------------------------------------------------------------------ #

    async def _safe_disconnect(self) -> None:
        """连接后发现不支持心率时，安静地断开。"""
        try:
            if self._client and self._client.is_connected:
                await self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        self._client = None

    def _notify_handler(self, _sender: int, data: bytearray) -> None:
        """
        BLE 心率通知回调（bleak 收到 0x2A37 数据包时触发）。

        数据格式（蓝牙 SIG Heart Rate Measurement，0x2A37）：
          Byte 0：Flags 标志位
            - bit0 = 0 → 心率值为 UINT8（data[1]）
            - bit0 = 1 → 心率值为 UINT16 小端（data[1:3]）
          Byte 1(+2)：心率 BPM
        """
        try:
            bpm = parse_heart_rate_measurement(bytes(data))
        except (IndexError, ValueError) as e:
            self._log(f"心率数据解析失败: {e}，原始: {bytes(data).hex()}")
            return

        # 注意：逐拍数据不再在此打「原始 hex」日志（太底层、太刷屏）。
        # 干净的展示文本由上层（界面/日志/TV）通过 on_heart_rate 结构化数据统一格式化。
        if self.on_heart_rate:
            self.on_heart_rate(bpm)

    def _log(self, msg: str) -> None:
        """向外部日志回调输出带前缀的日志，若未设置则静默。"""
        if self.on_log:
            self.on_log(f"[{self.address}|HR] {msg}")

    def _log_services(self) -> None:
        """列出当前已枚举的所有 GATT 服务 UUID，用于调试。"""
        try:
            svcs = list(self._client.services) if self._client else []
            if not svcs:
                self._log("[诊断] 服务列表为空（可能尚未枚举完毕）。")
                return
            lines = []
            for s in svcs:
                chars = [str(c.uuid) for c in s.characteristics]
                lines.append(f"  服务 {s.uuid}: {chars}")
            self._log(f"[诊断] 共 {len(svcs)} 个 GATT 服务:\n" + "\n".join(lines))
        except Exception as e:  # noqa: BLE001
            self._log(f"[诊断] 读取服务列表异常: {e!r}")
