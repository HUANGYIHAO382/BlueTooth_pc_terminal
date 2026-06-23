# -*- coding: utf-8 -*-
"""
四区分层 UI 控件（与主窗口解耦）。

区域划分（参见重构方案）：
- 区域1 DevicePoolPanel  : 设备发现与预连接池（扫描、过滤、列表、右键设类型）
- 区域2 SessionPanel     : 当前连接会话（只读展示：名称/MAC/角色/类型/状态 + 断开）
- 区域3 FunctionPanel    : 动态功能面板（连接设置 Tab + 业务操作 Tab，按设备类型切换）
- 区域4 GlobalBar        : 底部全局栏（全局按钮 + TV 推送配置）

设计原则：
- 每个面板只负责「显示」与「发信号」，不直接碰后端；真正的连接/测量由主窗口接线。
- 面板之间通过 Qt 信号通信，主窗口做总线。
"""

from __future__ import annotations

from typing import Callable, List, Optional, Set, Tuple

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from device_profile import (
    DeviceProfile,
    ROLE_CLIENT,
    ROLE_SERVER,
    TYPE_BAND,
    TYPE_BP,
    TYPE_SCALE,
    norm_mac,
    type_label,
)

# 状态标签颜色（已配置=绿 / 未知=灰 / 已连接=蓝）
_COLOR_CONFIGURED = "#2e7d32"
_COLOR_UNKNOWN = "#888888"
_COLOR_CONNECTED = "#1565c0"
# 预连接池高亮底色（auto_connect=True）
_BG_POOL = "#e3f2fd"  # 浅蓝
_MARK_POOL = "\u2705"  # ✅


# ──────────────────────────────────────────────────────────────────────
# 预连接池：编辑配置对话框
# ──────────────────────────────────────────────────────────────────────

