# -*- coding: utf-8 -*-
"""
测量读数的「人类可读」格式化（按设备类型转换）。

设计目的：
- 把界面显示、运行日志、TV 推送统一到「处理过后」的文本，不再出现 ``（原始 0656）``、
  ``[MAC|HR]`` 这类底层调试信息。
- 不同设备类型转换后的展示不一样（心率手环 / 血压计 / 体脂秤），集中在这里维护，
  以后加新设备只要在此追加一个 format_xxx 即可。

约定：返回的字符串「不含时间戳」，时间戳由调用方（日志/面板）统一加在前面，
形如 ``[15:08:35] 心率: 86 BPM``。
"""

from __future__ import annotations

from device_profile import TYPE_BAND, TYPE_BP, TYPE_SCALE, type_label


def format_hr(bpm: int) -> str:
    """心率手环：``心率: 86 BPM``（注意单位 BPM = 次/分）。"""
    return f"心率: {bpm} BPM"


def format_bp_result(systolic: int, diastolic: int, pulse: int) -> str:
    """血压计测量结果：``血压: 120/80 mmHg，脉搏 72 BPM``。"""
    return f"血压: {systolic}/{diastolic} mmHg，脉搏 {pulse} BPM"


def format_bp_pressure(mmhg: int) -> str:
    """血压计加压过程中的实时压力：``加压中: 150 mmHg``。"""
    return f"加压中: {mmhg} mmHg"


def format_for_type(type_: str, **values) -> str:
    """
    通用入口：按设备类型选择格式化函数。

    用法::

        format_for_type(TYPE_BAND, bpm=86)
        format_for_type(TYPE_BP, systolic=120, diastolic=80, pulse=72)

    未知类型时回退为「类型名 + 原始键值」，保证不抛异常。
    """
    if type_ == TYPE_BAND and "bpm" in values:
        return format_hr(int(values["bpm"]))
    if type_ == TYPE_BP and {"systolic", "diastolic", "pulse"} <= values.keys():
        return format_bp_result(
            int(values["systolic"]), int(values["diastolic"]), int(values["pulse"])
        )
    if type_ == TYPE_BP and "mmhg" in values:
        return format_bp_pressure(int(values["mmhg"]))
    # 兜底
    kv = "，".join(f"{k}={v}" for k, v in values.items())
    return f"{type_label(type_)}: {kv}"
