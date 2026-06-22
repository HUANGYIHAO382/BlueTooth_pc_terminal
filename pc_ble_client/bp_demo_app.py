# -*- coding: utf-8 -*-
"""
多路 BLE 测试端（桌面 GUI）—— 四区分层重构版。

四个区域（见 ui_panels.py）：
  区域1 设备池   DevicePoolPanel : 扫描 / 过滤 / 列表（状态标签 + 右键设类型）
  区域2 会话     SessionPanel    : 当前连接（只读：名称/MAC/角色/类型/状态 + 断开）
  区域3 功能面板 FunctionPanel   : 连接设置 Tab + 业务操作 Tab（按设备类型切换 HR/BP）
  区域4 底部栏   GlobalBar       : 全局按钮 + TV 推送配置

核心思想：
  - 分层管理：把「蓝牙连接」与「业务操作（测血压/看心率）」彻底分开。
  - 设备档案：device_profile.DeviceProfileStore 记住每台 MAC 的类型/角色，
    扫描即标记「已配置/未知/已连接」，连接按档案 type 路由（band→心率，bp→血压）。
  - TV 联动：tv_link.TvLink 用 JSON over UDP 与 TV 双向通信；联动模式下血压测量
    走「连接→发 READY→等 TV 的 START→测量→回推 RESULT」。

技术栈：Python 3.10+ / PySide6 / qasync（Qt 与 asyncio 合并事件循环）。
"""

from __future__ import annotations

import argparse
import asyncio
import traceback
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, Qt, QSettings, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from qasync import QEventLoop, asyncSlot

from bp_protocol import (
    device_name_matches_legacy_android_demo,
    sort_rows_bp_name_candidates_first,
)
from device_profile import (
    DeviceProfile,
    DeviceProfileStore,
    TYPE_BAND,
    TYPE_BP,
    TYPE_SCALE,
    norm_mac,
    type_label,
)
from gateway_config import GatewayConfigStore, detect_lan_ip
from gateway_controller import GatewayController
from multi_ble_backend import MultiBleBackend
from reading_format import format_bp_result
from tv_link import TvLink
from ui_panels import (
    DevicePoolPanel,
    FunctionPanel,
    GlobalBar,
    LogTabsWidget,
    ProfileEditDialog,
    SessionPanel,
)


class SignalBridge(QObject):
    """bleak 回调 → Qt 界面的信号桥。"""

    log_line = Signal(str)
    status = Signal(str)
    pressure_mmhg = Signal(int)
    heart_rate = Signal(str, int)               # (mac, bpm)
    connect_finished = Signal(bool, str)         # (成功, MAC 或错误说明)
    disconnect_finished = Signal()
    measure_finished = Signal(bool, str)
    measurement_result = Signal(str, int, int, int)  # (mac, sys, dia, pulse)
    bp_session_changed = Signal(str, bool)  # (mac, connected)