class ProfileEditDialog(QDialog):
    """
    「加入/编辑预连接池」表单：填写 类型 / 角色 / 自动连接 / 备注 / 分组。

    用法::

        dlg = ProfileEditDialog(mac, name, profile, parent)
        if dlg.exec() == QDialog.Accepted:
            p = dlg.result_profile()   # 返回填好的 DeviceProfile
    """

    def __init__(
        self,
        mac: str,
        name: str = "",
        profile: Optional[DeviceProfile] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("预连接配置")
        self._mac = norm_mac(mac)
        form = QFormLayout(self)

        self.edit_name = QLineEdit(profile.name if profile else name)
        form.addRow("名称", self.edit_name)
        form.addRow("MAC", QLabel(self._mac))

        self.combo_type = QComboBox()
        self.combo_type.addItem("心率手环", TYPE_BAND)
        self.combo_type.addItem("血压计", TYPE_BP)
        self.combo_type.addItem("体脂秤（暂未实现）", TYPE_SCALE)
        form.addRow("类型", self.combo_type)

        self.combo_role = QComboBox()
        self.combo_role.addItem("client（PC 为中心）", ROLE_CLIENT)
        self.combo_role.addItem("server（外设）", ROLE_SERVER)
        form.addRow("角色", self.combo_role)

        self.edit_protocol = QLineEdit(profile.protocol if (profile and profile.protocol) else "")
        self.edit_protocol.setPlaceholderText("血压计可填 TYPE_9000，留空即默认")
        form.addRow("协议", self.edit_protocol)

        self.chk_auto = QCheckBox("扫描到时自动连接")
        self.chk_auto.setChecked(profile.auto_connect if profile else True)
        form.addRow("预连接", self.chk_auto)

        self.edit_group = QLineEdit(profile.group if profile else "")
        self.edit_group.setPlaceholderText("如 门诊组 / 家庭组（可空）")
        form.addRow("分组", self.edit_group)

        self.edit_notes = QLineEdit(profile.notes if profile else "")
        self.edit_notes.setPlaceholderText("备注（可空）")
        form.addRow("备注", self.edit_notes)

        # 回填类型/角色当前值
        if profile is not None:
            i = self.combo_type.findData(profile.type)
            if i >= 0:
                self.combo_type.setCurrentIndex(i)
            j = self.combo_role.findData(profile.role)
            if j >= 0:
                self.combo_role.setCurrentIndex(j)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def result_profile(self) -> DeviceProfile:
        return DeviceProfile(
            mac=self._mac,
            name=self.edit_name.text().strip(),
            type=str(self.combo_type.currentData()),
            role=str(self.combo_role.currentData()),
            auto_connect=self.chk_auto.isChecked(),
            protocol=(self.edit_protocol.text().strip() or None),
            group=self.edit_group.text().strip(),
            notes=self.edit_notes.text().strip(),
        )


# ──────────────────────────────────────────────────────────────────────
# 区域1：设备发现与预连接池
# ──────────────────────────────────────────────────────────────────────

class DevicePoolPanel(QGroupBox):
    """
    设备池：扫描 + 过滤 + 列表（带状态标签与右键菜单）。

    信号：
        refresh_requested()           点「刷新」
        auto_refresh_toggled(bool)    勾选/取消「自动刷新」
        auto_connect_toggled(bool)    勾选/取消「自动连接」
        batch_probe_requested()       点「批量探测 FFF0」
        connect_mac_requested(str)    请求连接某 MAC（双击列表 / 「添加连接」/「按地址连接」）
        set_type_requested(str, str)  右键设类型：(mac, type)
        remove_profile_requested(str) 右键移除配置：(mac)
        edit_profile_requested(str)   右键「加入/编辑预连接池…」：(mac)
        pool_changed()                预连接池被本面板改动（刷新计数用）
    """

    refresh_requested = Signal()
    auto_refresh_toggled = Signal(bool)
    auto_connect_toggled = Signal(bool)
    batch_probe_requested = Signal()
    connect_mac_requested = Signal(str)
    set_type_requested = Signal(str, str)
    remove_profile_requested = Signal(str)
    edit_profile_requested = Signal(str)
    pool_changed = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("可用设备（区域1：发现与预连接池）", parent)
        self._connected: Set[str] = set()
        self._profile_get: Callable[[str], Optional[DeviceProfile]] = lambda _m: None

        root = QVBoxLayout(self)
        root.setSpacing(6)

        # 第一行：刷新 / 自动刷新 / 自动连接 / 单次扫描秒数
        row1 = QHBoxLayout()
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_requested)
        row1.addWidget(self.btn_refresh)
        self.chk_auto_refresh = QCheckBox("自动刷新")
        self.chk_auto_refresh.toggled.connect(self.auto_refresh_toggled)
        row1.addWidget(self.chk_auto_refresh)
        self.chk_auto_connect = QCheckBox("自动连接预连接池")
        self.chk_auto_connect.setChecked(True)
        self.chk_auto_connect.setToolTip(
            "总开关（默认开启）：勾选后，凡是在「预连接池」里的设备（管理表里「自动」打勾），\n"
            "一旦扫描到就会自动连接。取消勾选则全部暂停自动连接。"
        )
        self.chk_auto_connect.toggled.connect(self.auto_connect_toggled)
        row1.addWidget(self.chk_auto_connect)
        row1.addStretch()
        row1.addWidget(QLabel("单次扫描"))
        self.spin_scan_seconds = QSpinBox()
        self.spin_scan_seconds.setRange(2, 60)
        self.spin_scan_seconds.setValue(8)
        self.spin_scan_seconds.setSuffix(" 秒")
        row1.addWidget(self.spin_scan_seconds)
        root.addLayout(row1)

        # 第二行：过滤选项
        row2 = QHBoxLayout()
        self.chk_filter_noname = QCheckBox("过滤无名设备")
        self.chk_filter_noname.setToolTip("很多血压计无广播名；找不到设备时请取消勾选。")
        row2.addWidget(self.chk_filter_noname)
        self.chk_legacy_name_only = QCheckBox("仅 RBP/BP")
        self.chk_legacy_name_only.setToolTip("仅保留名称含 RBP 或 BP 的设备（旧 Android Demo 规则）。")
        row2.addWidget(self.chk_legacy_name_only)
        self.chk_legacy_sort_top = QCheckBox("RBP/BP 置顶")
        self.chk_legacy_sort_top.setChecked(True)
        row2.addWidget(self.chk_legacy_sort_top)
        row2.addStretch()
        root.addLayout(row2)

        # 设备列表（双击连接，右键设类型）
        self.list_devices = QListWidget()
        self.list_devices.setMinimumHeight(180)
        self.list_devices.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.list_devices.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list_devices.customContextMenuRequested.connect(self._on_context_menu)
        self.list_devices.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.list_devices.setToolTip(
            "双击=按该设备的「配置档案」类型连接；右键=设为心率手环/血压计或移除配置。\n"
            "未配置的设备请先右键设置类型，或用下方「默认角色」+「添加连接」。"
        )
        root.addWidget(self.list_devices, stretch=1)

        # 第三行：批量探测 + 默认角色（未配置设备的回退）+ 添加连接
        row3 = QHBoxLayout()
        self.btn_batch_probe = QPushButton("批量探测「无广播名」(FFF0)")
        self.btn_batch_probe.clicked.connect(self.batch_probe_requested)
        row3.addWidget(self.btn_batch_probe)
        row3.addStretch()
        row3.addWidget(QLabel("默认角色"))
        self.combo_default_role = QComboBox()
        self.combo_default_role.addItem("心率手环", TYPE_BAND)
        self.combo_default_role.addItem("瑞光血压计", TYPE_BP)
        self.combo_default_role.setToolTip("当设备没有配置档案时，「添加连接/按地址连接」按此角色连接。")
        row3.addWidget(self.combo_default_role)
        self.btn_connect = QPushButton("添加连接")
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        row3.addWidget(self.btn_connect)
        root.addLayout(row3)

        # 第四行：已知 MAC 直连
        row4 = QHBoxLayout()
        self.edit_mac = QLineEdit()
        self.edit_mac.setPlaceholderText("例 AA:BB:CC:DD:EE:FF（扫描不到时手动输入）")
        row4.addWidget(self.edit_mac, stretch=1)
        self.btn_connect_mac = QPushButton("按地址连接")
        self.btn_connect_mac.clicked.connect(self._on_connect_by_mac)
        row4.addWidget(self.btn_connect_mac)
        root.addLayout(row4)

    # ---- 对外方法 ----

    def default_type(self) -> str:
        """返回「默认角色」下拉当前选中的类型代码。"""
        return str(self.combo_default_role.currentData() or TYPE_BAND)

    def selected_mac(self) -> Optional[str]:
        it = self.list_devices.currentItem()
        if it is None:
            return None
        mac = it.data(Qt.UserRole)
        return str(mac) if mac else None

    def set_devices(
        self,
        rows: List[Tuple[str, str]],
        profile_get: Callable[[str], Optional[DeviceProfile]],
        connected: Set[str],
    ) -> None:
        """
        刷新设备列表。

        :param rows: [(显示名, MAC), ...]
        :param profile_get: 按 MAC 查档案的函数
        :param connected: 当前已连接的 MAC 集合
        """
        self._profile_get = profile_get
        self._connected = {m.upper() for m in connected}
        self.list_devices.clear()
        for name, mac in rows:
            up = mac.upper()
            prof = profile_get(mac)
            pooled = bool(prof and prof.auto_connect)  # 预连接池成员
            if up in self._connected:
                tag, color = "已连接", _COLOR_CONNECTED
            elif prof is not None:
                tag, color = f"已配置·{type_label(prof.type)}", _COLOR_CONFIGURED
            else:
                tag, color = "未知", _COLOR_UNKNOWN
            # 预连接池成员加 ✅ 前缀
            prefix = f"{_MARK_POOL} " if pooled else ""
            it = QListWidgetItem(f"{prefix}[{tag}]  {name} ({mac})")
            it.setData(Qt.UserRole, mac)
            it.setForeground(QBrush(QColor(color)))
            # 预连接池成员：浅蓝高亮底色
            if pooled:
                it.setBackground(QBrush(QColor(_BG_POOL)))
            self.list_devices.addItem(it)

    def device_macs_with_marker(self, marker: str) -> List[str]:
        """收集列表里显示文本包含 marker 的 MAC（批量探测「无广播名」用）。"""
        out: List[str] = []
        for i in range(self.list_devices.count()):
            it = self.list_devices.item(i)
            if it is not None and marker in it.text():
                mac = it.data(Qt.UserRole)
                if mac:
                    out.append(str(mac))
        return out

    # ---- 内部交互 ----

    def _on_connect_clicked(self) -> None:
        mac = self.selected_mac()
        if mac:
            self.connect_mac_requested.emit(mac)

    def _on_connect_by_mac(self) -> None:
        mac = self.edit_mac.text().strip().upper().replace("-", ":")
        if mac:
            self.connect_mac_requested.emit(mac)

    def _on_item_double_clicked(self, it: QListWidgetItem) -> None:
        mac = it.data(Qt.UserRole)
        if mac:
            self.connect_mac_requested.emit(str(mac))

    def _on_context_menu(self, pos) -> None:  # noqa: ANN001
        it = self.list_devices.itemAt(pos)
        if it is None:
            return
        mac = str(it.data(Qt.UserRole) or "")
        if not mac:
            return
        prof = self._profile_get(mac)
        menu = QMenu(self)
        act_edit = menu.addAction("加入/编辑预连接池…" if prof is None else "编辑预连接配置…")
        menu.addSeparator()
        act_band = menu.addAction("快速设为心率手环")
        act_bp = menu.addAction("快速设为血压计")
        act_scale = menu.addAction("快速设为体脂秤（暂未实现）")
        menu.addSeparator()
        act_remove = menu.addAction("从预连接池移除")
        act_remove.setEnabled(prof is not None)
        chosen = menu.exec(self.list_devices.mapToGlobal(pos))
        if chosen == act_edit:
            self.edit_profile_requested.emit(mac)
        elif chosen == act_band:
            self.set_type_requested.emit(mac, TYPE_BAND)
        elif chosen == act_bp:
            self.set_type_requested.emit(mac, TYPE_BP)
        elif chosen == act_scale:
            self.set_type_requested.emit(mac, TYPE_SCALE)
        elif chosen == act_remove:
            self.remove_profile_requested.emit(mac)


