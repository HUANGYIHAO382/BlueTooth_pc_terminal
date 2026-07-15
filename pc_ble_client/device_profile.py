# -*- coding: utf-8 -*-
"""
设备配置档案（本地 JSON 持久化）。

目的（初学者向）：
- 把「某台 MAC 是手环还是血压计、用什么角色连、是否预连接」这些信息记下来，
  下次扫描到同一台设备就能自动标记类型、一键按既定方式连接，省去每次手选。

存储位置：应用可写根目录下的 ``devices.json``
（源码运行时为 ``pc_ble_client/``；绿色版 exe 为 exe 同目录）。
旧版 ``device_profiles.json`` 会自动迁移。
用纯 JSON（而非 SQLite）是为了方便你直接用记事本查看/手改。

数据结构（与需求文档一致）::

    {
      "mac":  "F8:3B:7E:09:BD:BB",
      "name": "HUAWEI Band 11",
      "type": "band",          # band(手环) / bp(血压计) / scale(体脂秤，暂占位)
      "role": "client",        # client / server —— 仅用于界面展示，不改变实际连接
      "auto_connect": true,    # 是否在扫描到时尝试预连接
      "last_connected": "2024-06-14 10:00",  # 最近一次成功连接时间
      "protocol": "TYPE_9000"  # 血压计特有：型号协议（可空）
    }

重要说明：在 Windows / bleak 上，PC 始终是 GATT「中心(client)」，外设是「外围(server)」。
``role`` 字段只用于会话面板的只读展示，连接时真正的路由依据是 ``type``
（band→标准心率 0x180D，bp→瑞光透传 FFF0）。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, asdict, field
from datetime import datetime
from typing import Dict, List, Optional

from app_paths import get_app_dir

# 设备类型常量
TYPE_BAND = "band"   # 心率手环（标准 0x180D / 0x2A37）
TYPE_BP = "bp"       # 瑞光血压计（FFF0 / FFF1 / FFF2）
TYPE_SCALE = "scale" # 体脂秤（暂未实现，仅档案占位）

# 连接角色常量（仅展示用）
ROLE_CLIENT = "client"
ROLE_SERVER = "server"

# 档案文件名（放在应用可写根目录，见 app_paths.get_app_dir）
_PROFILE_FILENAME = "devices.json"
# 旧文件名：若存在则自动迁移到新文件名（兼容历史版本）
_LEGACY_FILENAME = "device_profiles.json"


def norm_mac(addr: str) -> str:
    """统一 MAC 字符串：去空白、大写、把减号换成冒号。"""
    return (addr or "").strip().upper().replace("-", ":")


def type_label(type_: str) -> str:
    """把设备类型代码转成中文显示名。"""
    return {
        TYPE_BAND: "心率手环",
        TYPE_BP: "血压计",
        TYPE_SCALE: "体脂秤",
    }.get(type_, "未知")


@dataclass
class DeviceProfile:
    """单台设备的配置档案。"""

    mac: str
    name: str = ""
    type: str = TYPE_BAND
    role: str = ROLE_CLIENT
    auto_connect: bool = False
    last_connected: Optional[str] = None
    protocol: Optional[str] = None
    notes: str = ""          # 备注（如「办公室测试手环」）
    group: str = ""          # 分组（如「门诊组 / 家庭组」，预留筛选用）
    strategy: str = ""       # 连接策略（如 reconnect_on_fail / timeout_30s，预留）

    def __post_init__(self) -> None:
        # 始终保证 MAC 规范化，避免大小写/分隔符导致查不到
        self.mac = norm_mac(self.mac)

    @staticmethod
    def from_dict(d: dict) -> "DeviceProfile":
        """从 JSON 字典还原；对缺失字段给出安全默认值。"""
        return DeviceProfile(
            mac=norm_mac(str(d.get("mac", ""))),
            name=str(d.get("name", "") or ""),
            type=str(d.get("type", TYPE_BAND) or TYPE_BAND),
            role=str(d.get("role", ROLE_CLIENT) or ROLE_CLIENT),
            auto_connect=bool(d.get("auto_connect", False)),
            last_connected=(d.get("last_connected") or None),
            protocol=(d.get("protocol") or None),
            notes=str(d.get("notes", "") or ""),
            group=str(d.get("group", "") or ""),
            strategy=str(d.get("strategy", "") or ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)

    def touch_connected(self) -> None:
        """记录「刚刚成功连接」的时间戳。"""
        self.last_connected = datetime.now().strftime("%Y-%m-%d %H:%M")


class DeviceProfileStore:
    """
    设备档案库：负责加载 / 保存 / 查询 / 增改 / 删除。

    用法::

        store = DeviceProfileStore()          # 自动从 device_profiles.json 读取
        p = store.get("F8:3B:...")            # 查不到返回 None
        store.upsert(DeviceProfile(mac=...))  # 新增或覆盖，并立即落盘
        store.remove("F8:3B:...")             # 删除并落盘
    """

    def __init__(self, path: Optional[str] = None) -> None:
        if path is None:
            # 与 gateway.json 一样：绿色版写到 exe 旁，源码写到本目录
            here = str(get_app_dir())
            path = os.path.join(here, _PROFILE_FILENAME)
            # 历史兼容：旧 device_profiles.json 存在而新 devices.json 不存在时迁移
            legacy = os.path.join(here, _LEGACY_FILENAME)
            if (not os.path.exists(path)) and os.path.exists(legacy):
                try:
                    os.replace(legacy, path)
                except OSError:
                    pass
        self._path = path
        # 以规范化 MAC 为键
        self._profiles: Dict[str, DeviceProfile] = {}
        self.load()

    @property
    def path(self) -> str:
        return self._path

    def __len__(self) -> int:
        return len(self._profiles)

    # ---- 读写 ----

    def load(self) -> None:
        """从磁盘加载档案；文件不存在或损坏时以空库启动（不抛异常）。"""
        self._profiles.clear()
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (OSError, ValueError):
            # 文件损坏：保持空库，避免影响程序启动
            return
        if isinstance(data, list):
            for item in data:
                if not isinstance(item, dict):
                    continue
                p = DeviceProfile.from_dict(item)
                if p.mac:
                    self._profiles[p.mac] = p

    def save(self) -> None:
        """把当前档案写回磁盘（JSON 数组，带缩进便于手改）。"""
        try:
            with open(self._path, "w", encoding="utf-8") as fp:
                json.dump(
                    [p.to_dict() for p in self._profiles.values()],
                    fp,
                    ensure_ascii=False,
                    indent=2,
                )
        except OSError:
            # 落盘失败不应让 UI 崩溃；仅放弃本次持久化
            pass

    # ---- 查询 / 增改 / 删除 ----

    def get(self, mac: str) -> Optional[DeviceProfile]:
        """按 MAC 查档案；查不到返回 None。"""
        return self._profiles.get(norm_mac(mac))

    def has(self, mac: str) -> bool:
        return norm_mac(mac) in self._profiles

    def all(self) -> List[DeviceProfile]:
        return list(self._profiles.values())

    def upsert(self, profile: DeviceProfile) -> DeviceProfile:
        """新增或覆盖一条档案，并立即落盘。返回存入的对象。"""
        profile.mac = norm_mac(profile.mac)
        self._profiles[profile.mac] = profile
        self.save()
        return profile

    def set_type(
        self,
        mac: str,
        type_: str,
        *,
        name: str = "",
        role: Optional[str] = None,
        protocol: Optional[str] = None,
    ) -> DeviceProfile:
        """
        便捷方法：把某 MAC 设为指定类型（右键菜单「设为心率手环 / 血压计」用）。

        已存在则只更新类型/名称/协议；不存在则新建。role 默认按类型推断。
        """
        mac = norm_mac(mac)
        p = self._profiles.get(mac)
        if role is None:
            # 经验默认：手环视为 client，血压计/体脂秤视为 server（仅展示语义）
            role = ROLE_CLIENT if type_ == TYPE_BAND else ROLE_SERVER
        if p is None:
            p = DeviceProfile(mac=mac, name=name, type=type_, role=role, protocol=protocol)
        else:
            p.type = type_
            p.role = role
            if name:
                p.name = name
            if protocol is not None:
                p.protocol = protocol
        return self.upsert(p)

    def mark_connected(self, mac: str, name: str = "") -> Optional[DeviceProfile]:
        """连接成功后回写 last_connected（若该 MAC 有档案）。"""
        p = self._profiles.get(norm_mac(mac))
        if p is None:
            return None
        if name and not p.name:
            p.name = name
        p.touch_connected()
        self.save()
        return p

    def remove(self, mac: str) -> bool:
        """删除某 MAC 的档案；删除成功返回 True。"""
        mac = norm_mac(mac)
        if mac in self._profiles:
            del self._profiles[mac]
            self.save()
            return True
        return False

    # ---- 预连接池相关 ----

    def get_auto_connect_devices(self) -> List[DeviceProfile]:
        """返回所有开启了 auto_connect 的档案（预连接池）。"""
        return [p for p in self._profiles.values() if p.auto_connect]

    def auto_connect_count(self) -> int:
        return len(self.get_auto_connect_devices())

    def set_auto_connect(self, mac: str, value: bool) -> Optional[DeviceProfile]:
        """开关某 MAC 的预连接；档案不存在返回 None。"""
        p = self._profiles.get(norm_mac(mac))
        if p is None:
            return None
        p.auto_connect = bool(value)
        self.save()
        return p

    # ---- 导入 / 导出（备份配置）----

    def export_to(self, path: str) -> None:
        """把全部档案导出为 JSON 数组文件（用于备份）。"""
        with open(path, "w", encoding="utf-8") as fp:
            json.dump(
                [p.to_dict() for p in self._profiles.values()],
                fp,
                ensure_ascii=False,
                indent=2,
            )

    def import_from(self, path: str, *, merge: bool = True) -> int:
        """
        从 JSON 文件导入档案。

        :param merge: True=与现有合并（同 MAC 覆盖）；False=清空后导入
        :return: 成功导入的条目数
        """
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
        if not isinstance(data, list):
            raise ValueError("导入文件格式应为 JSON 数组")
        if not merge:
            self._profiles.clear()
        count = 0
        for item in data:
            if not isinstance(item, dict):
                continue
            p = DeviceProfile.from_dict(item)
            if p.mac:
                self._profiles[p.mac] = p
                count += 1
        self.save()
        return count