class MainWindow(QMainWindow):
    """主窗口：组装四区面板，接线后端 / 档案 / TV 联动。"""

    def __init__(self, cli_overrides: Optional[dict] = None) -> None:
        super().__init__()
        self._cli = cli_overrides or {}
        self.setWindowTitle("多路 BLE 测试端（设备档案 + 四区布局 + TV 联动）")
        self.resize(1240, 820)

        self._settings = QSettings("RuiguangBpTest", "PcBleClient")
        self._store = DeviceProfileStore()
        self._gw_store = GatewayConfigStore()
        self._apply_cli_to_gateway()

        self._bridge = SignalBridge()
        self._backend = MultiBleBackend(self._bridge)
        self._tv = TvLink(
            on_log=lambda m: self._bridge.log_line.emit(m),
            on_protocol_log=self._append_protocol_log,
        )
        self._gateway = GatewayController(
            self._gw_store,
            self._tv,
            self._backend,
            on_run_log=self._append_log_raw,
            on_protocol_log=self._append_protocol_log,
            on_status=self._set_status,
        )

        # 运行态标志
        self._scan_busy = False
        self._connect_busy = False
        self._batch_probe_busy = False
        self._measuring = False
        self._hr_push_enabled = False
        self._bp_push_enabled = False
        # 预连接池总开关：默认开启——只要设备在池里(auto_connect=True)，扫描到就自动连
        self._auto_connect = True

        self._scan_names: Dict[str, str] = {}
        self._conn_source: Dict[str, str] = {}

        self._build_ui()
        self._gateway.apply_ui_to_bar(self.bar)
        self._update_window_title()
        self._wire_bridge()
        self._wire_panels()

        # 自动刷新定时器（与 HeartRateMonitor DevCtrl 一致：10s 再扫一次）
        self._auto_refresh_timer = QTimer(self)
        self._auto_refresh_timer.setInterval(10000)
        self._auto_refresh_timer.timeout.connect(self._on_auto_refresh_tick)

        # 自动断开定时器
        self._disconnect_timer = QTimer(self)
        self._disconnect_timer.setSingleShot(True)
        self._disconnect_timer.timeout.connect(self._on_disconnect_all)

        self._append_log("已启动（qasync）。默认协议：P0 双信道（A=18500 遥测，B=18501 测压闭环）。")
        self._append_log("启动后将自动 bind 18500+18501 并发送 SCRIPT_READY（listen_port=18501）。")
        QTimer.singleShot(800, self._on_refresh_clicked)
        QTimer.singleShot(1200, self._auto_start_gateway)

    @asyncSlot()
    async def _auto_start_gateway(self) -> None:
        """P0 默认开机即网关：双信道 + SCRIPT_READY。"""
        if not self._gw_store.config.auto_start_gateway:
            return
        ok = await self._gateway.ensure_tv()
        self.bar.set_channel_b_status(self._tv.is_channel_b_running)
        if ok:
            c = self._gw_store.config
            self._append_log(
                f"[TV] 网关已启动 P0：A={c.port_a} B={c.port_b} "
                f"script_ip={c.effective_script_ip()}"
            )
        else:
            self._append_log("[TV] 自动启动网关失败，请检查端口占用或防火墙。")

    def _apply_cli_to_gateway(self) -> None:
        """命令行参数覆盖 gateway.json。"""
        c = self._gw_store.config
        if self._cli.get("emulator"):
            c.protocol_stage = "P0"
            c.tv_unicast_ip = "127.0.0.1"
            c.no_broadcast = True
            c.script_ip = "10.0.2.2"
            c.text_mode = False
            c.json_mode = True
        if self._cli.get("protocol_stage"):
            c.protocol_stage = self._cli["protocol_stage"]
        if self._cli.get("tv_unicast_ip"):
            c.tv_unicast_ip = self._cli["tv_unicast_ip"]
            c.tv_mode = "unicast"
        if self._cli.get("tv_ip"):
            c.tv_ip = self._cli["tv_ip"]
        if self._cli.get("no_broadcast"):
            c.no_broadcast = True
        if self._cli.get("script_ip"):
            c.script_ip = self._cli["script_ip"]
        self._gw_store.save()

    def _update_window_title(self) -> None:
        self.setWindowTitle(
            "多路 BLE 网关测试端 — " + self._gateway.version_title_suffix()
        )

    # ──────────────────────────────────────────────────────────────
    # UI 组装
    # ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        # 上下分隔：上=三列面板，下=运行日志
        main_split = QSplitter(Qt.Vertical)
        root.addWidget(main_split, stretch=1)

        # 顶部三列（区域1/2/3）
        top_split = QSplitter(Qt.Horizontal)
        self.pool = DevicePoolPanel()
        self.session = SessionPanel()
        self.func = FunctionPanel()
        top_split.addWidget(self.pool)
        top_split.addWidget(self.session)
        top_split.addWidget(self.func)
        top_split.setStretchFactor(0, 30)
        top_split.setStretchFactor(1, 25)
        top_split.setStretchFactor(2, 45)
        top_split.setSizes([360, 300, 540])
        main_split.addWidget(top_split)

        # 运行日志（分 Tab）
        self.log_panel = LogTabsWidget()
        main_split.addWidget(self.log_panel)
        main_split.setStretchFactor(0, 3)
        main_split.setStretchFactor(1, 1)

        # 区域4：底部栏
        self.bar = GlobalBar()
        root.addWidget(self.bar, stretch=0)

        sb = QStatusBar()
        self.setStatusBar(sb)
        self._status_label = QLabel("就绪")
        sb.addPermanentWidget(self._status_label, stretch=1)

    # ──────────────────────────────────────────────────────────────
    # 信号接线
    # ──────────────────────────────────────────────────────────────

    def _wire_bridge(self) -> None:
        self._bridge.log_line.connect(self._append_log)
        self._bridge.status.connect(self._set_status)
        self._bridge.pressure_mmhg.connect(self._on_bp_pressure)
        self._bridge.heart_rate.connect(self._on_heart_rate)
        self._bridge.connect_finished.connect(self._on_connect_finished)
        self._bridge.disconnect_finished.connect(lambda: self._refresh_sessions_ui())
        self._bridge.measure_finished.connect(self._on_measure_finished)
        self._bridge.measurement_result.connect(self._on_measurement_result)
        self._bridge.bp_session_changed.connect(self._on_bp_session_changed)

    def _on_bp_session_changed(self, mac: str, connected: bool) -> None:
        """血压计连接/断开时同步 TV 网关与界面会话表。"""
        name = self._scan_names.get(norm_mac(mac), "")
        if connected:
            asyncio.create_task(self._gateway.on_bp_connected(mac, name))
        else:
            asyncio.create_task(self._gateway.on_bp_disconnected(mac))
            self._set_status(f"血压计已断开: {mac}")
        # 意外断开（休眠等）也会走此信号，必须刷新区域2
        self._refresh_sessions_ui()

    def _wire_panels(self) -> None:
        # 区域1 设备池
        self.pool.refresh_requested.connect(self._on_refresh_clicked)
        self.pool.auto_refresh_toggled.connect(self._on_auto_refresh_toggled)
        self.pool.auto_connect_toggled.connect(self._on_auto_connect_toggled)
        self.pool.batch_probe_requested.connect(self._on_batch_probe_clicked)
        self.pool.connect_mac_requested.connect(self._on_connect_mac)
        self.pool.set_type_requested.connect(self._on_set_type)
        self.pool.remove_profile_requested.connect(self._on_remove_profile)
        self.pool.edit_profile_requested.connect(self._on_edit_profile)

        # 区域2 会话
        self.session.session_selected.connect(self._on_session_selected)
        self.session.disconnect_requested.connect(self._on_disconnect_mac)
        self.session.disconnect_all_requested.connect(self._on_disconnect_all)

        # 区域3 功能面板
        self.func.keepalive_toggled.connect(self._on_keepalive_toggled)
        self.func.keepalive_interval_changed.connect(self._on_keepalive_interval_changed)
        self.func.hr_push_toggled.connect(self._on_hr_push_toggled)
        self.func.bp_push_toggled.connect(self._on_bp_push_toggled)
        self.func.bp_start_measure.connect(self._on_full_measure)
        self.func.bp_cmd_connect.connect(self._on_cmd_connect)
        self.func.bp_cmd_power.connect(self._on_cmd_power)
        self.func.bp_cmd_start.connect(self._on_cmd_start)
        self.func.bp_cmd_stop.connect(self._on_cmd_stop)
        self.func.bp_start_wait_stop.connect(self._on_start_wait_stop)

        # 区域3 预连接池管理 Tab
        pm = self.func.pool_manager
        pm.auto_connect_changed.connect(self._on_pool_auto_connect_changed)
        pm.edit_requested.connect(self._on_edit_profile)
        pm.remove_requested.connect(self._on_remove_profile)
        pm.import_requested.connect(self._on_import_profiles)
        pm.export_requested.connect(self._on_export_profiles)
        pm.save_requested.connect(self._on_save_pool)

        # 区域4 底部栏
        self.bar.refresh_requested.connect(self._on_refresh_clicked)
        self.bar.clear_log_requested.connect(self.log_panel.clear_all)
        self.bar.save_log_requested.connect(self._on_save_log)
        self.bar.save_pool_requested.connect(self._on_save_pool)
        self.bar.tv_test_requested.connect(self._on_tv_test)
        self.bar.tv_linkage_toggled.connect(self._on_tv_linkage_toggled)
        self.bar.tv_config_changed.connect(self._on_tv_config_changed)
        self.bar.detect_script_ip_requested.connect(self._on_detect_script_ip)

        td = self.func.tv_debug
        td.send_script_ready_requested.connect(self._on_send_script_ready)
        td.simulate_start_requested.connect(lambda: self._gateway.simulate_start(use_p0=False))
        td.simulate_start_measure_requested.connect(
            lambda: self._gateway.simulate_start(use_p0=True)
        )

        # 初始化预连接池视图（管理表 + 计数）
        self._refresh_pool_views()

        # 恢复保活设置
        try:
            self.func.chk_keepalive.setChecked(int(self._settings.value("keepalive_power/enabled", 0)) != 0)
            self.func.spin_keepalive_interval.setValue(int(self._settings.value("keepalive_power/seconds", 5)))
        except (TypeError, ValueError):
            pass

    # ──────────────────────────────────────────────────────────────
    # 日志 / 状态
    # ──────────────────────────────────────────────────────────────

    def _append_log_raw(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_panel.append_run(f"[{ts}] {text}")

    def _append_log(self, text: str) -> None:
        self._append_log_raw(text)
        if "FFF1:" in text or "写入 FFF2" in text:
            self.log_panel.append_ble(text)

    def _append_protocol_log(self, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_panel.append_tv(f"[{ts}] {text}")
        self.func.tv_debug.append_outbound(text)

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    # ──────────────────────────────────────────────────────────────
    # 扫描
    # ──────────────────────────────────────────────────────────────

    @asyncSlot()
    async def _on_refresh_clicked(self) -> None:
        if self._batch_probe_busy:
            self._append_log("批量探测进行中，已忽略本次扫描。")
            return
        if self._connect_busy:
            self._append_log("正在连接设备，已忽略本次扫描（避免 WinRT 扫描与连接冲突）。")
            return
        if self._scan_busy:
            return
        self._scan_busy = True
        self.pool.btn_refresh.setText("扫描中…")
        sec = float(self.pool.spin_scan_seconds.value())
        self._set_status(f"正在扫描 BLE（约 {sec:.0f} 秒）…")
        try:
            rows = await self._backend.scan_devices(sec, self.pool.chk_filter_noname.isChecked())
            self._on_scan_finished(rows)
        except OSError as e:
            werr = getattr(e, "winerror", None)
            if werr == -2147020577:
                self._append_log("蓝牙未开启或不可用，请在 Windows 设置中打开蓝牙。")
                QMessageBox.warning(self, "错误", "蓝牙未开启或不可用，请打开蓝牙后再扫描。")
            else:
                self._append_log(f"扫描失败(OSError): {e!r}\n{traceback.format_exc()}")
                self._set_status("扫描失败")
        except Exception as e:  # noqa: BLE001
            self._append_log(f"扫描失败: {e!r}\n{traceback.format_exc()}")
            self._set_status("扫描失败")
        finally:
            self._scan_busy = False
            self.pool.btn_refresh.setText("刷新")

    def _on_scan_finished(self, rows: object) -> None:
        assert isinstance(rows, list)
        raw_list: List[Tuple[str, str]] = [(str(t[0]), str(t[1])) for t in rows]

        if self.pool.chk_legacy_name_only.isChecked():
            before = len(raw_list)
            raw_list = [it for it in raw_list if device_name_matches_legacy_android_demo(it[0])]
            self._append_log(f"[旧版名称规则] 仅保留含 RBP/BP：{before} -> {len(raw_list)} 台")
        if self.pool.chk_legacy_sort_top.isChecked():
            raw_list = sort_rows_bp_name_candidates_first(raw_list)

        # 记录 MAC->名称
        for name, mac in raw_list:
            self._scan_names[norm_mac(mac)] = name

        connected = {m for m, _k, ok in self._backend.list_sessions_summary() if ok}
        self.pool.set_devices(raw_list, self._store.get, connected)

        pr = self._backend.last_scan_seconds_per_round
        self._append_log(
            f"找到 {len(raw_list)} 个设备（最近一轮约 {pr:.1f} 秒；{self._backend.last_scan_note or '—'}）"
        )
        self._set_status(f"扫描完成，共 {len(raw_list)} 个设备")

        if not raw_list and self.pool.chk_filter_noname.isChecked():
            self._append_log("列表为空且勾选了「过滤无名设备」：血压计常无广播名，建议取消勾选后重扫。")

        # 预连接池：连接所有 auto_connect=True 且未连接的已配置设备
        pending: List[str] = []
        for _name, mac in raw_list:
            prof = self._store.get(mac)
            if (
                prof and prof.auto_connect
                and prof.type != TYPE_SCALE
                and norm_mac(mac) not in connected
            ):
                pending.append(mac)
        if pending:
            if not self._auto_connect:
                # 命中了池内设备，但总开关被手动关掉——给出提示，避免误以为没生效
                self._append_log(
                    f"[预连接池] 命中 {len(pending)} 台池内设备，但「自动连接」总开关已关闭，未自动连接。"
                )
            elif self._connect_busy:
                self._append_log("[预连接池] 正在连接其它设备，稍后再自动连接池内设备。")
            else:
                names = ", ".join(pending)
                self._append_log(f"[预连接池] 命中 {len(pending)} 台待自动连接：{names}")
                asyncio.create_task(self._run_auto_connect(pending))

    def _on_auto_refresh_toggled(self, on: bool) -> None:
        if on:
            self._on_refresh_clicked()
            self._auto_refresh_timer.start()
        else:
            self._auto_refresh_timer.stop()

    def _on_auto_connect_toggled(self, on: bool) -> None:
        self._auto_connect = on

    def _on_auto_refresh_tick(self) -> None:
        if (
            self.pool.chk_auto_refresh.isChecked()
            and not self._scan_busy
            and not self._batch_probe_busy
            and not self._connect_busy
        ):
            self._on_refresh_clicked()

    # ──────────────────────────────────────────────────────────────
    # 设备档案：设类型 / 移除
    # ──────────────────────────────────────────────────────────────

    def _on_set_type(self, mac: str, type_: str) -> None:
        name = self._scan_names.get(norm_mac(mac), "")
        # 快速设类型默认开启预连接（auto_connect），与「加入预连接池」语义一致
        p = self._store.set_type(mac, type_, name=name)
        p.auto_connect = True
        self._store.save()
        self._append_log(f"已将 {mac} 配置为「{type_label(type_)}」并加入预连接池。")
        self._refresh_pool_views()

    def _on_remove_profile(self, mac: str) -> None:
        if self._store.remove(mac):
            self._append_log(f"已移除 {mac} 的预连接配置。")
        self._refresh_pool_views()

    def _on_edit_profile(self, mac: str) -> None:
        """打开「加入/编辑预连接池」对话框。"""
        mac = norm_mac(mac)
        name = self._scan_names.get(mac, "")
        prof = self._store.get(mac)
        dlg = ProfileEditDialog(mac, name=name, profile=prof, parent=self)
        if dlg.exec() == dlg.DialogCode.Accepted:
            self._store.upsert(dlg.result_profile())
            self._append_log(f"已保存 {mac} 的预连接配置。")
            self._refresh_pool_views()

    def _on_pool_auto_connect_changed(self, mac: str, value: bool) -> None:
        self._store.set_auto_connect(mac, value)
        self._append_log(f"{mac} 预连接已{'开启' if value else '关闭'}。")
        # 仅刷新池标签与计数（不重建管理表，避免打断用户勾选）
        self._refresh_pool_labels()
        self.bar.set_pool_count(self._store.auto_connect_count())

    def _on_import_profiles(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入预连接配置", "", "JSON 文件 (*.json)")
        if not path:
            return
        try:
            n = self._store.import_from(path, merge=True)
            self._append_log(f"已从 {path} 导入 {n} 条配置（合并）。")
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "导入失败", str(e))
            return
        self._refresh_pool_views()

    def _on_export_profiles(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "导出预连接配置", "devices_backup.json", "JSON 文件 (*.json)")
        if not path:
            return
        try:
            self._store.export_to(path)
            self._append_log(f"已导出预连接配置到 {path}。")
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))

    def _on_save_pool(self) -> None:
        self._store.save()
        self._append_log(f"已保存预连接配置到 {self._store.path}")
        self._refresh_pool_views()

    def _refresh_pool_labels(self) -> None:
        """用最近一次扫描名重画设备池（仅更新标签，不重新扫描）。"""
        rows = [(self._scan_names.get(norm_mac(m), n), m)
                for n, m in self._current_pool_rows()]
        connected = {m for m, _k, ok in self._backend.list_sessions_summary() if ok}
        self.pool.set_devices(rows, self._store.get, connected)

    def _refresh_pool_views(self) -> None:
        """统一刷新：设备池标签 + 预连接池管理表 + 底部计数。"""
        self._refresh_pool_labels()
        self.func.pool_manager.set_profiles(self._store.all())
        self.bar.set_pool_count(self._store.auto_connect_count())

    def _current_pool_rows(self) -> List[Tuple[str, str]]:
        out: List[Tuple[str, str]] = []
        for i in range(self.pool.list_devices.count()):
            it = self.pool.list_devices.item(i)
            mac = str(it.data(Qt.UserRole) or "")
            if mac:
                out.append((self._scan_names.get(norm_mac(mac), ""), mac))
        return out

    # ──────────────────────────────────────────────────────────────
    # 连接 / 断开（按档案 type 路由）
    # ──────────────────────────────────────────────────────────────

    def _resolve_type(self, mac: str) -> str:
        """决定连接类型：优先档案 type，否则用设备池「默认角色」。"""
        prof = self._store.get(mac)
        if prof is not None:
            return prof.type
        return self.pool.default_type()

    @asyncSlot(str)
    async def _on_connect_mac(self, mac: str) -> None:
        """界面发起的手动连接。"""
        await self._do_connect(mac, source="手动", interactive=True)

    @asyncSlot(str)
    async def _auto_connect_mac(self, mac: str) -> None:
        """预连接池自动连接（不弹窗）。"""
        await self._do_connect(mac, source="预连接池", interactive=False)

    async def _run_auto_connect(self, macs: List[str]) -> None:
        """按顺序自动连接多台预连接池设备（避免 WinRT 并发连接冲突）。"""
        for mac in macs:
            if norm_mac(mac) in {m for m, _k, ok in self._backend.list_sessions_summary() if ok}:
                continue
            await self._do_connect(mac, source="预连接池", interactive=False)
            await asyncio.sleep(0.5)

    async def _do_connect(self, mac: str, *, source: str, interactive: bool) -> None:
        mac = norm_mac(mac)
        if not mac or mac.count(":") != 5:
            if interactive:
                QMessageBox.warning(self, "提示", "MAC 格式应为 AA:BB:CC:DD:EE:FF。")
            return
        if self._batch_probe_busy:
            if interactive:
                QMessageBox.warning(self, "提示", "正在批量探测，请稍后再连接。")
            return

        type_ = self._resolve_type(mac)
        if type_ == TYPE_SCALE:
            if interactive:
                QMessageBox.information(self, "暂未实现", "体脂秤（scale）类型尚未实现连接逻辑。")
            return

        # 手环不做系统配对；血压计按勾选
        pair = self.func.chk_pair.isChecked() and type_ == TYPE_BP
        self._last_connect_interactive = interactive
        self._set_status(f"正在连接 {mac}（{type_label(type_)}，{source}）…")
        self._connect_busy = True
        auto_was_on = self._auto_refresh_timer.isActive()
        if auto_was_on:
            self._auto_refresh_timer.stop()
        try:
            if type_ == TYPE_BAND:
                await self._backend.connect_hr(mac, pair)
            else:
                await self._backend.connect_bp(mac, pair)
            # 连接成功：回写档案（含 last_connected）；若无档案则按本次 type 建档
            name = self._scan_names.get(mac, "")
            if self._store.get(mac) is None:
                self._store.set_type(mac, type_, name=name)
            self._store.mark_connected(mac, name)
            self._conn_source[mac] = source
            self._refresh_pool_views()
            self._bridge.connect_finished.emit(True, mac)
        except Exception as e:  # noqa: BLE001
            self._bridge.connect_finished.emit(False, str(e))
        finally:
            self._connect_busy = False
            if auto_was_on and self.pool.chk_auto_refresh.isChecked():
                self._auto_refresh_timer.start()

    def _on_connect_finished(self, ok: bool, msg: str) -> None:
        if ok:
            self._append_log(f"连接成功: {msg}")
            self._set_status(f"已连接: {msg}")
            self._refresh_sessions_ui()
            self._schedule_disconnect_if_needed()
            self._maybe_start_keepalive()
        else:
            self._append_log(f"连接失败:\n{msg}")
            self._set_status("连接失败")
            if getattr(self, "_last_connect_interactive", True):
                QMessageBox.critical(self, "连接失败", msg)

    @asyncSlot(str)
    async def _on_disconnect_mac(self, mac: str) -> None:
        self._disconnect_timer.stop()
        try:
            await self._backend.disconnect_address(mac)
        except Exception as e:  # noqa: BLE001
            self._append_log(f"断开异常: {e!r}")
        self._refresh_sessions_ui()

    @asyncSlot()
    async def _on_disconnect_all(self) -> None:
        self._disconnect_timer.stop()
        try:
            await self._backend.disconnect_all()
        except Exception as e:  # noqa: BLE001
            self._append_log(f"断开全部异常: {e!r}")
        self._refresh_sessions_ui()

    def _refresh_sessions_ui(self) -> None:
        summary = self._backend.list_sessions_summary()
        self.session.set_sessions(summary, self._store.get, self._source_get)
        # 同步设备池里的「已连接」标签
        self._refresh_pool_labels()
        # 若当前没有任何会话，功能面板回到空页
        if not summary:
            self.func.show_empty()

    def _source_get(self, mac: str) -> str:
        """返回某 MAC 的连接来源（默认「手动」）。"""
        return self._conn_source.get(norm_mac(mac), "手动")

    def _on_session_selected(self, mac: str, type_: str) -> None:
        """选中会话→切换功能面板；若是 BP 则设为透传目标。"""
        self.func.show_for_type(type_)
        if type_ == TYPE_BP:
            self._backend.active_bp_address = norm_mac(mac)

    # ──────────────────────────────────────────────────────────────
    # 心率 / 血压结果回调
    # ──────────────────────────────────────────────────────────────

    def _on_heart_rate(self, mac: str, bpm: int) -> None:
        line, _reading = self._gateway.on_heart_rate(mac, bpm)
        self.func.set_hr(bpm)
        self.func.append_hr_log(line)
        self._append_log_raw(line.split("] ", 1)[-1] if "] " in line else line)

    def _on_bp_pressure(self, mmhg: int) -> None:
        mac = self._backend.active_bp_address or ""
        line = self._gateway.on_bp_pressure(mmhg, mac=mac)
        if line is None:
            return
        self.func.set_bp_pressure(mmhg)
        self.func.append_bp_log(line)

    def _on_measurement_result(self, mac: str, sys_: int, dia_: int, pulse: int) -> None:
        line = self._gateway.on_measurement_result(mac, sys_, dia_, pulse)
        self.func.set_bp_result(sys_, dia_, pulse)
        self.func.append_bp_log(line)
        self._append_log_raw(format_bp_result(sys_, dia_, pulse))

    # ──────────────────────────────────────────────────────────────
    # 血压测量（分步 + 一键 + TV 联动）
    # ──────────────────────────────────────────────────────────────

    @asyncSlot()
    async def _on_cmd_connect(self) -> None:
        await self._safe_cmd(self._backend.send_connect_command, "已发送连接指令。")

    @asyncSlot()
    async def _on_cmd_power(self) -> None:
        await self._safe_cmd(self._backend.send_query_power, "已发送查询电量指令。")

    @asyncSlot()
    async def _on_cmd_start(self) -> None:
        await self._safe_cmd(self._backend.send_start_measurement, "已发送启动测量指令。")

    @asyncSlot()
    async def _on_cmd_stop(self) -> None:
        await self._safe_cmd(self._backend.send_stop, "已发送停止测量指令。")

    async def _safe_cmd(self, coro_func, ok_msg: str) -> None:
        try:
            await coro_func()
            self._append_log(ok_msg)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "指令失败", str(e))

    @asyncSlot()
    async def _on_start_wait_stop(self) -> None:
        self.func.bp.set_busy(True)
        try:
            await self._backend.run_start_wait_stop_only()
            self._bridge.measure_finished.emit(True, "「启动并等待」流程结束。")
        except Exception as e:  # noqa: BLE001
            self._bridge.measure_finished.emit(False, str(e))
        finally:
            self.func.bp.set_busy(False)

    @asyncSlot()
    async def _on_full_measure(self) -> None:
        """开始测量：经 GatewayController + MeasureFsm 统一入口。"""
        if self._measuring:
            return
        self._measuring = True
        self.func.bp.set_busy(True)
        force = self.func.bp.is_force()
        d9 = self.func.bp.is_type9000()
        self._gateway.linkage_enabled = self.bar.is_linkage_on()
        self._gateway.bp_push_enabled = self._bp_push_enabled
        try:
            if self.bar.is_linkage_on():
                self.func.set_tv_status("等待 TV 授权…", waiting=True)
            active = self._backend.active_bp_address or ""
            name = self._scan_names.get(active, "")
            ok, msg = await self._gateway.run_full_measure(
                force=force,
                device_type_9000=d9,
                active_mac=active,
                device_name=name,
            )
            self._bridge.measure_finished.emit(ok, msg)
            if ok and self.bar.is_linkage_on():
                self.func.set_tv_status("TV 联动：已启用", active=True)
        except Exception as e:  # noqa: BLE001
            self._bridge.measure_finished.emit(False, str(e))
        finally:
            self._measuring = False
            self.func.bp.set_busy(False)
            if self.bar.is_linkage_on():
                self.func.set_tv_status("TV 联动：已启用（等待下次触发）", active=True)

    def _on_measure_finished(self, ok: bool, msg: str) -> None:
        if ok:
            self._append_log(msg)
        else:
            self._append_log(f"测量流程异常: {msg}")
            QMessageBox.warning(self, "测量", msg)
        self._schedule_disconnect_if_needed()

    # ──────────────────────────────────────────────────────────────
    # 批量探测「无广播名」FFF0
    # ──────────────────────────────────────────────────────────────

    @asyncSlot()
    async def _on_batch_probe_clicked(self) -> None:
        if self._batch_probe_busy or self._scan_busy:
            QMessageBox.warning(self, "提示", "当前正在扫描/探测，请稍后再试。")
            return
        addrs = self.pool.device_macs_with_marker("(无广播名)")
        if not addrs:
            QMessageBox.information(self, "批量探测", "当前列表无「(无广播名)」条目。请先扫描并取消「过滤无名设备」。")
            return
        self._batch_probe_busy = True
        await self._backend.disconnect_all()
        self._refresh_sessions_ui()
        self._append_log(f"===== 开始批量探测 {len(addrs)} 台「无广播名」设备（检测 FFF0）=====")
        hits: List[str] = []
        pair = self.func.chk_pair.isChecked()
        try:
            for idx, addr in enumerate(addrs, start=1):
                self._set_status(f"批量探测 {idx}/{len(addrs)}: {addr}")
                ok, detail = await self._backend.probe_fff0_service_only(addr, pair)
                if ok:
                    hits.append(addr)
                    self._append_log(f"  [{idx}] 命中 FFF0: {addr} — {detail}")
                    # 命中即自动建/更新为血压计档案
                    self._store.set_type(addr, TYPE_BP, name=self._scan_names.get(norm_mac(addr), ""))
                else:
                    self._append_log(f"  [{idx}] 未命中: {addr} — {detail}")
                await asyncio.sleep(0.8)
        finally:
            self._batch_probe_busy = False
            self._set_status("批量探测结束")
            self._refresh_pool_views()
        if hits:
            QMessageBox.information(self, "批量探测结果",
                                    "发现 FFF0 并已标记为血压计：\n" + "\n".join(hits))
        else:
            QMessageBox.information(self, "批量探测结果", "未发现含 FFF0 的设备。")

    # ──────────────────────────────────────────────────────────────
    # 连接设置（自动断开 / 保活）
    # ──────────────────────────────────────────────────────────────

    def _schedule_disconnect_if_needed(self) -> None:
        sec = int(self.func.spin_auto_disconnect.value())
        self._disconnect_timer.stop()
        if sec > 0:
            self._disconnect_timer.start(sec * 1000)

    def _maybe_start_keepalive(self) -> None:
        if not self.func.chk_keepalive.isChecked():
            return
        addr = self._backend.active_bp_address
        if not addr:
            return
        try:
            loop = asyncio.get_event_loop()
            if not loop.is_running():
                return
        except RuntimeError:
            return
        self._backend.start_power_keepalive_for_session(
            addr, float(self.func.spin_keepalive_interval.value())
        )

    def _on_keepalive_toggled(self, checked: bool) -> None:
        self._settings.setValue("keepalive_power/enabled", 1 if checked else 0)
        if checked:
            self._maybe_start_keepalive()
        else:
            for a in list(self._backend.sessions.keys()):
                self._backend.stop_session_keepalive_fire_and_forget(a)

    def _on_keepalive_interval_changed(self, _value: int) -> None:
        self._settings.setValue("keepalive_power/seconds", int(self.func.spin_keepalive_interval.value()))
        if self.func.chk_keepalive.isChecked():
            self._maybe_start_keepalive()

    # ──────────────────────────────────────────────────────────────
    # TV 联动
    # ──────────────────────────────────────────────────────────────

    def _on_hr_push_toggled(self, on: bool) -> None:
        self._hr_push_enabled = on
        self._gateway.hr_push_enabled = on
        if on:
            self._ensure_tv_fire_and_forget()

    def _on_bp_push_toggled(self, on: bool) -> None:
        self._bp_push_enabled = on
        self._gateway.bp_push_enabled = on
        if on:
            self._ensure_tv_fire_and_forget()

    async def _ensure_tv(self) -> bool:
        self._gateway.sync_config_from_ui(self.bar.get_tv_config())
        ok = await self._gateway.ensure_tv()
        self.bar.set_channel_b_status(self._tv.is_channel_b_running)
        self._update_window_title()
        return ok

    @asyncSlot()
    async def _ensure_tv_fire_and_forget(self) -> None:
        await self._ensure_tv()

    @asyncSlot(bool)
    async def _on_tv_linkage_toggled(self, on: bool) -> None:
        self._gateway.linkage_enabled = on
        if on:
            ok = await self._ensure_tv()
            if ok:
                self.func.set_tv_status("TV 联动：已启用（等待测量触发）", active=True)
                self._append_log("已启用 TV 联动：测量前等待 TV 的 START / START_MEASURE。")
            else:
                self.bar.chk_linkage.setChecked(False)
        else:
            self.func.set_tv_status("TV 联动：未启用")
            self._append_log("已关闭 TV 联动模式。")

    @asyncSlot()
    async def _on_tv_config_changed(self) -> None:
        self._gateway.sync_config_from_ui(self.bar.get_tv_config())
        self._update_window_title()
        if self._tv.is_running:
            await self._ensure_tv()

    @asyncSlot()
    async def _on_tv_test(self) -> None:
        if not await self._ensure_tv():
            return
        self._gateway.send_ping()
        cfg = self.bar.get_tv_config()
        self._append_log(f"[TV] 已发送 PING → {cfg.get('ip')}:{cfg.get('port_a')}")

    @asyncSlot()
    async def _on_send_script_ready(self) -> None:
        if await self._ensure_tv():
            self._gateway.send_script_ready()

    def _on_detect_script_ip(self) -> None:
        ip = detect_lan_ip()
        self.bar.edit_script_ip.setText(ip)
        self._gw_store.config.script_ip = ip
        self._gw_store.save()
        self._append_log(f"已检测 script_ip: {ip}")

    # ──────────────────────────────────────────────────────────────
    # 杂项
    # ──────────────────────────────────────────────────────────────

    def _on_save_log(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "保存日志", "", "文本文件 (*.txt)")
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(self.log_panel.text_run.toPlainText())
        self._append_log(f"已保存: {path}")

    def closeEvent(self, event) -> None:  # noqa: ANN001
        self._auto_refresh_timer.stop()
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self._shutdown())
        except RuntimeError:
            pass
        super().closeEvent(event)

    async def _shutdown(self) -> None:
        try:
            await self._gateway.stop_tv()
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._backend.disconnect_all()
        except Exception:  # noqa: BLE001
            pass