# ──────────────────────────────────────────────────────────────────────
# 区域2：当前连接会话（只读）
# ──────────────────────────────────────────────────────────────────────

class SessionPanel(QGroupBox):
    """
    当前连接会话：只读表格 + 断开按钮。

    信号：
        session_selected(str, str)   选中某行：(mac, type)
        disconnect_requested(str)    断开选中：(mac)
        disconnect_all_requested()   断开全部
    """

    session_selected = Signal(str, str)
    disconnect_requested = Signal(str)
    disconnect_all_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("当前连接会话（区域2：只读状态）", parent)
        root = QVBoxLayout(self)
        root.setSpacing(6)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["名称 / MAC", "角色", "类型", "状态", "来源"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_selection_changed)
        self.table.setToolTip("选中一行后，右侧功能面板会切换到对应设备类型；此处只读，改连接请去区域1。")
        root.addWidget(self.table, stretch=1)

        row = QHBoxLayout()
        self.btn_disconnect = QPushButton("断开选中")
        self.btn_disconnect.clicked.connect(self._on_disconnect_clicked)
        row.addWidget(self.btn_disconnect)
        self.btn_disconnect_all = QPushButton("断开全部")
        self.btn_disconnect_all.clicked.connect(self.disconnect_all_requested)
        row.addWidget(self.btn_disconnect_all)
        row.addStretch()
        root.addLayout(row)

    def set_sessions(
        self,
        summary: List[Tuple[str, str, bool]],
        profile_get: Callable[[str], Optional[DeviceProfile]],
        source_get: Optional[Callable[[str], str]] = None,
    ) -> None:
        """
        刷新会话表。

        :param summary: [(mac, kind_label 'BP'/'HR', connected), ...]
        :param profile_get: 按 MAC 查档案
        :param source_get: 按 MAC 查连接来源（返回 "手动"/"预连接池"），可空
        """
        prev = self.selected_mac()
        self.table.setRowCount(0)
        for mac, kind, connected in summary:
            type_ = TYPE_BP if kind == "BP" else TYPE_BAND
            prof = profile_get(mac)
            name = prof.name if (prof and prof.name) else "(未命名)"
            role = (prof.role if prof else None) or ("server" if type_ == TYPE_BP else "client")
            source = source_get(mac) if source_get else "手动"
            r = self.table.rowCount()
            self.table.insertRow(r)
            it_name = QTableWidgetItem(f"{name}\n{mac}")
            it_name.setData(Qt.UserRole, mac)
            it_name.setData(Qt.UserRole + 1, type_)
            self.table.setItem(r, 0, it_name)
            self.table.setItem(r, 1, QTableWidgetItem(role))
            self.table.setItem(r, 2, QTableWidgetItem(type_label(type_)))
            self.table.setItem(r, 3, QTableWidgetItem("已连接" if connected else "未连接"))
            self.table.setItem(r, 4, QTableWidgetItem(source))
        self.table.resizeRowsToContents()
        # 尽量恢复之前的选中行
        if prev:
            for r in range(self.table.rowCount()):
                if str(self.table.item(r, 0).data(Qt.UserRole)) == prev:
                    self.table.selectRow(r)
                    break

    def selected_mac(self) -> Optional[str]:
        items = self.table.selectedItems()
        if not items:
            return None
        first = self.table.item(items[0].row(), 0)
        mac = first.data(Qt.UserRole) if first else None
        return str(mac) if mac else None

    def selected_type(self) -> Optional[str]:
        items = self.table.selectedItems()
        if not items:
            return None
        first = self.table.item(items[0].row(), 0)
        t = first.data(Qt.UserRole + 1) if first else None
        return str(t) if t else None

    def _on_selection_changed(self) -> None:
        mac = self.selected_mac()
        t = self.selected_type()
        if mac and t:
            self.session_selected.emit(mac, t)

    def _on_disconnect_clicked(self) -> None:
        mac = self.selected_mac()
        if mac:
            self.disconnect_requested.emit(mac)


# ──────────────────────────────────────────────────────────────────────
# 区域3 子面板：心率业务
# ──────────────────────────────────────────────────────────────────────

class HRBusinessWidget(QWidget):
    """心率手环业务面板：大字号心率 + 推送开关 + 实时日志。"""

    push_toggled = Signal(bool)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setSpacing(8)

        self.lbl_bpm = QLabel("-- BPM")
        self.lbl_bpm.setAlignment(Qt.AlignCenter)
        self.lbl_bpm.setStyleSheet("font-size: 48px; font-weight: bold; color: #c62828;")
        root.addWidget(self.lbl_bpm)

        row = QHBoxLayout()
        self.chk_push = QCheckBox("推送心率到 TV")
        self.chk_push.toggled.connect(self.push_toggled)
        row.addWidget(self.chk_push)
        row.addStretch()
        root.addLayout(row)

        root.addWidget(QLabel("实时日志："))
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setMinimumHeight(120)
        root.addWidget(self.text_log, stretch=1)

    def set_bpm(self, bpm: int) -> None:
        self.lbl_bpm.setText(f"{bpm} BPM")

    def append_log(self, text: str) -> None:
        self.text_log.append(text)


# ──────────────────────────────────────────────────────────────────────
# 区域3 子面板：血压业务
# ──────────────────────────────────────────────────────────────────────

class BPBusinessWidget(QWidget):
    """
    血压计业务面板：简化「开始测量」+ 结果区 + 高级选项折叠。

    信号：
        start_measure()    点「开始测量」（= 一键完整测量）
        push_toggled(bool) 勾选/取消「推送血压到 TV」
        cmd_connect() / cmd_power() / cmd_start() / cmd_stop() / start_wait_stop()
                           高级分步调试按钮
    """

    start_measure = Signal()
    push_toggled = Signal(bool)
    cmd_connect = Signal()
    cmd_power = Signal()
    cmd_start = Signal()
    cmd_stop = Signal()
    start_wait_stop = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # 开始测量（大按钮）
        self.btn_start_measure = QPushButton("开始测量")
        self.btn_start_measure.setMinimumHeight(48)
        self.btn_start_measure.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.btn_start_measure.clicked.connect(self.start_measure)
        root.addWidget(self.btn_start_measure)

        # 推送血压到 TV（与心率面板一致）
        self.chk_push = QCheckBox("推送血压到 TV")
        self.chk_push.toggled.connect(self.push_toggled)
        root.addWidget(self.chk_push)

        # 实时压力
        self.lbl_pressure = QLabel("实时压力：-- mmHg")
        root.addWidget(self.lbl_pressure)

        # 结果区
        gb_result = QGroupBox("测量结果")
        gr = QGridLayout(gb_result)
        self.lbl_sys = QLabel("--")
        self.lbl_dia = QLabel("--")
        self.lbl_pulse = QLabel("--")
        for lbl in (self.lbl_sys, self.lbl_dia, self.lbl_pulse):
            lbl.setStyleSheet("font-size: 28px; font-weight: bold; color: #1565c0;")
            lbl.setAlignment(Qt.AlignCenter)
        gr.addWidget(QLabel("高压(SYS)"), 0, 0, alignment=Qt.AlignCenter)
        gr.addWidget(QLabel("低压(DIA)"), 0, 1, alignment=Qt.AlignCenter)
        gr.addWidget(QLabel("脉搏(PUL)"), 0, 2, alignment=Qt.AlignCenter)
        gr.addWidget(self.lbl_sys, 1, 0)
        gr.addWidget(self.lbl_dia, 1, 1)
        gr.addWidget(self.lbl_pulse, 1, 2)
        root.addWidget(gb_result)

        # 高级选项（可折叠）
        self.gb_adv = QGroupBox("高级选项（分步调试 / 型号开关）")
        self.gb_adv.setCheckable(True)
        self.gb_adv.setChecked(False)
        adv_body = QWidget()
        av = QVBoxLayout(adv_body)
        av.setContentsMargins(0, 0, 0, 0)
        self.chk_force = QCheckBox("忽略电量门限（调试用）")
        av.addWidget(self.chk_force)
        self.chk_type9000 = QCheckBox("TYPE_9000 设备（BP0542/BP06 类，跳过连接指令）")
        av.addWidget(self.chk_type9000)
        grid = QGridLayout()
        self.btn_cmd_connect = QPushButton("连接指令")
        self.btn_cmd_connect.clicked.connect(self.cmd_connect)
        grid.addWidget(self.btn_cmd_connect, 0, 0)
        self.btn_cmd_power = QPushButton("查询电量")
        self.btn_cmd_power.clicked.connect(self.cmd_power)
        grid.addWidget(self.btn_cmd_power, 0, 1)
        self.btn_cmd_start = QPushButton("启动测量")
        self.btn_cmd_start.clicked.connect(self.cmd_start)
        grid.addWidget(self.btn_cmd_start, 1, 0)
        self.btn_cmd_stop = QPushButton("停止测量")
        self.btn_cmd_stop.clicked.connect(self.cmd_stop)
        grid.addWidget(self.btn_cmd_stop, 1, 1)
        self.btn_start_wait_stop = QPushButton("启动并等待结果（不发连接/电量）")
        self.btn_start_wait_stop.clicked.connect(self.start_wait_stop)
        grid.addWidget(self.btn_start_wait_stop, 2, 0, 1, 2)
        av.addLayout(grid)
        outer = QVBoxLayout(self.gb_adv)
        outer.setContentsMargins(6, 6, 6, 6)
        outer.addWidget(adv_body)
        # 折叠：未勾选时隐藏内容
        self._adv_body = adv_body
        self.gb_adv.toggled.connect(self._adv_body.setVisible)
        self._adv_body.setVisible(False)
        root.addWidget(self.gb_adv)

        # 实时日志（加压过程 / 测量结果实时滚动）
        root.addWidget(QLabel("实时日志："))
        self.text_log = QTextEdit()
        self.text_log.setReadOnly(True)
        self.text_log.setMinimumHeight(120)
        root.addWidget(self.text_log, stretch=1)

    def set_pressure(self, mmhg: int) -> None:
        self.lbl_pressure.setText(f"实时压力：{mmhg} mmHg")

    def append_log(self, text: str) -> None:
        self.text_log.append(text)

    def set_result(self, sys_: int, dia_: int, pulse: int) -> None:
        self.lbl_sys.setText(str(sys_))
        self.lbl_dia.setText(str(dia_))
        self.lbl_pulse.setText(str(pulse))

    def is_force(self) -> bool:
        return self.chk_force.isChecked()

    def is_type9000(self) -> bool:
        return self.chk_type9000.isChecked()

    def set_busy(self, busy: bool) -> None:
        """测量进行中禁用按钮，避免重复下发透传帧。"""
        for b in (
            self.btn_start_measure,
            self.btn_cmd_connect,
            self.btn_cmd_power,
            self.btn_cmd_start,
            self.btn_cmd_stop,
            self.btn_start_wait_stop,
        ):
            b.setEnabled(not busy)


# ──────────────────────────────────────────────────────────────────────
# 预连接池管理（FunctionPanel 的一个 Tab）
# ──────────────────────────────────────────────────────────────────────

class PoolManagerWidget(QWidget):
    """
    预连接池管理表：列出 devices.json 全部档案，可勾选 AutoConnect、编辑、删除、导入/导出。

    信号：
        auto_connect_changed(str, bool)  某行 AutoConnect 勾选变化：(mac, value)
        edit_requested(str)              点「编辑」：(mac)
        remove_requested(str)            点「删除」：(mac)
        import_requested()               点「导入」
        export_requested()               点「导出」
        save_requested()                 点「保存到 devices.json」
    """

    auto_connect_changed = Signal(str, bool)
    edit_requested = Signal(str)
    remove_requested = Signal(str)
    import_requested = Signal()
    export_requested = Signal()
    save_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._suppress = False  # 重建表格时抑制复选框信号
        root = QVBoxLayout(self)
        root.setSpacing(6)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["自动", "名称", "MAC", "类型", "分组", "最近连接"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.doubleClicked.connect(self._on_double_clicked)
        root.addWidget(self.table, stretch=1)

        row = QHBoxLayout()
        self.btn_edit = QPushButton("编辑")
        self.btn_edit.clicked.connect(self._on_edit_clicked)
        row.addWidget(self.btn_edit)
        self.btn_remove = QPushButton("删除")
        self.btn_remove.clicked.connect(self._on_remove_clicked)
        row.addWidget(self.btn_remove)
        row.addStretch()
        self.btn_import = QPushButton("导入…")
        self.btn_import.clicked.connect(self.import_requested)
        row.addWidget(self.btn_import)
        self.btn_export = QPushButton("导出…")
        self.btn_export.clicked.connect(self.export_requested)
        row.addWidget(self.btn_export)
        self.btn_save = QPushButton("保存")
        self.btn_save.setToolTip("把当前内存中的预连接配置强制写入 devices.json")
        self.btn_save.clicked.connect(self.save_requested)
        row.addWidget(self.btn_save)
        root.addLayout(row)

    def set_profiles(self, profiles: List[DeviceProfile]) -> None:
        """用全部档案重建表格。"""
        self._suppress = True
        self.table.setRowCount(0)
        for p in profiles:
            r = self.table.rowCount()
            self.table.insertRow(r)
            chk = QCheckBox()
            chk.setChecked(p.auto_connect)
            chk.toggled.connect(lambda v, m=p.mac: self._on_chk_toggled(m, v))
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(0, 0, 0, 0)
            hl.setAlignment(Qt.AlignCenter)
            hl.addWidget(chk)
            self.table.setCellWidget(r, 0, holder)
            it_name = QTableWidgetItem(p.name or "(未命名)")
            it_name.setData(Qt.UserRole, p.mac)
            self.table.setItem(r, 1, it_name)
            self.table.setItem(r, 2, QTableWidgetItem(p.mac))
            self.table.setItem(r, 3, QTableWidgetItem(type_label(p.type)))
            self.table.setItem(r, 4, QTableWidgetItem(p.group or "—"))
            self.table.setItem(r, 5, QTableWidgetItem(p.last_connected or "—"))
        self._suppress = False

    def selected_mac(self) -> Optional[str]:
        items = self.table.selectedItems()
        if not items:
            return None
        it = self.table.item(items[0].row(), 1)
        mac = it.data(Qt.UserRole) if it else None
        return str(mac) if mac else None

    def _on_chk_toggled(self, mac: str, value: bool) -> None:
        if not self._suppress:
            self.auto_connect_changed.emit(mac, value)

    def _on_edit_clicked(self) -> None:
        mac = self.selected_mac()
        if mac:
            self.edit_requested.emit(mac)

    def _on_remove_clicked(self) -> None:
        mac = self.selected_mac()
        if mac:
            self.remove_requested.emit(mac)

    def _on_double_clicked(self, _index) -> None:  # noqa: ANN001
        mac = self.selected_mac()
        if mac:
            self.edit_requested.emit(mac)


# ──────────────────────────────────────────────────────────────────────
# 区域3：动态功能面板
# ──────────────────────────────────────────────────────────────────────

class FunctionPanel(QGroupBox):
    """
    动态功能面板：连接设置 Tab + 业务操作 Tab（按设备类型切换）。

    信号：
        pair_toggled(bool)
        keepalive_toggled(bool)
        keepalive_interval_changed(int)
        auto_disconnect_changed(int)
        hr_push_toggled(bool)
        bp_start_measure() / bp_cmd_connect() / bp_cmd_power() /
        bp_cmd_start() / bp_cmd_stop() / bp_start_wait_stop()
    """

    pair_toggled = Signal(bool)
    keepalive_toggled = Signal(bool)
    keepalive_interval_changed = Signal(int)
    auto_disconnect_changed = Signal(int)
    hr_push_toggled = Signal(bool)
    bp_start_measure = Signal()
    bp_push_toggled = Signal(bool)
    bp_cmd_connect = Signal()
    bp_cmd_power = Signal()
    bp_cmd_start = Signal()
    bp_cmd_stop = Signal()
    bp_start_wait_stop = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("功能面板（区域3：随所选设备类型切换）", parent)
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # TV 联动状态灯（阶段二使用）
        self.lbl_tv_status = QLabel("TV 联动：未启用")
        self.lbl_tv_status.setStyleSheet("padding: 4px; border-radius: 4px; background: #eeeeee;")
        root.addWidget(self.lbl_tv_status)

        self.tabs = QTabWidget()
        root.addWidget(self.tabs, stretch=1)

        # Tab1：连接设置（通用）
        tab_conn = QWidget()
        cv = QGridLayout(tab_conn)
        cv.setVerticalSpacing(10)
        cv.addWidget(QLabel("自动断开时间"), 0, 0)
        self.spin_auto_disconnect = QSpinBox()
        self.spin_auto_disconnect.setRange(0, 3600)
        self.spin_auto_disconnect.setValue(0)
        self.spin_auto_disconnect.setSuffix(" 秒（0=持续连接）")
        self.spin_auto_disconnect.valueChanged.connect(self.auto_disconnect_changed)
        cv.addWidget(self.spin_auto_disconnect, 0, 1)
        self.chk_pair = QCheckBox("连接时系统配对（血压计首次可勾选；心率手环不勾选）")
        self.chk_pair.toggled.connect(self.pair_toggled)
        cv.addWidget(self.chk_pair, 1, 0, 1, 2)
        self.chk_keepalive = QCheckBox("连接后定时查询电量（试探延长待机，仅血压计）")
        self.chk_keepalive.toggled.connect(self.keepalive_toggled)
        cv.addWidget(self.chk_keepalive, 2, 0, 1, 2)
        row_kp = QHBoxLayout()
        row_kp.addWidget(QLabel("查电间隔"))
        self.spin_keepalive_interval = QSpinBox()
        self.spin_keepalive_interval.setRange(5, 600)
        self.spin_keepalive_interval.setValue(5)
        self.spin_keepalive_interval.setSuffix(" 秒")
        self.spin_keepalive_interval.valueChanged.connect(self.keepalive_interval_changed)
        row_kp.addWidget(self.spin_keepalive_interval)
        row_kp.addStretch()
        cv.addLayout(row_kp, 3, 0, 1, 2)
        cv.setRowStretch(4, 1)
        self.tabs.addTab(tab_conn, "连接设置")

        # Tab2：业务操作（动态）
        self.stack = QStackedWidget()
        self.page_empty = QLabel("请在「当前连接会话」中选中一台设备，以加载对应业务面板。")
        self.page_empty.setAlignment(Qt.AlignCenter)
        self.page_empty.setWordWrap(True)
        self.hr = HRBusinessWidget()
        self.bp = BPBusinessWidget()
        self._idx_empty = self.stack.addWidget(self.page_empty)
        self._idx_hr = self.stack.addWidget(self.hr)
        self._idx_bp = self.stack.addWidget(self.bp)
        self.tabs.addTab(self.stack, "业务操作")

        # Tab3：预连接池管理
        self.pool_manager = PoolManagerWidget()
        self.tabs.addTab(self.pool_manager, "预连接池管理")

        # Tab4：TV 联调（协议报文预览 + 模拟 START）
        self.tv_debug = TvDebugWidget()
        self.tabs.addTab(self.tv_debug, "TV 联调")

        # 透传子面板信号转发
        self.hr.push_toggled.connect(self.hr_push_toggled)
        self.bp.start_measure.connect(self.bp_start_measure)
        self.bp.push_toggled.connect(self.bp_push_toggled)
        self.bp.cmd_connect.connect(self.bp_cmd_connect)
        self.bp.cmd_power.connect(self.bp_cmd_power)
        self.bp.cmd_start.connect(self.bp_cmd_start)
        self.bp.cmd_stop.connect(self.bp_cmd_stop)
        self.bp.start_wait_stop.connect(self.bp_start_wait_stop)

    # ---- 切换与更新 ----

    def show_for_type(self, type_: Optional[str]) -> None:
        """按设备类型切换业务面板，并跳到「业务操作」Tab。"""
        if type_ == TYPE_BAND:
            self.stack.setCurrentIndex(self._idx_hr)
        elif type_ == TYPE_BP:
            self.stack.setCurrentIndex(self._idx_bp)
        else:
            self.stack.setCurrentIndex(self._idx_empty)

    def show_empty(self) -> None:
        self.stack.setCurrentIndex(self._idx_empty)

    def set_hr(self, bpm: int) -> None:
        self.hr.set_bpm(bpm)

    def append_hr_log(self, text: str) -> None:
        self.hr.append_log(text)

    def set_bp_pressure(self, mmhg: int) -> None:
        self.bp.set_pressure(mmhg)

    def append_bp_log(self, text: str) -> None:
        self.bp.append_log(text)

    def set_bp_result(self, sys_: int, dia_: int, pulse: int) -> None:
        self.bp.set_result(sys_, dia_, pulse)

    def set_tv_status(self, text: str, *, active: bool = False, waiting: bool = False) -> None:
        """更新 TV 联动状态灯。"""
        if waiting:
            bg = "#fff3cd"  # 黄：等待授权
        elif active:
            bg = "#d4edda"  # 绿：已启用/已连通
        else:
            bg = "#eeeeee"  # 灰：未启用
        self.lbl_tv_status.setText(text)
        self.lbl_tv_status.setStyleSheet(f"padding: 4px; border-radius: 4px; background: {bg};")


class TvDebugWidget(QWidget):
  """
  TV 联调面板：最近发出的报文预览 + 模拟 TV 控制指令。

  信号：
      send_script_ready_requested()
      simulate_start_requested()
      simulate_start_measure_requested()
  """

  send_script_ready_requested = Signal()
  simulate_start_requested = Signal()
  simulate_start_measure_requested = Signal()

  def __init__(self, parent: Optional[QWidget] = None) -> None:
    super().__init__(parent)
    root = QVBoxLayout(self)
    row = QHBoxLayout()
    self.btn_ready = QPushButton("发送 SCRIPT_READY")
    self.btn_ready.clicked.connect(self.send_script_ready_requested)
    row.addWidget(self.btn_ready)
    self.btn_sim_start = QPushButton("模拟 TV: START")
    self.btn_sim_start.clicked.connect(self.simulate_start_requested)
    row.addWidget(self.btn_sim_start)
    self.btn_sim_measure = QPushButton("模拟 TV: START_MEASURE")
    self.btn_sim_measure.clicked.connect(self.simulate_start_measure_requested)
    row.addWidget(self.btn_sim_measure)
    row.addStretch()
    root.addLayout(row)
    root.addWidget(QLabel("最近发出的 TV 报文（最多 20 条）："))
    self.text_msgs = QTextEdit()
    self.text_msgs.setReadOnly(True)
    self.text_msgs.setMinimumHeight(120)
    root.addWidget(self.text_msgs, stretch=1)

  def append_outbound(self, line: str) -> None:
    """追加一条发出报文；超过 20 条时删最旧。"""
    lines = self.text_msgs.toPlainText().splitlines()
    lines.append(line)
    if len(lines) > 20:
      lines = lines[-20:]
    self.text_msgs.setPlainText("\n".join(lines))
    self.text_msgs.verticalScrollBar().setValue(self.text_msgs.verticalScrollBar().maximum())


class LogTabsWidget(QGroupBox):
  """运行日志分区：运行 | TV 协议 | BLE 调试。"""

  def __init__(self, parent: Optional[QWidget] = None) -> None:
    super().__init__("运行日志", parent)
    lay = QVBoxLayout(self)
    self.tabs = QTabWidget()
    self.text_run = QTextEdit()
    self.text_run.setReadOnly(True)
    self.text_tv = QTextEdit()
    self.text_tv.setReadOnly(True)
    self.text_ble = QTextEdit()
    self.text_ble.setReadOnly(True)
    self.tabs.addTab(self.text_run, "运行")
    self.tabs.addTab(self.text_tv, "TV 协议")
    self.tabs.addTab(self.text_ble, "BLE 调试")
    lay.addWidget(self.tabs)

  def append_run(self, text: str) -> None:
    self.text_run.append(text)

  def append_tv(self, text: str) -> None:
    self.text_tv.append(text)

  def append_ble(self, text: str) -> None:
    self.text_ble.append(text)

  def clear_all(self) -> None:
    self.text_run.clear()
    self.text_tv.clear()
    self.text_ble.clear()


# ──────────────────────────────────────────────────────────────────────
# 区域4：底部全局栏 + TV 推送配置
# ──────────────────────────────────────────────────────────────────────

class GlobalBar(QGroupBox):
    """
    底部全局栏：左=全局按钮；右=TV 推送配置。

    信号：
        refresh_requested()
        clear_log_requested()
        save_log_requested()
        tv_test_requested()
        tv_linkage_toggled(bool)
        tv_config_changed()
    """

    refresh_requested = Signal()
    clear_log_requested = Signal()
    save_log_requested = Signal()
    save_pool_requested = Signal()
    tv_test_requested = Signal()
    tv_linkage_toggled = Signal(bool)
    tv_config_changed = Signal()
    detect_script_ip_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__("全局控制 / TV 联动（区域4）", parent)
        outer = QVBoxLayout(self)
        row_main = QHBoxLayout()
        row_main.setSpacing(10)

        # 左：全局按钮
        self.btn_refresh = QPushButton("刷新")
        self.btn_refresh.clicked.connect(self.refresh_requested)
        row_main.addWidget(self.btn_refresh)
        self.btn_clear_log = QPushButton("清空日志")
        self.btn_clear_log.clicked.connect(self.clear_log_requested)
        row_main.addWidget(self.btn_clear_log)
        self.btn_save_log = QPushButton("保存日志")
        self.btn_save_log.clicked.connect(self.save_log_requested)
        row_main.addWidget(self.btn_save_log)
        self.btn_save_pool = QPushButton("保存预连接配置")
        self.btn_save_pool.setToolTip("把当前预连接池状态强制写入 devices.json")
        self.btn_save_pool.clicked.connect(self.save_pool_requested)
        row_main.addWidget(self.btn_save_pool)

        self.lbl_pool_count = QLabel("预连接池：0 个设备")
        self.lbl_pool_count.setStyleSheet("padding: 2px 8px; border-radius: 4px; background: #e3f2fd;")
        row_main.addWidget(self.lbl_pool_count)
        row_main.addStretch()
        outer.addLayout(row_main)

        row_tv = QHBoxLayout()
        row_tv.setSpacing(8)

        # 协议阶段
        row_tv.addWidget(QLabel("协议阶段"))
        self.combo_stage = QComboBox()
        self.combo_stage.addItem("L0 纯文本", "L0")
        self.combo_stage.addItem("T0 JSON+文本", "T0")
        self.combo_stage.addItem("P0 双信道", "P0")
        self.combo_stage.setCurrentIndex(2)  # 默认 P0 产品协议
        self.combo_stage.currentIndexChanged.connect(lambda _i: self.tv_config_changed.emit())
        row_tv.addWidget(self.combo_stage)

        row_tv.addWidget(_vline())

        row_tv.addWidget(QLabel("TV推送"))
        self.combo_mode = QComboBox()
        self.combo_mode.addItem("广播", "broadcast")
        self.combo_mode.addItem("单播", "unicast")
        self.combo_mode.setToolTip(
            "广播：向 255.255.255.255:18500 发 A 信道（发现/心率/DEVICE_READY）\n"
            "单播：仅向下方「TV IP」发 A 信道"
        )
        self.combo_mode.currentIndexChanged.connect(self._on_mode_changed)
        row_tv.addWidget(self.combo_mode)
        row_tv.addWidget(QLabel("TV IP"))
        self.edit_ip = QLineEdit("255.255.255.255")
        self.edit_ip.setFixedWidth(120)
        self.edit_ip.setEnabled(False)
        self.edit_ip.setToolTip("仅「TV推送=单播」时使用：A 信道单播目标")
        self.edit_ip.editingFinished.connect(self.tv_config_changed)
        row_tv.addWidget(self.edit_ip)
        row_tv.addWidget(QLabel("机顶盒IP"))
        self.edit_unicast = QLineEdit()
        self.edit_unicast.setPlaceholderText("真机填机顶盒IP；模拟器 127.0.0.1")
        self.edit_unicast.setFixedWidth(130)
        self.edit_unicast.setToolTip(
            "对应 gateway.json 的 tv_unicast_ip。\n"
            "PC 向 A 信道(18500) 单播加固：SCRIPT_READY、DEVICE_READY、心率等。\n"
            "真机：机顶盒局域网 IP（设置→网络里查看）。\n"
            "模拟器：127.0.0.1（配合 adb redir 18500）。\n"
            "测血压 ACK/进度/结果走 B 信道 reply_to，不依赖本项。"
        )
        self.edit_unicast.editingFinished.connect(self.tv_config_changed)
        row_tv.addWidget(self.edit_unicast)
        row_tv.addWidget(QLabel("端口A"))
        self.spin_port = QSpinBox()
        self.spin_port.setRange(1, 65535)
        self.spin_port.setValue(18500)
        self.spin_port.valueChanged.connect(lambda _v: self.tv_config_changed.emit())
        row_tv.addWidget(self.spin_port)

        self.chk_json = QCheckBox("JSON")
        self.chk_json.setChecked(True)
        self.chk_json.toggled.connect(lambda _v: self.tv_config_changed.emit())
        row_tv.addWidget(self.chk_json)
        self.chk_text = QCheckBox("文本")
        self.chk_text.setChecked(True)
        self.chk_text.toggled.connect(lambda _v: self.tv_config_changed.emit())
        row_tv.addWidget(self.chk_text)
        self.chk_no_broadcast = QCheckBox("禁用广播")
        self.chk_no_broadcast.setToolTip(
            "勾选后 A 信道不再发 255.255.255.255 广播，\n"
            "必须填写「机顶盒IP」；真机联调建议不勾选。"
        )
        self.chk_no_broadcast.toggled.connect(lambda _v: self.tv_config_changed.emit())
        row_tv.addWidget(self.chk_no_broadcast)

        row_tv.addWidget(QLabel("script_ip"))
        self.edit_script_ip = QLineEdit()
        self.edit_script_ip.setPlaceholderText("PC 局域网 IP")
        self.edit_script_ip.setFixedWidth(110)
        self.edit_script_ip.setToolTip(
            "写入 SCRIPT_READY.script_ip，TV 据此向 PC:18501 发 START_MEASURE。\n"
            "真机填 PC 在 WiFi/网线下的 IP，可点「检测」。"
        )
        self.edit_script_ip.editingFinished.connect(self.tv_config_changed)
        row_tv.addWidget(self.edit_script_ip)
        self.btn_detect_ip = QPushButton("检测")
        self.btn_detect_ip.clicked.connect(self.detect_script_ip_requested)
        row_tv.addWidget(self.btn_detect_ip)

        self.lbl_b_status = QLabel("B: —")
        self.lbl_b_status.setStyleSheet("padding: 2px 6px; background: #eee; border-radius: 3px;")
        row_tv.addWidget(self.lbl_b_status)

        self.btn_test = QPushButton("测试连接")
        self.btn_test.clicked.connect(self.tv_test_requested)
        row_tv.addWidget(self.btn_test)
        self.chk_linkage = QCheckBox("TV 联动")
        self.chk_linkage.setToolTip("测量前发 READY 并等待 TV 的 START / START_MEASURE")
        self.chk_linkage.toggled.connect(self.tv_linkage_toggled)
        row_tv.addWidget(self.chk_linkage)
        row_tv.addStretch()
        outer.addLayout(row_tv)

    def set_channel_b_status(self, ok: bool) -> None:
        if ok:
            self.lbl_b_status.setText("B: 已监听")
            self.lbl_b_status.setStyleSheet("padding: 2px 6px; background: #d4edda; border-radius: 3px;")
        else:
            self.lbl_b_status.setText("B: 未监听")
            self.lbl_b_status.setStyleSheet("padding: 2px 6px; background: #eee; border-radius: 3px;")

    def set_gateway_config(self, cfg: object) -> None:
        """从 GatewayConfig 回填控件。"""
        stage = getattr(cfg, "protocol_stage", "P0")
        i = self.combo_stage.findData(stage)
        if i >= 0:
            self.combo_stage.setCurrentIndex(i)
        mode = getattr(cfg, "tv_mode", "broadcast")
        j = self.combo_mode.findData(mode)
        if j >= 0:
            self.combo_mode.setCurrentIndex(j)
        self.edit_ip.setText(getattr(cfg, "tv_ip", "255.255.255.255"))
        self.edit_unicast.setText(getattr(cfg, "tv_unicast_ip", ""))
        self.spin_port.setValue(int(getattr(cfg, "port_a", 18500)))
        self.chk_json.setChecked(bool(getattr(cfg, "json_mode", True)))
        self.chk_text.setChecked(bool(getattr(cfg, "text_mode", True)))
        self.chk_no_broadcast.setChecked(bool(getattr(cfg, "no_broadcast", False)))
        self.edit_script_ip.setText(getattr(cfg, "script_ip", ""))

    def _on_mode_changed(self, _idx: int) -> None:
        is_unicast = self.combo_mode.currentData() == "unicast"
        self.edit_ip.setEnabled(is_unicast)
        if not is_unicast:
            self.edit_ip.setText("255.255.255.255")
        self.tv_config_changed.emit()

    def get_tv_config(self) -> dict:
        return {
            "protocol_stage": str(self.combo_stage.currentData() or "P0"),
            "mode": str(self.combo_mode.currentData() or "broadcast"),
            "ip": self.edit_ip.text().strip() or "255.255.255.255",
            "unicast_ip": self.edit_unicast.text().strip(),
            "port_a": int(self.spin_port.value()),
            "text_mode": self.chk_text.isChecked(),
            "json_mode": self.chk_json.isChecked(),
            "no_broadcast": self.chk_no_broadcast.isChecked(),
            "script_ip": self.edit_script_ip.text().strip(),
        }

    def is_linkage_on(self) -> bool:
        return self.chk_linkage.isChecked()

    def set_pool_count(self, count: int) -> None:
        self.lbl_pool_count.setText(f"预连接池：{count} 个设备")


def _vline() -> QWidget:
    """竖直分隔线。"""
    from PySide6.QtWidgets import QFrame

    line = QFrame()
    line.setFrameShape(QFrame.VLine)
    line.setFrameShadow(QFrame.Sunken)
    return line
