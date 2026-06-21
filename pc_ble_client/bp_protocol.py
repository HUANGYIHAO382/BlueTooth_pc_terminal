# -*- coding: utf-8 -*-
"""
瑞光康泰家用血压计 —— 蓝牙协议常量与解析（与厂家 PDF、Android Demo 一致）。

================================================================================
初学者必读：两件事不要混在一谈（你贴的「二、蓝牙指令工作流程」属于下面第 2 层）
================================================================================

【第 1 层：BLE 无线链路】
- 电脑要先通过 BLE「扫描广播 / 或已知 MAC」找到设备，再建立 GATT 连接。
- 这一层用的是操作系统蓝牙栈（Windows 上 bleak→WinRT），**不会**发送你 PDF 里的
  CC 80 / AA 80 应用层帧；搜不到设备时，问题在这一层（广播、被手机占用、驱动等），
  不是「没先发连接指令」——因为连接指令必须走已建立的 GATT 写通道。

【第 2 层：GATT 透传（厂家 PDF 的帧格式）】
- 连上后，在「服务 FFF0」下：
  - 终端→血压计：通过「下发特征 FFF2」写入一帧字节（前导一般为 CC 80）。
  - 血压计→终端：通过「上传特征 FFF1」通知一帧字节（前导一般为 AA 80）。
- 你理解的「要测的话终端要向血压计发包」**完全正确**，指的就是写 FFF2；
  本仓库里 ``CMD_CONNECT`` / ``CMD_START`` 等即 PDF 3.1、2.2 等节的完整帧（含校验）。

================================================================================
协议帧组成（与 PDF 第一章对应，便于你对照纸面）
================================================================================
1.1 前导码：终端→计 CC 80；计→终端 AA 80（表示一帧开始）。
1.2 设备版本：如 0x02 表示蓝牙通讯方式。
1.3 数据长度：仅指「类型标识 + 类型子码 + 数据内容」三部分的**总字节数**。
1.4 类型标识、1.5 类型子码：区分报文类别与操作（如连接应答、实时压力、测量结果等）。
1.6 数据内容：具体参数；无数据时可为 0x00。
1.7 校验码：除前导码与校验字节外，其余数据字节逐字节异或（见 ``xor_checksum``）。

================================================================================
业务流程（与 PDF「二、蓝牙指令工作流程」一致；本 PC 端实现顺序见 RuiguangBpSession / MultiBleBackend）
================================================================================
典型测量：设备开机 → 终端建立 BLE/GATT → 终端写「连接指令」→ 计应答(FFF1) →
终端写「启动指令」→ 测量中计上报实时压力(FFF1) → 完成 → 计上报测量结果 →
终端可写「停止」等。查电量：连上后写「电量查询」指令，计在 FFF1 应答。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple, TypedDict

from bleak.uuids import normalize_uuid_str


class FrameDispatchCallbacks(TypedDict, total=False):
    """解析到一帧后的回调（GUI 与命令行共用）。"""

    on_log: Callable[[str], None]
    on_pressure: Callable[[int], None]
    on_power_mv: Callable[[int], None]
    on_measurement_done: Callable[[], None]
    # 结构化测量结果回调：参数为 (收缩压, 舒张压, 脉搏)，供界面结果区与 TV 推送使用
    on_result: Callable[[int, int, int], None]

# 与厂家 PDF 1.8 一致的 UUID（16 位短 UUID 在 GATT 里常扩展为 128 位，比较时用 service_uuid_match）
BP_SERVICE_UUID = "0000fff0-0000-1000-8000-00805f9b34fb"
BP_NOTIFY_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"  # 上传（计→终端）透传
BP_WRITE_UUID = "0000fff2-0000-1000-8000-00805f9b34fb"  # 下发（终端→计）透传

# ---------------------------------------------------------------------------
# 终端→血压计 完整帧（经 FFF2 写入）。结构：CC 80 | ver | len | type | sub | data… | XOR
# 校验：XOR = ver ^ len ^ type ^ sub ^ (数据各字节) —— 与 PDF 3.1 备注算法一致。
# ---------------------------------------------------------------------------
# PDF 3.1 连接指令：CC 80 02 03 01 01 00 | XOR；XOR=0x02^0x03^0x01^0x01^0x00=0x01
CMD_CONNECT = bytes.fromhex("cc80020301010001")
# PDF 3.7 查询电量：类型标识 04、子码 04；XOR=0x02^0x03^0x04^0x04^0x00=0x01
CMD_QUERY_POWER = bytes.fromhex("cc80020304040001")
# PDF 2.2 启动测量：子码由 01 变为 02；XOR=0x02^0x03^0x01^0x02^0x00=0x02
CMD_START = bytes.fromhex("cc80020301020002")
# PDF 3.4 停止测量：子码 03；XOR=0x02^0x03^0x01^0x03^0x00=0x03
CMD_STOP = bytes.fromhex("cc80020301030003")

MIN_POWER_MV = 3600
WRITE_GAP_SEC = 0.55


def device_name_matches_legacy_android_demo(name: str) -> bool:
    """
    旧 Android 工程里为「缩小扫描列表」使用的设备名规则（不是协议层校验，连上后仍以 FFF0 服务为准）。

    依据源码：
    - BluetoothConnMeasureActivity.periodScanCallback：若名称非空，则
      deviceName.contains(\"RBP\") || deviceName.contains(\"BP\")，
      且自动连接分支还要求 contains(\"A\")（约 225–226 行，与具体型号有关；本 PC 端「仅 RBP/BP」勾选不强制 A）。
    - BluetoothManager 经典蓝牙发现：用「名称 + '-' + 地址」拼串后取前 3 字符与 \"RBP\" 比较，
      或整段 contains(\"BP\")（约 299–303 行）；该写法与纯 BLE 名称略有出入，本函数以 Activity 的 BLE 逻辑为主。

    注意：contains(\"BP\") 较宽，可能与其它设备撞名；若列表仍杂，请以连接后能否发现 FFF0 为准。
    """
    if not name or name == "(无广播名)":
        return False
    return ("RBP" in name) or ("BP" in name)


def sort_rows_bp_name_candidates_first(rows: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """把名称符合旧版 RBP/BP 规则的设备排到列表前面，其余按名称排序。"""
    return sorted(
        rows,
        key=lambda item: (not device_name_matches_legacy_android_demo(item[0]), item[0].lower()),
    )


def _norm_uuid(u: str) -> str:
    """去掉横线并转小写，便于比较。"""
    return u.replace("-", "").lower()


def service_uuid_match(actual: str, expected: str) -> bool:
    """
    判断服务/特征 UUID 是否与期望值一致（兼容 16 位短 UUID 与 128 位完整形式）。

    重要（初学者易踩坑）：**不能**用「去掉横线后比尾部几段十六进制」这类捷径。
    蓝牙 SIG 标准里 0x180D（心率）、0xFFF0（厂商自定义）等扩展为 128 位后**共用同一基底**，
    仅比尾部会与心率等服务误判为 FFF0，接着订阅 FFF1 会报「特征不存在」。
    这里统一交给 bleak 的 ``normalize_uuid_str`` 展开后再做字符串相等比较。
    """
    try:
        return normalize_uuid_str(str(actual)) == normalize_uuid_str(str(expected))
    except Exception:  # noqa: BLE001 — 兜底：无横线的原始串直接比
        return _norm_uuid(str(actual)) == _norm_uuid(str(expected))


def xor_checksum(body_without_preamble: bytes) -> int:
    """
    校验码（PDF 1.7）：对「设备版本 … 数据内容最后一字节」逐字节异或，不含前导码与校验字节本身。
    ``body_without_preamble`` 应传入从版本字节起到数据末尾的字节序列。
    """
    x = 0
    for b in body_without_preamble:
        x ^= b
    return x & 0xFF


@dataclass
class ParsedFrame:
    """血压计 -> 终端 一帧（已通过异或校验）。"""

    version: int
    length: int
    flag: int
    sub: int
    payload: bytes
    raw: bytes


class FrameParser:
    """
    从 FFF1 通知字节流中切出完整帧：前导 AA 80，与 Java BluetoothStateMachineGatt 同类逻辑。
    """

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, chunk: bytes) -> List[ParsedFrame]:
        self._buf.extend(chunk)
        out: List[ParsedFrame] = []
        i = 0
        b = self._buf
        while i + 5 <= len(b):
            if b[i] != 0xAA or b[i + 1] != 0x80:
                i += 1
                continue
            ver = b[i + 2]
            ln = b[i + 3]
            frame_len = 2 + 1 + 1 + ln + 1
            if i + frame_len > len(b):
                break
            frame = bytes(b[i : i + frame_len])
            body_for_xor = frame[2:-1]
            if xor_checksum(body_for_xor) != frame[-1]:
                i += 1
                continue
            flag = frame[4]
            sub = frame[5]
            payload = frame[6 : 4 + ln]
            out.append(ParsedFrame(ver, ln, flag, sub, payload, frame))
            i += frame_len
        del b[:i]
        return out


def dispatch_ruiguang_frame(fr: ParsedFrame, cb: FrameDispatchCallbacks) -> None:
    """
    按厂家 TYPE_88A 常见分支解析一帧，调用 cb 中提供的回调（未提供的则忽略）。
    """
    on_log = cb.get("on_log")
    on_pressure = cb.get("on_pressure")
    on_power_mv = cb.get("on_power_mv")
    on_measurement_done = cb.get("on_measurement_done")
    on_result = cb.get("on_result")

    if fr.flag == 1:
        # PDF 表1 实时压力：6 字节 Dat5..Dat0，本处 payload[0]=Dat5 … payload[5]=Dat0
        # 压力 mmHg = Dat4*256 + (Dat1 xor Dat4)，与文档举例 260mmHg 一致。
        if fr.sub == 0x05 and len(fr.payload) >= 6 and on_pressure is not None:
            highflag = fr.payload[1] & 0xFF
            lowflag = highflag ^ (fr.payload[4] & 0xFF)
            on_pressure((highflag << 8) + lowflag)
        elif fr.sub == 0x06:
            r = parse_measurement_android_style(fr.payload)
            if r:
                if on_log is not None:
                    on_log(f"测量结果: 收缩压={r[0]} 舒张压={r[1]} 脉搏={r[2]}")
                # 结构化回调：让界面结果区/ TV 推送拿到 (sys, dia, pulse)
                if on_result is not None:
                    on_result(r[0], r[1], r[2])
            if on_measurement_done is not None:
                on_measurement_done()
        elif fr.sub == 0x01 and on_log is not None:
            ok = len(fr.payload) >= 1 and (fr.payload[0] & 0xFF) == 0
            on_log(f"连接应答(子码01): {'成功' if ok else '失败'}")
        elif fr.sub == 0x07 and on_log is not None:
            on_log("设备报错子码 07（参见 PDF 表4）")
    elif fr.flag == 4 and fr.sub == 0x04 and len(fr.payload) >= 2:
        mv = ((fr.payload[0] & 0xFF) << 8) + (fr.payload[1] & 0xFF)
        if on_power_mv is not None:
            on_power_mv(mv)
        if on_log is not None:
            # 与保活/手动「查询电量」共用：写进「血压数据记录」便于对照 FFF1 十六进制上一行
            cmp_tip = "低于门限（一键测量可能被程序拒绝）" if mv <= MIN_POWER_MV else "高于门限（可充气）"
            on_log(f"[查询电量结果] {mv} mV — {cmp_tip}；门限参考 {MIN_POWER_MV} mV（PDF 类型 04/子码 04）")


def parse_measurement_android_style(payload: bytes) -> Optional[tuple[int, int, int]]:
    """
    解析测量结果子码 0x06 的 data 区（与 Android BluetoothService.getResult 一致）。

    PDF 3.5：在「用户标识 + 测量时间(6B)」之后为血压值 6 字节（表3：SYS 高/低、DIA 高/低、PUL 高/低），
    故收缩压从 payload 偏移 7 起取 2 字节等；若帧结构变化需同步调整偏移。
    """
    if len(payload) < 13:
        return None
    math = 256
    sys_mmhg = (payload[7] & 0xFF) * math + (payload[8] & 0xFF)
    dia_mmhg = payload[10] & 0xFF
    pulse = ((payload[11] & 0xFF) << 4) + (payload[12] & 0xFF)
    return abs(sys_mmhg), abs(dia_mmhg), pulse


class RuiguangBpSession:
    """
    一次完整测量会话（内部自建 BleakClient，供命令行 ruiguang_bp_pc.py 使用）。
    """

    def __init__(
        self,
        address: str,
        *,
        force_measure: bool,
        device_type_9000: bool,
        on_pressure: Callable[[int], None],
        on_log: Callable[[str], None],
    ) -> None:
        self.address = address
        self.force_measure = force_measure
        self.device_type_9000 = device_type_9000
        self.on_pressure = on_pressure
        self.on_log = on_log
        self._parser = FrameParser()
        self._client: Optional[object] = None
        self._loop: Optional[object] = None
        self._last_power_mv: Optional[int] = None
        self._done = None  # asyncio.Event，在 run 内创建

    async def _write_cmd(self, data: bytes) -> None:
        import asyncio

        assert self._client is not None
        self.on_log(f"写入 FFF2: {data.hex()}")
        await self._client.write_gatt_char(BP_WRITE_UUID, data, response=False)
        await asyncio.sleep(WRITE_GAP_SEC)

    def _on_notify(self, _sender: int, data: bytearray) -> None:
        self.on_log(f"通知 FFF1: {bytes(data).hex()}")
        for fr in self._parser.feed(bytes(data)):
            self._handle_frame(fr)

    def _handle_frame(self, fr: ParsedFrame) -> None:
        def on_power_mv(mv: int) -> None:
            self._last_power_mv = mv

        def on_measurement_done() -> None:
            if self._loop is not None:
                self._loop.call_soon_threadsafe(self._done.set)
            else:
                self._done.set()

        dispatch_ruiguang_frame(
            fr,
            {
                "on_log": self.on_log,
                "on_pressure": self.on_pressure,
                "on_power_mv": on_power_mv,
                "on_measurement_done": on_measurement_done,
            },
        )

    async def run(self) -> None:
        import asyncio

        from bleak import BleakClient

        self._done = asyncio.Event()
        self._loop = asyncio.get_running_loop()
        self._client = BleakClient(self.address)
        async with self._client as client:
            if not client.is_connected:
                raise RuntimeError("未能保持 BLE 连接")
            self.on_log("已连接，开启 FFF1 通知…")
            await client.start_notify(BP_NOTIFY_UUID, self._on_notify)
            await asyncio.sleep(WRITE_GAP_SEC)

            if self.device_type_9000:
                self.on_log("设备类型 9000：跳过连接指令，直接查电量")
            else:
                self.on_log("发送连接指令（TYPE_88A）…")
                await self._write_cmd(CMD_CONNECT)

            self.on_log("查询电量…")
            await self._write_cmd(CMD_QUERY_POWER)

            for _ in range(50):
                if self._last_power_mv is not None:
                    break
                await asyncio.sleep(0.1)

            if not self.force_measure:
                if self._last_power_mv is None:
                    self.on_log("未收到电量数据，请勾选「忽略电量门限」或检查设备。")
                    return
                if self._last_power_mv <= MIN_POWER_MV:
                    self.on_log(
                        f"电量 {self._last_power_mv} mV ≤ {MIN_POWER_MV} mV，已中止充气；可勾选忽略门限后重试。"
                    )
                    return

            self.on_log("启动测量（袖带会充气）…")
            await self._write_cmd(CMD_START)

            try:
                await asyncio.wait_for(self._done.wait(), timeout=180.0)
            except asyncio.TimeoutError:
                self.on_log("等待测量结果超时（180s）")
            finally:
                self.on_log("发送停止测量指令…")
                try:
                    await self._write_cmd(CMD_STOP)
                except Exception as e:  # noqa: BLE001
                    self.on_log(f"停止指令写入异常（可忽略）: {e}")
                await asyncio.sleep(0.2)