def parse_cli(argv: Optional[List[str]] = None) -> dict:
    """解析命令行，供 run_gui / 直接启动使用。"""
    p = argparse.ArgumentParser(description="PC BLE 网关 GUI")
    p.add_argument("--protocol-stage", choices=["L0", "T0", "P0"], default=None)
    p.add_argument(
        "--emulator",
        action="store_true",
        help="AS 模拟器预设：P0 + 单播 127.0.0.1 + script_ip=10.0.2.2 + 禁用广播",
    )
    p.add_argument("--tv-ip", default=None, help="TV 单播 IP（广播模式下的加固单播）")
    p.add_argument("--tv-unicast-ip", default=None, help="单播目标，模拟器常用 127.0.0.1")
    p.add_argument("--no-broadcast", action="store_true")
    p.add_argument("--script-ip", default=None)
    ns = p.parse_args(argv)
    out: dict = {}
    if ns.emulator:
        out["emulator"] = True
    if ns.protocol_stage:
        out["protocol_stage"] = ns.protocol_stage
    if ns.tv_ip:
        out["tv_ip"] = ns.tv_ip
    if ns.tv_unicast_ip:
        out["tv_unicast_ip"] = ns.tv_unicast_ip
    if ns.no_broadcast:
        out["no_broadcast"] = True
    if ns.script_ip:
        out["script_ip"] = ns.script_ip
    return out


def main(argv: Optional[List[str]] = None) -> None:
    cli = parse_cli(argv)
    app = QApplication([])
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    w = MainWindow(cli_overrides=cli)
    w.show()
    app.lastWindowClosed.connect(loop.stop)
    with loop:
        loop.run_forever()


if __name__ == "__main__":
    main()
