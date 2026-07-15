# -*- coding: utf-8 -*-
"""
应用目录解析（开发运行 / PyInstaller 打包通用）。

初学者说明：
- 用源码运行时：配置文件放在本目录（与 .py 同级），例如 gateway.json。
- 打成绿色版 exe 后：Python 文件被打包进 _internal，不能往里面写配置。
  此时应把 gateway.json / devices.json 放在「exe 旁边」，方便用户修改且可持久保存。

判断是否打包：查看 sys.frozen（PyInstaller 运行时会设为 True）。
"""

from __future__ import annotations

import sys
from pathlib import Path


def get_app_dir() -> Path:
    """
    返回「用户可读可写的应用根目录」。

    - 打包后（绿色版）：exe 所在文件夹
    - 开发时：pc_ble_client 源码目录
    """
    # PyInstaller onefile/onedir 都会设置 sys.frozen
    if getattr(sys, "frozen", False):
        # sys.executable 即 PCBleGateway.exe 的完整路径
        return Path(sys.executable).resolve().parent
    # 本文件在 pc_ble_client/ 下，因此 parent 就是客户端根目录
    return Path(__file__).resolve().parent


def get_resource_dir() -> Path:
    """
    返回打包资源目录（只读资源；当前项目主要用 get_app_dir 读写 JSON）。

    onedir 模式下，PyInstaller 6+ 的附加数据常在 _MEIPASS 或 _internal。
    """
    if getattr(sys, "frozen", False):
        # _MEIPASS：onefile 解压临时目录；onedir 时也可能存在
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent
