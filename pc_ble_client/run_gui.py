# -*- coding: utf-8 -*-
"""
用「当前这条命令所用的 Python」安装依赖并启动图形界面。

初学者说明：双击 .bat 时，PATH 里的 `python` 可能指向 Anaconda / 官方 Python 等。
若该环境没有 pip 或版本过旧，本脚本会提示你换用别的解释器，而不是去「降级 Python」。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def pip_available() -> bool:
    """检查当前解释器能否执行 `python -m pip`（Anaconda 损坏时常出现 No module named pip）。"""
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        return r.returncode == 0
    except OSError:
        return False


def print_pip_missing_help() -> None:
    """当 pip 不可用时，打印可操作的中文说明。"""
    print()
    print("========== 说明 ==========")
    print("当前解释器里没有可用的 pip（常见于 Anaconda 的 base 环境被弄坏）。")
    print("不需要把 Python「降到更低版本」；需要的是换一个带 pip 的 Python，或修好 conda。")
    print()
    print("请任选一种方式：")
    print("  1) 在本目录打开 cmd，执行（推荐，用系统里已装的 3.12）：")
    print("       py -3.12 run_gui.py")
    print("  2) 若你本机有独立安装的 Python 3.12，用完整路径，例如：")
    print('       "B:\\python3.12\\python.exe" run_gui.py')
    print("  3) 若必须用当前 Anaconda：打开「Anaconda Prompt」执行：")
    print("       conda install -y pip")
    print("     或：python -m ensurepip --upgrade")
    print("========== ==========")


def main() -> int:
    root = Path(__file__).resolve().parent
    req = root / "requirements.txt"
    app = root / "bp_demo_app.py"

    print("当前使用的 Python 路径:", sys.executable)
    print("版本信息:", sys.version.split()[0])

    # PySide6 / 新版 bleak 建议 3.10+；3.8 仍可能跑但容易与依赖不兼容，仅作提示
    if sys.version_info < (3, 10):
        print("提示: 建议使用 Python 3.10 及以上运行本测试端（官方 PySide6 轮子更全）。")

    if not pip_available():
        print("错误: 当前 Python 无法执行 -m pip（没有 pip 模块）。")
        print_pip_missing_help()
        return 1

    pip_cmd = [
        sys.executable,
        "-m",
        "pip",
        "install",
        "-r",
        str(req),
    ]
    print("正在执行:", " ".join(pip_cmd))
    r = subprocess.call(pip_cmd)
    if r != 0:
        print("pip 安装依赖失败，请把完整报错复制给开发者。")
        return r

    run_cmd = [sys.executable, str(app), *sys.argv[1:]]
    print("正在启动界面:", " ".join(run_cmd))
    return subprocess.call(run_cmd, cwd=str(root))


if __name__ == "__main__":
    raise SystemExit(main())
