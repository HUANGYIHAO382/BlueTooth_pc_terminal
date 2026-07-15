# -*- coding: utf-8 -*-
"""
网关运行配置（gateway.json）的加载与持久化。

与 devices.json（蓝牙设备档案）分离：本文件只存 TV 联调、协议阶段、端口等网关参数。
"""

from __future__ import annotations

import json
import socket
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

from app_paths import get_app_dir

# 协议阶段：L0=纯文本 Legacy；T0=18500 JSON+可选文本；P0=双信道闭环
ProtocolStage = Literal["L0", "T0", "P0"]

GATEWAY_VERSION = "2.3.0"


def get_default_gateway_path() -> Path:
    """
    gateway.json 的默认路径。

    - 源码运行：pc_ble_client/gateway.json
    - 绿色版 exe：与 PCBleGateway.exe 同目录（用户可改、可保存）
    """
    return get_app_dir() / "gateway.json"


def detect_lan_ip() -> str:
    """
    尝试检测本机在局域网中的 IPv4 地址（用于 SCRIPT_READY.script_ip）。

    原理：UDP 连接外部地址（不真正发包）让系统选出默认出口网卡 IP。
    失败时返回 127.0.0.1，界面应提示用户手填。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        pass
    return "127.0.0.1"


@dataclass
class GatewayConfig:
    """网关配置项（与 gateway.json 字段一一对应）。"""

    protocol_stage: ProtocolStage = "P0"
    tv_mode: str = "broadcast"  # broadcast | unicast
    tv_ip: str = "255.255.255.255"
    tv_unicast_ip: str = ""
    port_a: int = 18500
    port_b: int = 18501
    text_mode: bool = False
    json_mode: bool = True
    no_broadcast: bool = False
    script_ip: str = ""
    script_ready_interval_sec: int = 60
    # TV 端 DEVICE_READY 45s 超时；PC 每 10s 刷新一次保持「可测量」角标
    device_ready_interval_sec: int = 10
    progress_throttle_ms: int = 200
    hr_throttle_ms: int = 1000
    auto_start_gateway: bool = True

    def normalize_ports_for_stage(self) -> bool:
        """
        P0 双信道固定端口：A=18500 遥测，B=18501 控制。
        若 gateway.json 被误改，自动校正并返回 True 表示有改动。
        """
        changed = False
        if self.protocol_stage == "P0":
            if self.port_a != 18500:
                self.port_a = 18500
                changed = True
            if self.port_b != 18501:
                self.port_b = 18501
                changed = True
        return changed

    def effective_script_ip(self) -> str:
        """SCRIPT_READY 里写入的 PC IP。"""
        return (self.script_ip or "").strip() or detect_lan_ip()

    def listen_port_for_stage(self) -> int:
        """TV 发 START/START_MEASURE 时应打到的端口（写在 SCRIPT_READY 里）。"""
        if self.protocol_stage == "P0":
            return self.port_b
        return self.port_a

    def effective_unicast_ip(self) -> str:
        """单播加固目标：优先 tv_unicast_ip，否则广播模式下用 tv_ip（单播模式）。"""
        if self.tv_unicast_ip.strip():
            return self.tv_unicast_ip.strip()
        if self.tv_mode == "unicast":
            return self.tv_ip.strip() or "255.255.255.255"
        return ""

    def is_emulator_profile(self) -> bool:
        """
        是否为 Windows 模拟器联调配置（run_gui.py --emulator）。

        特征：禁广播 + 单播 127.0.0.1 + SCRIPT_READY 里 script_ip=10.0.2.2。
        此时 TV 的 START_MEASURE.reply_to 为 127.0.0.1:18500，仅 adb redir 18500。
        """
        return (
            self.no_broadcast
            and self.tv_unicast_ip.strip() == "127.0.0.1"
            and self.script_ip.strip() == "10.0.2.2"
        )

    def default_measure_reply_to(self, tv_source_ip: str = "") -> tuple[str, int]:
        """
        PC 回 ACK / MEASURE_PROGRESS / MEASURE_RESULT 的默认目标。

        - 模拟器（防回环）：127.0.0.1:18500，经 adb「仅 redir 18500」回到 TV
        - 真机：TV 局域网 IP:18501（信道 B）
        """
        if self.is_emulator_profile():
            return ("127.0.0.1", self.port_a)
        ip = (tv_source_ip or self.effective_unicast_ip() or self.tv_ip).strip()
        if not ip or ip == "255.255.255.255":
            ip = "127.0.0.1"
        return (ip, self.port_b)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GatewayConfig":
        stage = str(data.get("protocol_stage", "P0")).upper()
        if stage not in ("L0", "T0", "P0"):
            stage = "P0"
        return cls(
            protocol_stage=stage,  # type: ignore[arg-type]
            tv_mode=str(data.get("tv_mode", "broadcast")),
            tv_ip=str(data.get("tv_ip", "255.255.255.255")),
            tv_unicast_ip=str(data.get("tv_unicast_ip", "")),
            port_a=int(data.get("port_a", 18500)),
            port_b=int(data.get("port_b", 18501)),
            text_mode=bool(data.get("text_mode", False)),
            json_mode=bool(data.get("json_mode", True)),
            no_broadcast=bool(data.get("no_broadcast", False)),
            script_ip=str(data.get("script_ip", "")),
            script_ready_interval_sec=int(data.get("script_ready_interval_sec", 60)),
            device_ready_interval_sec=int(data.get("device_ready_interval_sec", 10)),
            progress_throttle_ms=int(data.get("progress_throttle_ms", 200)),
            hr_throttle_ms=int(data.get("hr_throttle_ms", 1000)),
            auto_start_gateway=bool(data.get("auto_start_gateway", True)),
        )


class GatewayConfigStore:
    """读写 gateway.json。"""

    def __init__(self, path: Optional[Path] = None) -> None:
        # 未指定路径时，按「源码 / 绿色版」规则选可写目录
        self.path = path or get_default_gateway_path()
        self._config = GatewayConfig()
        self.load()

    @property
    def config(self) -> GatewayConfig:
        return self._config

    def load(self) -> GatewayConfig:
        if not self.path.is_file():
            self._config = GatewayConfig()
            self.save()
            return self._config
        try:
            with open(self.path, encoding="utf-8") as fp:
                data = json.load(fp)
            if isinstance(data, dict):
                self._config = GatewayConfig.from_dict(data)
            else:
                self._config = GatewayConfig()
        except (OSError, ValueError, json.JSONDecodeError):
            self._config = GatewayConfig()
        return self._config

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as fp:
            json.dump(self._config.to_dict(), fp, ensure_ascii=False, indent=2)

    def update(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            if hasattr(self._config, k):
                setattr(self._config, k, v)
        self.save()
