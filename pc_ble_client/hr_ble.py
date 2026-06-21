# -*- coding: utf-8 -*-
"""
标准 BLE 心率（与 HeartRateMonitor-main/Blegetheartbeat.py 一致）。

蓝牙 SIG 心率服务 0x180D，心率测量特征 0x2A37；notify 数据首字节为标志位，
bit0=1 表示心率值为 UINT16（小端），否则为 UINT8。
"""

from __future__ import annotations

from bleak.uuids import normalize_uuid_str

# 与 Blegetheartbeat.HEART_RATE_SERVICE_UUID / HEART_RATE_MEASUREMENT_UUID 一致
HEART_RATE_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"


def parse_heart_rate_measurement(data: bytes) -> int:
    """
    解析 0x2A37 通知负载为 BPM（与 Blegetheartbeat._parse_heart_rate 逻辑一致）。

    :param data: 外设推送的原始字节（至少 2 字节）
    :return: 心率 BPM
    """
    if len(data) < 2:
        return 0
    flags = data[0]
    if (flags & 0x01) == 0x01:
        return int.from_bytes(data[1:3], byteorder="little")
    return int(data[1])


def hr_service_uuid_in_client_services(services) -> bool:
    """
    判断已枚举的 GATT 服务中是否包含标准心率服务。

    使用 bleak 的 ``normalize_uuid_str`` 统一 16 位/128 位写法后再比较，避免手写 endswith 误判。
    """
    want = normalize_uuid_str(HEART_RATE_SERVICE_UUID)
    for s in services:
        if normalize_uuid_str(str(s.uuid)) == want:
            return True
    return False
