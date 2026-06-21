# -*- coding: utf-8 -*-
"""
多路 BLE 后端（解耦版）：血压计与心率手环完全分开管理。

设计说明（初学者向）：
─────────────────────────────────────────────────────────────
「血压计（BP）」路径
  - 使用私有 FFF0/FFF1/FFF2 透传服务（瑞光 PDF 协议）
  - BleakClient + winrt={"use_cached_services": False}（避免读到旧缓存）
  - 连接后订阅 FFF1 收帧，FFF2 发命令

「心率手环（HR）」路径
  - 使用标准 BLE 心率服务（0x180D / 0x2A37）
  - 完全委托给 hr_ble_backend.HRBleClient（独立模块）
  - 裸连接：BleakClient(address)，不加任何额外参数
  - 连接后查 client.services 有无 0x180D，有才订阅 0x2A37

两条路径互不干扰，HR 的改动不影响 BP，BP 的改动不影响 HR。
─────────────────────────────────────────────────────────────
"""

from __future__ import annotations

import asyncio
import sys
from typing import Dict, List, Optional, Tuple

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError

from bp_protocol import (
    BP_NOTIFY_UUID,
    BP_SERVICE_UUID,
    BP_WRITE_UUID,
    CMD_CONNECT,
    CMD_QUERY_POWER,
    CMD_START,
    CMD_STOP,
    MIN_POWER_MV,
    WRITE_GAP_SEC,
    FrameParser,
    dispatch_ruiguang_frame,
    service_uuid_match,
    sort_rows_bp_name_candidates_first,
)
from hr_ble_backend import HRBleClient, format_hr_error


# ──────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────

def norm_mac(addr: str) -> str:
    """统一 MAC 字符串格式（大写、冒号分隔），用作 sessions 字典的键。"""
    return addr.strip().upper().replace("-", ":")


def _is_winrt_user_cancelled(exc: BaseException) -> bool:
    """判断是否为 WinRT「用户取消」错误（winerror -2147023673）。"""
    if getattr(exc, "winerror", None) == -2147023673:
        return True
    t = str(exc)
    return (
        "2147023673" in t
        or "操作已被用户取消" in t
        or "canceled" in t.lower()
        or "cancelled" in t.lower()
    )


# ──────────────────────────────────────────────────────────────────────
# 血压计专用：BleakClient 构造辅助
# ──────────────────────────────────────────────────────────────────────

def _make_bp_client(
    address_or_device: str | BLEDevice,
    *,
    service_uuids: Optional[list[str]] = None,
    pair: bool = False,
) -> BleakClient:
    """
    构造用于「瑞光血压计」的 BleakClient。

    血压计专用参数说明：
    - ``use_cached_services=False``：强制每次都重新枚举 GATT，
      避免血压计因 Windows 缓存了旧服务而导致写入/订阅失败。
      注意：心率手环不能使用此参数（会触发 Unreachable），故两者必须分开构造。
    - ``pair``：是否在连接时请求系统配对（bleak 3.x 在 __init__ 里传入）。
    - ``services``：只解析 FFF0 子树，减少枚举时间（可选）。
    """
    extra: dict = {"use_cached_services": False} if sys.platform == "win32" else {}
    if service_uuids is not None:
        return BleakClient(address_or_device, services=service_uuids, pair=pair, winrt=extra)
    return BleakClient(address_or_device, pair=pair, winrt=extra)


# ──────────────────────────────────────────────────────────────────────
# 血压会话数据类
# ──────────────────────────────────────────────────────────────────────

class BPSession:
    """
    单台瑞光血压计的运行时状态。

    字段说明：
    - client:     底层 BleakClient，负责 GATT 通信
    - parser:     帧解析器，把 FFF1 数据拼装成完整的瑞光协议帧
    - meas_done:  测量完成事件（等测量结果时使用）
    - last_power: 最近一次收到的电量 mV
    - power_keepalive_task: 定时查电保活任务（可选）
    """

    def __init__(self, address: str, client: BleakClient) -> None:
        self.address = address         # 已规范化 MAC
        self.client = client           # BleakClient
        self.parser = FrameParser()    # 瑞光帧解析器
        self.meas_done: Optional[asyncio.Event] = None
        self.last_power: Optional[int] = None
        self.power_keepalive_task: Optional[asyncio.Task] = None

    def log_prefix(self) -> str:
        return f"[{self.address}|BP]"


