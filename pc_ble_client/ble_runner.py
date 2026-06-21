# -*- coding: utf-8 -*-
"""
（历史）独立线程 asyncio 运行器。

当前「血压计蓝牙测试端」已改为与 HeartRateMonitor 相同：使用 qasync + Qt 主循环跑 bleak，
本模块不再被 bp_demo_app 引用，仅保留文件以免旧链接失效；新代码请使用 qasync。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any, Coroutine, Optional, TypeVar

T = TypeVar("T")


class AsyncioThreadRunner:
    """后台线程 + asyncio 循环，用于执行 bleak 相关协程。"""

    def __init__(self) -> None:
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._ready.clear()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_run, daemon=True, name="BleAsyncLoop")
        self._thread.start()
        if not self._ready.wait(timeout=8.0):
            raise RuntimeError("异步蓝牙线程未能启动")

    def stop(self) -> None:
        if self._loop is None:
            return

        def _stop() -> None:
            self._loop.stop()

        self._loop.call_soon_threadsafe(_stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
        self._loop = None
        self._thread = None

    def submit(self, coro: Coroutine[Any, Any, T], timeout: Optional[float] = None) -> T:
        """在蓝牙线程执行协程并阻塞等待结果（请在 Qt 里用 QThread 或 runInThread 避免卡 UI）。"""
        if self._loop is None:
            raise RuntimeError("AsyncioThreadRunner 未 start()")
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    def submit_async(self, coro: Coroutine[Any, Any, T]) -> concurrent.futures.Future[T]:
        """提交协程，立即返回 Future，适合在界面线程里 future.add_done_callback 更新 UI。"""
        if self._loop is None:
            raise RuntimeError("AsyncioThreadRunner 未 start()")
        return asyncio.run_coroutine_threadsafe(coro, self._loop)

    @property
    def loop(self) -> asyncio.AbstractEventLoop:
        if self._loop is None:
            raise RuntimeError("loop 未就绪")
        return self._loop
