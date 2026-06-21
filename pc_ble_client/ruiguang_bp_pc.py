# -*- coding: utf-8 -*-
"""
命令行入口：扫描或执行一次完整测量（逻辑在 bp_protocol.RuiguangBpSession）。
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import List

from bleak import BleakScanner
from bleak.backends.device import BLEDevice

from bp_protocol import RuiguangBpSession


async def scan_devices(timeout: float) -> List[BLEDevice]:
    print(f"正在扫描 BLE 设备，{timeout} 秒…", flush=True)
    devices = await BleakScanner.discover(timeout=timeout)
    for d in devices:
        name = d.name or "(无广播名)"
        print(f"  {d.address}  {name}", flush=True)
    return list(devices)


def main() -> None:
    parser = argparse.ArgumentParser(description="电脑端连接瑞光康泰协议蓝牙血压计")
    parser.add_argument("--address", help="血压计蓝牙 MAC 地址")
    parser.add_argument("--scan-only", action="store_true", help="只扫描并列出设备")
    parser.add_argument("--scan-time", type=float, default=8.0, help="扫描时长（秒）")
    parser.add_argument("--force", action="store_true", help="忽略电量门限")
    parser.add_argument("--device-type-9000", action="store_true", help="TYPE_9000 机型")
    args = parser.parse_args()

    if args.scan_only or not args.address:
        asyncio.run(scan_devices(args.scan_time))
        if not args.address:
            print("请带上 --address 再次运行以连接指定设备。", flush=True)
        return

    def log(msg: str) -> None:
        print(msg, flush=True)

    def on_pressure(v: int) -> None:
        print(f"实时压力约: {v} mmHg", flush=True)

    async def _run() -> None:
        session = RuiguangBpSession(
            args.address,
            force_measure=args.force,
            device_type_9000=args.device_type_9000,
            on_pressure=on_pressure,
            on_log=log,
        )
        await session.run()

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("已取消", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"运行出错: {e}", file=sys.stderr, flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
