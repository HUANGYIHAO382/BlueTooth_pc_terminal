# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 规格文件：打成 Windows 绿色版目录（onedir）。

说明（初学者）：
- onedir：生成一个文件夹，内含 exe + _internal 依赖，启动比 onefile 快，也方便排查。
- 入口是 bp_demo_app.py（不要用 run_gui.py，后者还会尝试 pip install）。
- bleak / PySide6 用 collect_all 尽量把 Windows BLE 与 Qt 插件打全。
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules

# 本 spec 所在目录 = pc_ble_client
SPEC_ROOT = Path(SPECPATH).resolve()  # noqa: F821  — PyInstaller 注入 SPECPATH

datas: list = []
binaries: list = []
hiddenimports: list = [
    "qasync",
    # 本项目模块（显式列出，避免漏打包）
    "app_paths",
    "bp_protocol",
    "device_profile",
    "gateway_config",
    "gateway_controller",
    "hr_ble",
    "hr_ble_backend",
    "measure_fsm",
    "multi_ble_backend",
    "reading_format",
    "ruiguang_bp_pc",
    "tv_link",
    "tv_messages",
    "ui_panels",
    "ble_runner",
]

# ---- 收集第三方库（体积大，但绿色版最稳）----
for pkg in ("bleak", "PySide6", "shiboken6"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception as exc:  # noqa: BLE001
        print(f"[spec] warn: collect_all({pkg}) failed: {exc}", file=sys.stderr)

# winrt：bleak 在 Windows 上常用的后端（不同环境包名可能略有差异）
for pkg in ("winrt", "bleak_winrt"):
    try:
        d, b, h = collect_all(pkg)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

try:
    hiddenimports += collect_submodules("bleak")
except Exception:
    pass

a = Analysis(  # noqa: F821
    [str(SPEC_ROOT / "bp_demo_app.py")],
    pathex=[str(SPEC_ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)  # noqa: F821

exe = EXE(  # noqa: F821
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PCBleGateway",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # False = 无黑色控制台窗口（纯 GUI）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(  # noqa: F821
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="PCBleGateway",
)
