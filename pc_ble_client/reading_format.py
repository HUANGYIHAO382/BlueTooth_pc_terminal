# -*- coding: utf-8 -*-
"""
测量读数的「人类可读」格式化 + 结构化字段（供 JSON/TV 复用）。

设计目的：
- 界面、运行日志、TV 文本行、TV JSON 字段从同一数据源生成，禁止「先拼中文再正则拆回数字」。
- 不同设备类型转换后的展示不一样，集中在此维护。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from device_profile import TYPE_BAND, TYPE_BP, TYPE_SCALE, type_label

# 加压阶段跟踪（用于 progress / phase 计算，与 pc_gateway 文档一致）
_PHASE_INFLATING = "inflating"
_PHASE_DEFLATING = "deflating"
_PHASE_ANALYZING = "analyzing"

# 上次压力值，用于判断加压/减压（模块级，单台 BP 测量足够）
_last_pressure_mmhg: Optional[int] = None
_inflating_peak: int = 0


def reset_bp_pressure_tracking() -> None:
    """开始新一次测量前重置压力跟踪状态。"""
    global _last_pressure_mmhg, _inflating_peak  # noqa: PLW0603
    _last_pressure_mmhg = None
    _inflating_peak = 0


def _compute_phase_and_progress(mmhg: int) -> tuple[str, int]:
    """
    根据当前袖带压力估算 phase 与 progress（0–100）。

    映射参考 docs/pc_gateway升级方案.md §7：
    - 加压前半 10–55，加压后半 56–88，减压 89–95，分析 96–100
    """
    global _last_pressure_mmhg, _inflating_peak  # noqa: PLW0603

    prev = _last_pressure_mmhg
    _last_pressure_mmhg = mmhg

    if prev is None or mmhg >= prev:
        _inflating_peak = max(_inflating_peak, mmhg)
        phase = _PHASE_INFLATING
        if _inflating_peak <= 0:
            progress = 10
        elif mmhg < _inflating_peak * 0.5:
            progress = 10 + int(45 * mmhg / max(_inflating_peak, 1))
        else:
            span = max(_inflating_peak - _inflating_peak * 0.5, 1)
            progress = 56 + int(32 * (mmhg - _inflating_peak * 0.5) / span)
        progress = max(10, min(88, progress))
    else:
        # 压力下降：减压或分析
        if mmhg > 30:
            phase = _PHASE_DEFLATING
            progress = 89 + int(6 * (1 - mmhg / max(_inflating_peak, 1)))
            progress = max(89, min(95, progress))
        else:
            phase = _PHASE_ANALYZING
            progress = 96

    return phase, progress


def format_hr(bpm: int) -> str:
    """心率手环：``心率: 86 BPM``。"""
    return f"心率: {bpm} BPM"


def format_bp_result(systolic: int, diastolic: int, pulse: int) -> str:
    """血压计测量结果。"""
    return f"血压: {systolic}/{diastolic} mmHg，脉搏 {pulse} BPM"


def format_bp_pressure(mmhg: int) -> str:
    """血压计加压过程中的实时压力。"""
    return f"加压中: {mmhg} mmHg"


def format_for_type(type_: str, **values) -> str:
    """按设备类型选择格式化函数；未知类型时兜底不抛异常。"""
    if type_ == TYPE_BAND and "bpm" in values:
        return format_hr(int(values["bpm"]))
    if type_ == TYPE_BP and {"systolic", "diastolic", "pulse"} <= values.keys():
        return format_bp_result(
            int(values["systolic"]), int(values["diastolic"]), int(values["pulse"])
        )
    if type_ == TYPE_BP and "mmhg" in values:
        return format_bp_pressure(int(values["mmhg"]))
    kv = "，".join(f"{k}={v}" for k, v in values.items())
    return f"{type_label(type_)}: {kv}"


@dataclass
class HrReading:
    """心率结构化读数。"""

    bpm: int

    @property
    def text(self) -> str:
        return format_hr(self.bpm)


@dataclass
class BpPressureReading:
    """血压加压过程读数。"""

    mmhg: int
    phase: str = _PHASE_INFLATING
    progress: int = 10

    @classmethod
    def from_mmhg(cls, mmhg: int) -> "BpPressureReading":
        phase, progress = _compute_phase_and_progress(mmhg)
        return cls(mmhg=mmhg, phase=phase, progress=progress)

    @property
    def text(self) -> str:
        if self.phase == _PHASE_INFLATING:
            return format_bp_pressure(self.mmhg)
        if self.phase == _PHASE_DEFLATING:
            return f"减压中: {self.mmhg} mmHg"
        return f"分析中: {self.mmhg} mmHg"


@dataclass
class BpResultReading:
    """血压测量结果。"""

    systolic: int
    diastolic: int
    pulse: int

    @property
    def text(self) -> str:
        return format_bp_result(self.systolic, self.diastolic, self.pulse)