# ──────────────────────────────────────────────────────────────────────
# 多路 BLE 后端主类
# ──────────────────────────────────────────────────────────────────────

class MultiBleBackend:
    """
    同时管理多台血压计 + 多台心率手环的 BLE 后端。

    - 血压计：保存在 ``_bp_sessions``（BPSession 对象），用 MAC 作键
    - 心率手环：保存在 ``_hr_clients``（HRBleClient 对象），用 MAC 作键
    - 两条路径完全独立，互不干扰
    """

    def __init__(self, bridge: object) -> None:
        self.bridge = bridge
        # 血压计会话：MAC -> BPSession
        self._bp_sessions: Dict[str, BPSession] = {}
        # 心率手环客户端：MAC -> HRBleClient
        self._hr_clients: Dict[str, HRBleClient] = {}

        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self.last_scan_rounds: int = 1
        self.last_scan_seconds_per_round: float = 0.0
        self.last_scan_note: str = ""

        # 界面「血压指令目标」下拉框同步的 MAC
        self.active_bp_address: Optional[str] = None

    # ── 向下兼容旧接口（GUI 代码部分仍用这些属性）──────────────────

    @property
    def sessions(self) -> Dict[str, object]:
        """
        返回所有已管理连接（BP + HR）的合并视图，供界面调用。

        返回的对象均有 ``.kind`` / ``.address`` / ``.is_connected`` 属性。
        """
        result: Dict[str, object] = {}
        for k, s in self._bp_sessions.items():
            result[k] = _BPSessionView(s)
        for k, c in self._hr_clients.items():
            result[k] = _HRClientView(c)
        return result

    @property
    def client(self) -> Optional[BleakClient]:
        """兼容旧代码：返回当前活动血压计的 BleakClient。"""
        s = self._active_bp_session()
        return s.client if s else None

    # ── 会话查询 ──────────────────────────────────────────────────

    def _active_bp_session(self) -> Optional[BPSession]:
        """查找当前活动血压计会话（先用 active_bp_address，再找第一个已连接的）。"""
        if self.active_bp_address:
            s = self._bp_sessions.get(self.active_bp_address)
            if s and s.client.is_connected:
                return s
        for s in self._bp_sessions.values():
            if s.client.is_connected:
                return s
        return None

    def list_sessions_summary(self) -> List[Tuple[str, str, bool]]:
        """
        返回所有已管理连接的摘要，格式 [(mac, kind_label, is_connected), ...]。
        界面的「已连接设备」列表使用此方法刷新。
        """
        out: List[Tuple[str, str, bool]] = []
        for addr in sorted(self._bp_sessions.keys()):
            s = self._bp_sessions[addr]
            out.append((addr, "BP", bool(s.client.is_connected)))
        for addr in sorted(self._hr_clients.keys()):
            c = self._hr_clients[addr]
            out.append((addr, "HR", bool(c.is_connected)))
        return out

    def bp_addresses_connected(self) -> List[str]:
        """返回当前已连接的血压计 MAC 列表（供界面下拉框填充）。"""
        return [a for a, s in self._bp_sessions.items() if s.client.is_connected]

    # ── 断开 ──────────────────────────────────────────────────────

    async def disconnect_all(self) -> None:
        """断开所有已管理的 BP 和 HR 连接。"""
        for k in list(self._bp_sessions.keys()):
            await self._disconnect_bp(k)
        for k in list(self._hr_clients.keys()):
            await self._disconnect_hr(k)

    async def disconnect_address(self, address: str) -> None:
        """断开指定 MAC 的连接（BP 或 HR 均可）。"""
        k = norm_mac(address)
        if k in self._bp_sessions:
            await self._disconnect_bp(k)
        elif k in self._hr_clients:
            await self._disconnect_hr(k)

    async def _disconnect_bp(self, k: str) -> None:
        """内部：断开并清理血压计会话。"""
        sess = self._bp_sessions.pop(k, None)
        if sess is None:
            return
        await self._await_session_keepalive_cancel(sess)
        try:
            if sess.client.is_connected:
                try:
                    await sess.client.stop_notify(BP_NOTIFY_UUID)
                except Exception:  # noqa: BLE001
                    pass
                await sess.client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        if self.active_bp_address == k:
            self.active_bp_address = None

    async def _disconnect_hr(self, k: str) -> None:
        """内部：断开并清理心率手环客户端。"""
        hr_client = self._hr_clients.pop(k, None)
        if hr_client is None:
            return
        try:
            await hr_client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    # ── 血压计保活 ─────────────────────────────────────────────────

    async def _await_session_keepalive_cancel(self, sess: BPSession) -> None:
        t = sess.power_keepalive_task
        sess.power_keepalive_task = None
        if t is None:
            return
        if not t.done():
            t.cancel()
            try:
                await t
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass

    def stop_session_keepalive_fire_and_forget(self, addr: str) -> None:
        """停止指定血压计的保活任务（不等待结果）。"""
        k = norm_mac(addr)
        sess = self._bp_sessions.get(k)
        if sess is None:
            return
        t = sess.power_keepalive_task
        sess.power_keepalive_task = None
        if t is not None and not t.done():
            t.cancel()

    def start_power_keepalive_for_session(self, addr: str, interval_sec: float) -> None:
        """为指定血压计启动定时查电保活任务（由界面勾选驱动）。"""
        k = norm_mac(addr)
        sess = self._bp_sessions.get(k)
        if sess is None:
            return
        self.stop_session_keepalive_fire_and_forget(k)
        loop = asyncio.get_event_loop()
        sess.power_keepalive_task = loop.create_task(
            self._run_power_keepalive_loop(sess, interval_sec)
        )

    async def _run_power_keepalive_loop(self, sess: BPSession, interval_sec: float) -> None:
        """定期向血压计发送查电量指令（后台任务）。"""
        pref = sess.log_prefix()
        try:
            while True:
                await asyncio.sleep(float(interval_sec))
                if not sess.client.is_connected:
                    break
                if sess.meas_done is not None:
                    continue  # 测量进行中，跳过查电
                try:
                    self.bridge.log_line.emit(f"{pref} [保活] 发送查询电量帧…")
                    await self._write_to_bp_session(sess, CMD_QUERY_POWER)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    self.bridge.log_line.emit(f"{pref} [保活] 失败: {e!r}")
                    break
        except asyncio.CancelledError:
            pass

    # ── 扫描 ───────────────────────────────────────────────────────

    async def _try_find_ble_device(self, address: str, timeout: float = 3.0) -> Optional[BLEDevice]:
        """
        短扫描，尝试找到指定 MAC 对应的 BLEDevice 对象。
        找到后可直接传给 BleakClient，避免 bleak 内部再做一轮扫描。
        仅用于血压计路径（心率手环直接用 MAC 字符串裸连接）。
        """
        want = norm_mac(address)
        try:
            try:
                raw = await BleakScanner.discover(timeout=timeout, return_adv=True)
            except TypeError:
                raw = await BleakScanner.discover(timeout=timeout)
        except Exception as e:  # noqa: BLE001
            self.bridge.log_line.emit(f"连接前短扫失败（将仍按地址直连）: {e!r}")
            return None

        candidates: List[BLEDevice] = []
        if isinstance(raw, dict):
            for tup in raw.values():
                if isinstance(tup, tuple) and len(tup) >= 1 and tup[0] is not None:
                    candidates.append(tup[0])
        else:
            candidates = list(raw)

        for d in candidates:
            if norm_mac(d.address) == want:
                return d
        return None

    async def scan_devices(self, timeout: float, filter_noname: bool) -> List[Tuple[str, str]]:
        """多轮 discover 扫描（return_adv 合并广播名），返回 [(设备名, MAC), ...]。"""

        def _merge(raw: object, by_addr: dict, name_from_adv: dict) -> None:
            if raw is None:
                return
            if isinstance(raw, dict):
                for tup in raw.values():
                    if not isinstance(tup, tuple) or len(tup) < 2:
                        continue
                    dev, adv = tup[0], tup[1]
                    if dev is None:
                        continue
                    a = dev.address
                    by_addr[a] = dev
                    local = getattr(adv, "local_name", None)
                    parts = [(dev.name or "").strip(), (str(local).strip() if local else "")]
                    best = max((p for p in parts if p), key=len, default="")
                    if best:
                        old = name_from_adv.get(a, "")
                        if len(best) >= len(old):
                            name_from_adv[a] = best
                return
            for d in raw:  # type: ignore[union-attr]
                by_addr[d.address] = d

        by_addr: dict = {}
        name_from_adv: dict = {}
        rounds = 2 if timeout >= 6.0 else 1
        per_round = timeout / rounds
        used_return_adv = False

        for _ in range(rounds):
            try:
                batch = await BleakScanner.discover(timeout=per_round, return_adv=True)
                used_return_adv = True
            except TypeError:
                batch = await BleakScanner.discover(timeout=per_round)
            _merge(batch, by_addr, name_from_adv)

        self.last_scan_rounds = rounds
        self.last_scan_seconds_per_round = per_round
        self.last_scan_note = (
            f"{rounds} 轮 discover（return_adv 合并广播名）"
            if used_return_adv
            else f"{rounds} 轮 discover（当前 bleak 不支持 return_adv）"
        )

        rows: List[Tuple[str, str]] = []
        for d in by_addr.values():
            addr = d.address
            name = name_from_adv.get(addr) or (d.name or "").strip()
            if filter_noname and not name:
                continue
            rows.append((name or "(无广播名)", addr))

        rows.sort(key=lambda x: (x[0].lower(), x[1].lower()))
        return sort_rows_bp_name_candidates_first(rows)

    # ══════════════════════════════════════════════════════════════
    # 血压计连接（BP 路径）
    # ══════════════════════════════════════════════════════════════

    async def connect_bp(self, address: str, do_pair: bool) -> None:
        """
        连接瑞光血压计。

        流程：
        1. 短扫描（3s）拿到 BLEDevice 对象（加速连接）
        2. 构造 BleakClient（use_cached_services=False，避免读旧缓存）
        3. connect() 完成后检查 FFF0 服务是否存在
        4. 确认 FFF1（通知）/ FFF2（写入）特征都在
        5. 订阅 FFF1
        """
        k = norm_mac(address)
        if k in self._bp_sessions:
            raise RuntimeError(
                f"该 MAC 已在连接列表中: {k}\n"
                "请先在下栏选中后点「断开该路」，再重新连接。"
            )

        self._async_loop = asyncio.get_running_loop()
        self.bridge.log_line.emit(f"[{k}|BP] 连接前短扫约 3s，尝试解析 BLEDevice…")
        ble_dev = await self._try_find_ble_device(address, timeout=3.0)
        if ble_dev is not None:
            self.bridge.log_line.emit(f"[{k}|BP] 短扫命中，使用 BLEDevice 发起连接。")
        else:
            self.bridge.log_line.emit(f"[{k}|BP] 短扫未命中，按地址字符串连接。")

        c = _make_bp_client(
            ble_dev if ble_dev is not None else k,
            service_uuids=[BP_SERVICE_UUID],
            pair=do_pair,
        )

        # 连接（血压计允许使用 use_cached_services=False，不影响心率手环路径）
        try:
            await c.connect()
        except asyncio.TimeoutError:
            raise RuntimeError(
                f"[{k}|BP] 连接超时（30s）。\n"
                "请确认设备已开机且未被其他程序占用，然后重试。"
            )

        self.bridge.status.emit(f"GATT 已连接 (BP {k})")
        await asyncio.sleep(0.35)

        # 验证 FFF0 服务
        bp_svc = next(
            (s for s in c.services if service_uuid_match(str(s.uuid), BP_SERVICE_UUID)),
            None,
        )
        if bp_svc is None:
            await c.disconnect()
            raise RuntimeError(
                f"[{k}|BP] 未找到瑞光透传服务（FFF0）。\n"
                "若为心率手环，请把界面「连接角色」改为「心率手环」；"
                "若确为瑞光血压计，请核对型号是否与本协议 PDF 一致。"
            )

        # 验证 FFF1（通知）/ FFF2（写入）特征
        ch_notify = bp_svc.get_characteristic(BP_NOTIFY_UUID)
        ch_write = bp_svc.get_characteristic(BP_WRITE_UUID)
        if ch_notify is None or ch_write is None:
            listed = [str(ch.uuid) for ch in bp_svc.characteristics]
            await c.disconnect()
            raise RuntimeError(
                f"[{k}|BP] 已找到 FFF0，但缺少 FFF1/FFF2（当前服务下特征: {listed}）。\n"
                "手环类设备请使用「心率手环」连接；血压计请断开后重试。"
            )

        # 建立会话并绑定通知回调
        sess = BPSession(k, c)
        self._bind_bp_notify(sess)

        self.bridge.log_line.emit(f"[{k}|BP] 已检测 FFF0/FFF1/FFF2，开始订阅 FFF1…")
        for attempt in range(8):
            try:
                await c.start_notify(BP_NOTIFY_UUID, sess.bp_notify_handler)  # type: ignore[attr-defined]
                break
            except Exception as e:  # noqa: BLE001
                if attempt < 7 and _is_winrt_user_cancelled(e):
                    self.bridge.log_line.emit(f"[{k}|BP] 订阅被系统取消，0.7s 后重试…")
                    await asyncio.sleep(0.7)
                    continue
                await c.disconnect()
                raise

        self._bp_sessions[k] = sess
        if self.active_bp_address is None or self.active_bp_address not in self._bp_sessions:
            self.active_bp_address = k
        self.bridge.status.emit(f"已连接血压计并监听: {k}")

    def _bind_bp_notify(self, sess: BPSession) -> None:
        """绑定血压计 FFF1 通知回调（闭包，防多设备串数据）。"""

        def bp_notify_handler(_sender: int, data: bytearray) -> None:
            pref = sess.log_prefix()
            self.bridge.log_line.emit(f"{pref} FFF1: {bytes(data).hex()}")
            for fr in sess.parser.feed(bytes(data)):
                md = sess.meas_done

                def _on_done() -> None:
                    if md is None or md.is_set():
                        return
                    loop = self._async_loop
                    if loop is not None:
                        loop.call_soon_threadsafe(md.set)
                    else:
                        md.set()

                dispatch_ruiguang_frame(
                    fr,
                    {
                        "on_log": lambda m, p=pref: self.bridge.log_line.emit(f"{p} {m}"),
                        "on_pressure": self.bridge.pressure_mmhg.emit,
                        "on_power_mv": lambda mv, s=sess: self._on_bp_power(s, mv),
                        "on_measurement_done": _on_done,
                        # 结构化结果：带上本会话 MAC，供界面结果区与 TV 推送区分多台 BP
                        "on_result": lambda sys_, dia_, pul_, a=sess.address: (
                            self._emit_measurement_result(a, sys_, dia_, pul_)
                        ),
                    },
                )

        sess.bp_notify_handler = bp_notify_handler  # type: ignore[attr-defined]

    def _emit_measurement_result(self, mac: str, sys_: int, dia_: int, pulse: int) -> None:
        """把结构化测量结果通过 bridge 信号转发给界面（若 bridge 提供该信号）。"""
        sig = getattr(self.bridge, "measurement_result", None)
        if sig is not None:
            sig.emit(mac, sys_, dia_, pulse)

    def _on_bp_power(self, sess: BPSession, mv: int) -> None:
        sess.last_power = mv

    # ══════════════════════════════════════════════════════════════
    # 心率手环连接（HR 路径）—— 完全委托给 HRBleClient
    # ══════════════════════════════════════════════════════════════

    async def connect_hr(self, address: str, do_pair: bool) -> None:
        """
        连接标准心率手环（0x180D / 0x2A37）。

        全部逻辑委托给 hr_ble_backend.HRBleClient，与血压计代码完全解耦。

        核心原则（来自 HeartRateMonitor-1.3.8 + docs 分析）：
        - 裸连接：BleakClient(address)，不加任何额外参数
        - 连接前不判断广播包是否包含 0x180D（绝大多数手环不声明）
        - 连接后查 client.services 有无 0x180D
        - 不使用 services=[...] 过滤，不使用 winrt={"use_cached_services": False}

        参数 do_pair 在心率路径通常为 False（大多数手环不需要配对）。
        若用户勾选了「连接时系统配对」，也只是记录日志，
        HRBleClient 本身的 BleakClient(address) 不处理配对。
        """
        k = norm_mac(address)
        if k in self._hr_clients:
            raise RuntimeError(f"该 MAC 已连接: {k}")

        self._async_loop = asyncio.get_running_loop()
        pref = f"[{k}|HR]"

        if do_pair:
            self.bridge.log_line.emit(
                f"{pref} 注意：心率手环通常不需要系统配对，已忽略「连接时系统配对」选项。\n"
                f"  若手环连接后报「访问拒绝」，请在 Windows 蓝牙设置里手动配对该设备。"
            )

        # 创建 HRBleClient，注入日志和心率数据回调
        hr_client = HRBleClient(k)
        hr_client.on_log = lambda msg: self.bridge.log_line.emit(msg)
        hr_client.on_heart_rate = lambda bpm: (
            self.bridge.heart_rate.emit(k, bpm),
        )

        # 委托连接（裸连接，所有细节在 HRBleClient 内部处理）
        try:
            success, msg = await hr_client.connect()
        except asyncio.TimeoutError:
            raise RuntimeError(format_hr_error(asyncio.TimeoutError()))
        except BleakError as e:
            raise RuntimeError(format_hr_error(e))
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"心率手环连接异常: {e!r}")

        if not success:
            # 连接成功但不支持 0x180D（设备不是标准心率设备）
            raise RuntimeError(msg)

        self._hr_clients[k] = hr_client
        self.bridge.status.emit(f"已连接心率手环: {k}")

    # ══════════════════════════════════════════════════════════════
    # 血压计指令发送
    # ══════════════════════════════════════════════════════════════

    def _require_bp_session(self) -> BPSession:
        """获取当前活动血压计会话，未连接时抛出 RuntimeError。"""
        s = self._active_bp_session()
        if s is None or not s.client.is_connected:
            raise RuntimeError(
                "未连接瑞光血压计，或「血压指令目标」已断开；请先连接并在下拉框选择目标。"
            )
        return s

    async def send_connect_command(self) -> None:
        await self._write_to_bp_session(self._require_bp_session(), CMD_CONNECT)

    async def send_query_power(self) -> None:
        await self._write_to_bp_session(self._require_bp_session(), CMD_QUERY_POWER)

    async def send_start_measurement(self) -> None:
        await self._write_to_bp_session(self._require_bp_session(), CMD_START)

    async def send_stop(self) -> None:
        s = self._active_bp_session()
        if s and s.client.is_connected:
            await self._write_to_bp_session(s, CMD_STOP)

    async def _write_to_bp_session(self, sess: BPSession, data: bytes) -> None:
        """向血压计的 FFF2 特征写入命令帧。"""
        self.bridge.log_line.emit(f"{sess.log_prefix()} 写入 FFF2: {data.hex()}")
        await sess.client.write_gatt_char(BP_WRITE_UUID, data, response=False)
        await asyncio.sleep(WRITE_GAP_SEC)

    # ══════════════════════════════════════════════════════════════
    # 血压计测量流程
    # ══════════════════════════════════════════════════════════════

    async def run_full_measurement(self, force: bool, device_type_9000: bool) -> None:
        """
        完整测量流程：发连接指令 → 查电量 → 启动测量 → 等结果 → 停止。

        :param force:          True = 忽略电量门限（调试用）
        :param device_type_9000: True = TYPE_9000 设备，跳过连接指令（CC 80 01 01）
        """
        sess = self._require_bp_session()
        sess.meas_done = asyncio.Event()
        sess.last_power = None

        if not device_type_9000:
            self.bridge.log_line.emit(f"{sess.log_prefix()} 发送连接指令（TYPE_88A）…")
            await self._write_to_bp_session(sess, CMD_CONNECT)
        else:
            self.bridge.log_line.emit(f"{sess.log_prefix()} TYPE_9000：跳过连接指令")

        await self._write_to_bp_session(sess, CMD_QUERY_POWER)
        for _ in range(50):
            if sess.last_power is not None:
                break
            await asyncio.sleep(0.1)

        if not force:
            if sess.last_power is None:
                raise RuntimeError("未收到电量数据：请勾选「忽略电量门限」后重试。")
            if sess.last_power <= MIN_POWER_MV:
                raise RuntimeError(
                    f"电量 {sess.last_power} mV 不高于 {MIN_POWER_MV} mV，已中止充气；"
                    "可勾选忽略门限调试。"
                )

        self.bridge.log_line.emit(f"{sess.log_prefix()} 启动测量（袖带会充气，请注意安全）…")
        await self._write_to_bp_session(sess, CMD_START)
        try:
            await asyncio.wait_for(sess.meas_done.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            self.bridge.log_line.emit(f"{sess.log_prefix()} 等待测量结果超时（180s）。")
        finally:
            self.bridge.log_line.emit(f"{sess.log_prefix()} 发送停止测量指令…")
            try:
                await self._write_to_bp_session(sess, CMD_STOP)
            except Exception as e:  # noqa: BLE001
                self.bridge.log_line.emit(f"{sess.log_prefix()} 停止指令: {e!r}")
            sess.meas_done = None

    async def run_start_wait_stop_only(self) -> None:
        """仅发启动 → 等结果 → 停止（不含连接指令，供「一键完整测量」后续调用）。"""
        sess = self._require_bp_session()
        sess.meas_done = asyncio.Event()
        self.bridge.log_line.emit(f"{sess.log_prefix()} 发送启动测量…")
        await self._write_to_bp_session(sess, CMD_START)
        try:
            await asyncio.wait_for(sess.meas_done.wait(), timeout=180.0)
        except asyncio.TimeoutError:
            self.bridge.log_line.emit(f"{sess.log_prefix()} 等待测量结果超时（180s）。")
        finally:
            self.bridge.log_line.emit(f"{sess.log_prefix()} 发送停止测量指令…")
            try:
                await self._write_to_bp_session(sess, CMD_STOP)
            except Exception as e:  # noqa: BLE001
                self.bridge.log_line.emit(f"{sess.log_prefix()} 停止指令: {e!r}")
            sess.meas_done = None

    async def probe_fff0_service_only(self, address: str, do_pair: bool) -> Tuple[bool, str]:
        """批量探测：快速连接并检查 FFF0 服务是否存在（不订阅 FFF1）。"""
        k = norm_mac(address)
        c = _make_bp_client(k, service_uuids=[BP_SERVICE_UUID])
        try:
            await c.connect()
            if do_pair and hasattr(c, "pair"):
                try:
                    await c.pair()
                except Exception:  # noqa: BLE001
                    pass
            found = any(service_uuid_match(str(s.uuid), BP_SERVICE_UUID) for s in c.services)
            if found:
                return True, "发现 FFF0（瑞光透传服务）"
            return False, "已连上 GATT，但未发现 FFF0（多半不是本协议血压计）"
        except Exception as e:  # noqa: BLE001
            return False, f"连接/枚举失败: {e!r}"
        finally:
            try:
                if c.is_connected:
                    await c.disconnect()
            except Exception:  # noqa: BLE001
                pass

    # 旧名兼容
    async def _disconnect_coro(self) -> None:
        await self.disconnect_all()


# ──────────────────────────────────────────────────────────────────────
# 视图适配器（供 sessions 属性返回统一格式）
# ──────────────────────────────────────────────────────────────────────

class _BPSessionView:
    """
    将 BPSession 包装成与旧 BleSession 兼容的视图对象。
    界面调用 sess.kind / sess.address / sess.is_connected 时都能正常工作。
    """

    def __init__(self, s: BPSession) -> None:
        self._s = s

    @property
    def kind(self) -> str:
        return "bp"

    @property
    def address(self) -> str:
        return self._s.address

    @property
    def is_connected(self) -> bool:
        return bool(self._s.client.is_connected)

    def log_prefix(self) -> str:
        return self._s.log_prefix()


class _HRClientView:
    """
    将 HRBleClient 包装成与旧 BleSession 兼容的视图对象。
    """

    def __init__(self, c: HRBleClient) -> None:
        self._c = c

    @property
    def kind(self) -> str:
        return "hr"

    @property
    def address(self) -> str:
        return self._c.address

    @property
    def is_connected(self) -> bool:
        return bool(self._c.is_connected)

    def log_prefix(self) -> str:
        return f"[{self._c.address}|HR]"
