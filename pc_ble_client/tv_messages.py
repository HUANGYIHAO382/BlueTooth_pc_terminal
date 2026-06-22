# -*- coding: utf-8 -*-
"""
TV 联动 JSON 消息构造（F2 扁平 JSON，P0 产品协议）。

所有 PC→TV 的结构化报文应经本模块生成，避免在界面层散落 dict。
字段定义以 docs/通讯格式文档.md 与 docs/pc_gateway升级方案.md 为准。
"""

from __future__ import annotations

import json
import time
from typing import Any, List, Optional


def now_ts_ms() -> int:
    """Unix 毫秒时间戳。"""
    return int(time.time() * 1000)


def to_bytes(msg: dict[str, Any]) -> bytes:
    """序列化为 UDP 包体（UTF-8 JSON 一行）。"""
    return json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def script_ready(
    *,
    script_ip: str,
    listen_port: int,
    devices: Optional[List[str]] = None,
    device_type: str = "BP",
) -> dict[str, Any]:
    """网关发现：告诉 TV 往 script_ip:listen_port 发控制指令。"""
    return {
        "type": "SCRIPT_READY",
        "script_ip": script_ip,
        "listen_port": listen_port,
        "device_type": device_type,
        "devices": devices or ["BP", "Band"],
    }


def device_ready(
    *,
    device: str = "BP",
    device_name: str = "",
    timestamp_ms: Optional[int] = None,
) -> dict[str, Any]:
    """血压计（或其它设备）已连接、可测量。"""
    return {
        "type": "DEVICE_READY",
        "device": device,
        "device_name": device_name or device,
        "timestamp": timestamp_ms if timestamp_ms is not None else now_ts_ms(),
    }


def device_offline(
    *,
    device: str = "BP",
    reason: str = "bluetooth_disconnected",
) -> dict[str, Any]:
    """设备断开。"""
    return {
        "type": "DEVICE_OFFLINE",
        "device": device,
        "reason": reason,
    }


def heart_rate_stream(
    *,
    heart_rate: int,
    device: str = "Band",
    timestamp_ms: Optional[int] = None,
) -> dict[str, Any]:
    """心率遥测流（约 1Hz）。"""
    return {
        "type": "HEART_RATE_STREAM",
        "timestamp": timestamp_ms if timestamp_ms is not None else now_ts_ms(),
        "heart_rate": heart_rate,
        "device": device,
    }


def measure_progress(
    *,
    request_id: str,
    phase: str,
    progress: int,
    pressure_mmhg: int,
    device_category: str = "BP",
) -> dict[str, Any]:
    """测压进度（加压/减压/分析）。"""
    return {
        "type": "MEASURE_PROGRESS",
        "request_id": request_id,
        "device_category": device_category,
        "phase": phase,
        "progress": max(0, min(100, int(progress))),
        "pressure_mmhg": pressure_mmhg,
    }


def measure_result(
    *,
    request_id: str,
    systolic: int,
    diastolic: int,
    pulse: int,
    timestamp_ms: Optional[int] = None,
    device_category: str = "BP",
) -> dict[str, Any]:
    """测压最终结果。"""
    ts = timestamp_ms if timestamp_ms is not None else now_ts_ms()
    return {
        "type": "MEASURE_RESULT",
        "request_id": request_id,
        "device_category": device_category,
        "payload": {
            "systolic": systolic,
            "diastolic": diastolic,
            "pulse": pulse,
            "timestamp": ts,
        },
    }


def measure_error(
    *,
    request_id: str,
    error_code: str,
    message: str,
    device_category: str = "BP",
) -> dict[str, Any]:
    """测压失败。"""
    return {
        "type": "MEASURE_ERROR",
        "request_id": request_id,
        "device_category": device_category,
        "error_code": error_code,
        "message": message,
    }


def ack(*, request_id: str, message: str = "BP started") -> dict[str, Any]:
    """收到 START_MEASURE 后立即回复。"""
    return {
        "type": "ACK",
        "request_id": request_id,
        "message": message,
    }


def ping_json() -> dict[str, Any]:
    """JSON 格式测试连接。"""
    return {"type": "PING", "ts": now_ts_ms()}
