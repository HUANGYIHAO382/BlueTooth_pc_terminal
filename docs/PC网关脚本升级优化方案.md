# PC 网关脚本升级优化方案（全量）

## 1. 文档说明

本文档在 [PC网关脚本功能与实现分析.md](./PC网关脚本功能与实现分析.md)（**现网 L0 是什么**）基础上，给出 **面向产品联调与长期维护** 的升级优化方案，覆盖：

- **升级重点与优先级**
- **架构 / 模块**（对照 [项目结构与模块解耦说明.md](./项目结构与模块解耦说明.md)）
- **TV 协议与双信道**（对照 [pc_gateway升级方案.md](./pc_gateway升级方案.md)、[通讯格式文档.md](./通讯格式文档.md)）
- **脚本 UI、交互、功能**
- **分阶段交付与验收**（对照 [AndroidStudio双信道测试方案.md](./AndroidStudio双信道测试方案.md)）

**与其它文档的分工：**

| 文档 | 本文如何使用它 |
|------|----------------|
| [PC网关脚本功能与实现分析.md](./PC网关脚本功能与实现分析.md) | 升级起点；每项「现状」以此为准 |
| [pc_gateway升级方案.md](./pc_gateway升级方案.md) | **协议 L0→T0→P0** 的字段与端口细节；本文 §5 做任务映射，不重复 JSON 样例 |
| [通讯格式文档.md](./通讯格式文档.md) | 包体格式字典；实现时按阶段查 F1/F2 |
| [udp_信道设计.md](./udp_信道设计.md) | 双信道职责边界、能力矩阵 |
| [AndroidStudio双信道测试方案.md](./AndroidStudio双信道测试方案.md) | 每阶段怎么测、真机 vs 模拟器 |
| [项目结构与模块解耦说明.md](./项目结构与模块解耦说明.md) | BLE/UDP 解耦、独立复用模块的参考形态 |

**核心原则（与 TV 文档一致）：**

1. **复杂逻辑在 PC**：蓝牙、测量状态机、进度计算、文本→JSON 转换；
2. **TV 薄解析**：按 `type` 路由，不在 TV 用正则解析中文；
3. **分阶段验收**：L0 / T0 / P0 不混用期望（见 [pc_gateway §1.3](./pc_gateway升级方案.md)）；
4. **最小破坏升级**：T0 可与 L0 文本双发，便于工程师对照与回退。

---

## 2. 升级目标（一句话）

把 `pc_ble_client` 从 **工程师调试工具（L0 纯文本 + 单端口）** 升级为 **产品级家庭健康网关（T0/P0 JSON + 双信道 + 可运维 UI）**，同时保持血压/心率 BLE 路径稳定、设备档案与预连接池可用。

---

## 3. 升级总览

### 3.1 阶段路线

```text
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 R0（建议先做，1～2 天）                                       │
│  · 代码解耦：tv 消息层、测量状态机、配置持久化                      │
│  · UI：协议阶段指示、TV 联调面板增强                               │
│  · 不强制改 TV 行为                                                │
└───────────────────────────────┬─────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 T0（协议过渡，与 TV JSON 图表联调）                            │
│  · 18500 发 F2 JSON（可与 F1 双发）                                │
│  · SCRIPT_READY / DEVICE_READY / HR_STREAM / PROGRESS / RESULT   │
│  · 仍 listen 18500 收 START / START_MEASURE                      │
└───────────────────────────────┬─────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 P0（产品闭环）                                                │
│  · bind 0.0.0.0:18501，START_MEASURE → ACK → 进度 → 结果         │
│  · 18500 与 18501 职责分离                                         │
│  · 与 mock_gateway / TV 产品 UI 验收一致                           │
└───────────────────────────────┬─────────────────────────────────┘
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│ 阶段 P1（可选）                                                    │
│  · F3 统一信封、GATEWAY_HEARTBEAT、托盘/后台常驻                    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 模块升级矩阵

| 模块 / 文件 | 现网 | 升级方向 | 阶段 |
|-------------|------|----------|------|
| `tv_link.py` | 单端口、text_mode、简单 START | 双 socket、消息路由、request_id、双发 | T0/P0 |
| **新建** `tv_messages.py` | 无 | JSON type 构造、校验、序列化 | T0 |
| **新建** `measure_fsm.py` | 逻辑散在 `bp_demo_app` | BP 测量状态机、CANCEL、超时 | P0 |
| `reading_format.py` | 仅文本 | 增加「结构化 Reading」供 JSON 复用 | T0 |
| `bp_demo_app.py` | 业务总线过重 | 瘦身为编排层；TV/BLE 回调下沉 | R0/T0 |
| `multi_ble_backend.py` | BP+HR 编排 | 发 DEVICE_READY/OFFLINE；进度回调带 phase | T0 |
| `ui_panels.py` | 四区调试 UI | TV 联调区、协议阶段、日志分级 | R0/T0 |
| `device_profile.py` | devices.json | 增加 gateway.json（TV IP、阶段、端口） | R0 |
| `run_gui.py` | 无 CLI | `--tv-ip`、`--no-broadcast`、`--protocol-stage` | R0 |

---

## 4. 升级重点（优先级）

### 4.1 P0 — 必须做（阻塞 TV 产品联调）

| # | 重点 | 原因 | 主要改动 |
|---|------|------|----------|
| **P0-1** | **TV 协议 T0 JSON 上 18500** | TV 图表/角标依赖结构化字段，不能长期靠 F1 文本 | `tv_messages.py` + `tv_link` 双发 |
| **P0-2** | **文本→字段在 PC 内转换** | 禁止 TV 正则解析「加压中: 97 mmHg」 | `reading_format` / 测量循环直接产出 JSON 字段 |
| **P0-3** | **SCRIPT_READY + script_ip + listen_port** | TV 需知道往哪发 START | 启动与每 60s 广播；`listen_port` T0=18500，P0=18501 |
| **P0-4** | **DEVICE_READY / DEVICE_OFFLINE** | TV 血压入口亮灭 | BP 连接/断开时发 JSON |
| **P0-5** | **18501 监听 + START_MEASURE 闭环** | TV 产品 OK 走 B 信道 | `tv_link` 第二 transport；`measure_fsm` |
| **P0-6** | **request_id 全链路** | 日志关联、ACK/RESULT 配对 | 状态机持有当前 request_id |
| **P0-7** | **单播 + 广播双发** | 真机/部分路由下广播不可靠 | `127.0.0.1`（模拟器）或 `TV_IP` 单播加固 |

### 4.2 P1 — 应做（体验与可维护）

| # | 重点 | 说明 |
|---|------|------|
| **P1-1** | `bp_demo_app` 瘦身 | TV 推送、测量触发从 MainWindow 抽到 `GatewayController` |
| **P1-2** | UI「协议阶段」显式化 | 下拉：L0 / T0 / P0，避免工程师误用验收标准 |
| **P1-3** | 日志分级 | 运行日志 / 协议十六进制 / TV 报文 分 Tab 或颜色 |
| **P1-4** | 加压推送节流 | 避免 UI 与 UDP 刷屏（如 200ms 合并 PROGRESS） |
| **P1-5** | `gateway.json` 持久化 | TV IP、端口、text_mode、stage、script_ip 重启可恢复 |
| **P1-6** | 测量错误码 | `MEASURE_ERROR`：TIMEOUT、LOW_BATTERY、DISCONNECTED 等 |

### 4.3 P2 — 可选（产品 polish / 扩展）

| # | 重点 | 说明 |
|---|------|------|
| **P2-1** | 系统托盘 + 最小化到托盘 | 参考 HeartRateMonitor 托盘思路 |
| **P2-2** | 华为等私有手环协议 | 与标准 0x180D 分 `type=vendor_band` |
| **P2-3** | 体脂秤 `scale` | 新 BLE 路径，档案已占位 |
| **P2-4** | F3 信封 + `GATEWAY_HEARTBEAT` | P1 协议统一 |
| **P2-5** | CLI `ruiguang_bp_pc.py` 与 GUI 共用 `measure_fsm` | 避免两套测量逻辑 |

---

## 5. 协议与 TV 联动升级（脚本能力）

> JSON 字段与端口细节见 [pc_gateway升级方案 §5–§7](./pc_gateway升级方案.md)、[通讯格式文档 §5](./通讯格式文档.md)。

### 5.1 `tv_link.py` 重构目标

**现状：** 单 `DEFAULT_PORT=18500`；`text_mode` 发纯文本；`wait_for_start` 在 18500 上等 `START`。

**目标结构：**

```text
TvLink
├── sock_a (发送为主，也可 T0 收 Legacy START)
│     · send_broadcast + send_unicast(TV_IP)
│     · emit: SCRIPT_READY, HR_STREAM, DEVICE_*, text_line(可选)
├── sock_b (P0 必须)
│     · bind("0.0.0.0", 18501)
│     · on: START_MEASURE, CANCEL_MEASURE
│     · reply: ACK, PROGRESS, RESULT, ERROR → reply_to 或 TV:18501
└── ProtocolStage: L0 | T0 | P0
```

**实现要点：**

| 项 | T0 | P0 |
|----|----|----|
| PC listen | 18500（兼容） | **18500 + 18501** 双 listen |
| PC→TV 进度/结果 | JSON 可走 18500 | **仅 18501** 单播 |
| TV→PC START | 18500 `START` / `START_MEASURE` | **18501** `START_MEASURE` |
| text_mode | 可与 JSON 双发 | 建议仅工程师开关 |

### 5.2 新建 `tv_messages.py`（建议）

集中构造 F2 JSON，避免 `bp_demo_app` 里散落 dict：

```python
# 示例职责（实现时加注释）
def script_ready(script_ip: str, listen_port: int, devices: list[str]) -> dict: ...
def heart_rate_stream(bpm: int, ts_ms: int) -> dict: ...
def measure_progress(request_id: str, phase: str, progress: int, pressure: int) -> dict: ...
def measure_result(request_id: str, sys: int, dia: int, pulse: int, ts_ms: int) -> dict: ...
```

序列化统一 `json.dumps(..., ensure_ascii=False)`，单包 UTF-8。

### 5.3 新建 `measure_fsm.py`（P0 必须）

将 [pc_gateway §6.3](./pc_gateway升级方案.md) 状态机落地：

```text
Idle → (START_MEASURE) → Measuring → Done/Error → Idle
         ↑ CANCEL / 超时 / 断开
```

- `multi_ble_backend.run_full_measurement` 改为被 FSM **驱动**，而不是仅从 GUI 按钮调用；
- 加压回调 → 计算 `phase` + `progress`（映射表见 pc_gateway §7）→ `MEASURE_PROGRESS`；
- 结果回调 → `MEASURE_RESULT`；
- 与 `request_id` 绑定，拒绝交叉测量。

### 5.4 Legacy 文本与 JSON 的关系

| 数据源 | L0 | T0 | P0 |
|--------|----|----|-----|
| 心率 BPM | F1 行 | F2 `HEART_RATE_STREAM` | 同 T0，走 18500 |
| 加压 | F1 行 | F2 `MEASURE_PROGRESS` | F2，走 **18501** |
| 结果 | F1 行 | F2 `MEASURE_RESULT` | F2，走 **18501** |

**实现原则：** 在 `multi_ble_backend` 或 `GatewayController` 的**同一回调点**同时更新 UI 文本与 JSON 字段，不要「先拼中文再正则拆回数字」。

### 5.5 与 TV 端的协作边界

| 能力 | PC 升级后 | TV 仍需完成（见 pc_gateway §1.4） |
|------|-----------|-----------------------------------|
| 收 JSON 点亮 BP 角标 | 发 `DEVICE_READY` | Controller 接线 |
| 遥控器 OK | 收 `START_MEASURE` @18501 | 产品 UI 发 B 信道 |
| 进度环 | 发 `MEASURE_PROGRESS` | 图表吃 JSON 非 Mock 定时器 |
| 存历史 | 发 `MEASURE_RESULT` | TV 写 `bp_history.json` |

**联调策略：** PC 先到 T0，TV 用工程师控制台验 JSON；P0 再与 TV 产品 OK 闭环。

---

## 6. 架构与模块解耦升级

对照 [项目结构与模块解耦说明.md](./项目结构与模块解耦说明.md)，现网 `pc_ble_client` 已部分解耦（`hr_ble_backend`、`tv_link`、`reading_format`），但 **MainWindow 仍过重**。建议：

### 6.1 目标分层

```text
run_gui.py / bp_demo_app.py          # 入口 + 窗口壳
    GatewayController（新建）         # 编排：BLE 事件 → UI + TV + FSM
        ├── MultiBleBackend           # 不变，补 DEVICE 事件
        ├── TvLink                    # 双信道
        ├── MeasureFsm                # P0
        ├── DeviceProfileStore        # 设备档案
        └── GatewayConfigStore（新建） # TV/协议配置
ui_panels.py                          # 纯 UI，无 bleak
tv_messages.py                        # 纯 JSON 构造
reading_format.py                     # 纯展示文本
```

### 6.2 可独立复用的边界（便于测试）

| 模块 | 应能独立运行/单测 |
|------|-------------------|
| `tv_messages` + `tv_link` | 无 GUI，`udp_sender_test` 式脚本发 JSON |
| `bp_protocol.FrameParser` | 已有，继续用 hex fixture 测 |
| `reading_format` | 输入数字 → 断言文本与 JSON 字段一致 |
| `measure_fsm` | mock backend，模拟 START→进度→结果 |

### 6.3 配置拆分

| 文件 | 内容 |
|------|------|
| `devices.json` | 蓝牙设备档案（已有） |
| **gateway.json**（新建） | `tv_ip`, `tv_mode`, `protocol_stage`, `text_mode`, `script_ip`, `ports`, `no_broadcast` |

启动时：`device_profile` 与 `gateway` 分离，避免 TV 联调参数写进设备档案。

---

## 7. 功能升级清单

### 7.1 TV / 网关功能

| 功能 | 现状 | 升级后 |
|------|------|--------|
| 网关发现 | 无 / 偶发 READY 文本 | 周期 `SCRIPT_READY` JSON |
| 心率推 TV | F1 文本 | + `HEART_RATE_STREAM` ~1Hz |
| 血压就绪 | 无 | `DEVICE_READY` / `DEVICE_OFFLINE` |
| TV 触发测压 | `START` @18500 | + `START_MEASURE`；P0 @18501 |
| 测量 ACK | 无 | P0 立即 `ACK` |
| 取消测量 | 无 | 收 `CANCEL_MEASURE` → `send_stop` |
| 错误上报 | 仅日志 | `MEASURE_ERROR` + error_code |
| 测试连接 | PING 文本 | + JSON `PING` 或保留文本 |

### 7.2 BLE / 设备功能

| 功能 | 现状 | 升级 |
|------|------|------|
| 瑞光血压 | 完整 | 保持；连接成功触发 `DEVICE_READY` |
| 标准心率 | 0x180D | 保持；不支持设备档案标 `vendor` |
| 预连接池 | 已有 | 池内 BP 就绪后自动 `DEVICE_READY` |
| 批量 FFF0 探测 | 已有 | 探测成功可选「一键加入池并设 BP」 |
| 体脂秤 | 占位 | P2 单独立项 |
| 多 BP 同台 | 理论支持多 session | UI 标明「当前 TV 测量用哪台」 |

### 7.3 工程师 / 运维功能

| 功能 | 说明 |
|------|------|
| 协议抓包日志 | 每条 UDP 显示 port、type、request_id |
| 导出联调包 | 一键复制最近 N 条 TV 报文 |
| CLI 参数 | 模拟器：`--tv-ip 127.0.0.1 --no-broadcast`（见 pc_gateway §3.6.4） |
| 版本号 | 窗口标题或关于框显示 `gateway` 阶段与 git 版本 |

---

## 8. UI 升级方案

### 8.1 布局调整（在现网四区基础上增强）

**原则：** 不推翻四区；在 **区域 4 GlobalBar** 与 **区域 3 Tab** 增加「产品联调」能力，调试能力默认折叠。

```text
┌──────────────────────────────────────────────────────────────┐
│ 区域1 设备池  │ 区域2 会话  │ 区域3 功能（Tab）                │
│               │             │  · 连接设置                      │
│               │             │  · 业务操作（HR/BP）               │
│               │             │  · 预连接池                        │
│               │             │  · 【新】TV 联调（协议阶段、报文预览）│
├──────────────────────────────────────────────────────────────┤
│ 区域 日志（【新】分 Tab：运行 / TV 协议 / BLE 调试）              │
├──────────────────────────────────────────────────────────────┤
│ 区域4 全局：阶段[L0|T0|P0] · TV IP · 端口 · 双发开关 · 状态灯   │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 区域 4（GlobalBar）新增控件

| 控件 | 作用 |
|------|------|
| **协议阶段** | `L0` / `T0` / `P0` 下拉；切换时提示 listen 端口变化 |
| **script_ip** | 自动检测本机 LAN IP，可手动改（模拟器填说明链接） |
| **listen_port 显示** | T0: 18500；P0: 18501（只读，来自阶段） |
| **JSON + 文本双发** | T0 默认开；L0 仅文本 |
| **禁用广播** | `--no-broadcast`；模拟器联调默认建议开 |
| **18501 状态** | 绿/红：B 信道是否 bind 成功 |
| **最近 request_id** | P0 测量时显示，便于和 TV 日志对照 |

### 8.3 区域 3 新 Tab「TV 联调」

| 区块 | 内容 |
|------|------|
| 报文预览 | 最近 20 条发出的 JSON（格式化） |
| 手动发 SCRIPT_READY | 测试 TV 是否缓存网关 |
| 模拟 TV 发 START | 本地注入 `START_MEASURE`（不依赖 TV APK） |
| 联调说明链接 | 跳转本文档 / AS 测试方案章节 |

### 8.4 区域 3 业务面板微调

**血压 `BPBusinessWidget`：**

- 进度条与 `MEASURE_PROGRESS.progress` 同源（PC 算 progress，UI 与 TV 一致）；
- 显示当前 `phase`（加压/减压/分析）；
- 「推送血压到 TV」在 T0+ 改为「推送 JSON（含文本）」勾选说明。

**心率 `HRBusinessWidget`：**

- 显示「JSON 推流」状态（1Hz 计数）；
- 不支持 0x180D 时显示档案建议（换设备 / 标 vendor）。

### 8.5 日志区 Tab 化

| Tab | 内容 |
|-----|------|
| 运行 | 现有用户向日志 |
| TV 协议 | `[18500→] SCRIPT_READY ...` / `[18501←] START_MEASURE ...` |
| BLE 调试 | 可选：帧 hex（默认关，避免初学者困惑） |

### 8.6 视觉与可用性（P2）

- 会话表增加「TV 角色」列：当前哪台 BP 作为 `DEVICE_READY` 源；
- 状态栏显示：已连接数 / 池内数 / 当前阶段 / TV 目标 IP；
- 深色主题可选（长时间联调）。

---

## 9. 交互升级方案

### 9.1 用户角色与场景

| 角色 | 主要场景 | 交互目标 |
|------|----------|----------|
| 工程师 | 实验室联调 TV | 阶段可切换、报文可见、可模拟 START |
| 运维 | 家庭现场部署 | gateway.json 一次配置、预连接池自动连 |
| TV 用户 | 不直接操作 PC | PC 后台稳定发 READY/HR；OK 测压走 P0 |

### 9.2 关键交互流升级

#### 流 A：开机自动网关（运维）

```text
启动 GUI → 读 gateway.json → 协议阶段 T0/P0
  → 自动 start TvLink → 周期 SCRIPT_READY
  → 若开预连接池 → 扫描 → 自动连 BP/手环
  → BP 连接成功 → DEVICE_READY（TV 血压入口亮）
```

**现网缺口：** 无 SCRIPT_READY；DEVICE_READY 无；需用户手动点多处开关。

**升级：** 「开机即网关」总开关（默认关，避免误广播）；与预连接池 `auto_connect` 联动。

#### 流 B：TV 遥控器测血压（产品 P0）

```text
TV OK → START_MEASURE@18501
  → PC ACK → UI 显示 request_id + 进入测量中
  → 加压 → UI 进度环 + MEASURE_PROGRESS@18501
  → 结果 → MEASURE_RESULT → UI 结果区 + 可选 F1 文本@18500
  → FSM 回 Idle → 可再收下一次 START
```

**现网：** 仅「TV 联动模式」+ `START@18500` + 文本结果。

#### 流 C：工程师本地测（不依赖 TV）

保持区域 3「开始测量」；P0 阶段本地按钮应走 **同一 FSM**，避免「按钮路径」和「TV 路径」两套逻辑。

#### 流 D：模拟器联调（与 TV 同事协作）

1. TV 同事：`adb forward udp:18500/18501`；
2. PC：`TV IP = 127.0.0.1`，勾选禁用广播；
3. `SCRIPT_READY.script_ip` 在文档中说明模拟器侧填 `10.0.2.2`（TV 发回 PC）；
4. 详见 [AndroidStudio双信道测试方案 §2.5](./AndroidStudio双信道测试方案.md)。

### 9.3 交互细节优化

| 问题（现网） | 优化 |
|--------------|------|
| 加压日志刷屏 | PROGRESS 节流；运行日志合并为「当前压力」标签更新 |
| 扫描与连接冲突 | 连接中暂停自动刷新（已有）；UI 明确「扫描已暂停」 |
| TV 无反应不知哪端问题 | TV 联调 Tab 显示「上次收到 TV 包」时间与内容 |
| 阶段混用导致误判 | 切换 P0 时若 18501 未监听，弹窗阻断并说明 |
| 多台 BP | 测压前会话表选「TV 默认 BP」或自动选最近连接的 BP |

### 9.4 错误与提示文案

统一经 `reading_format` 或消息层输出用户可读句，并映射 `MEASURE_ERROR`：

| 场景 | UI 提示 | TV error_code |
|------|---------|---------------|
| 蓝牙断开 | 血压计已断开 | `DISCONNECTED` |
| 电量不足 | 电量过低，请更换电池 | `LOW_BATTERY` |
| 测量超时 | 测量超时 | `TIMEOUT` |
| 正在测压又收 START | 忽略并回 BUSY | `BUSY` |

---

## 10. 代码改动映射（实施 checklist）

### 10.1 R0 准备（建议第 1 迭代）

- [ ] 新建 `gateway.json` + `GatewayConfigStore`
- [ ] 新建 `GatewayController`，从 `bp_demo_app` 迁出 TV 推送逻辑
- [ ] `GlobalBar` 增加协议阶段、script_ip、禁用广播
- [ ] `run_gui.py` 增加 CLI 参数解析
- [ ] 日志 Tab：运行 / TV 协议

### 10.2 T0 迭代

- [ ] 新建 `tv_messages.py`
- [ ] `tv_link` 支持 `send_json(type, **fields)` + 可选 text 双发
- [ ] 定时 `SCRIPT_READY`（60s）
- [ ] BP 连接/断开 → `DEVICE_READY` / `DEVICE_OFFLINE`
- [ ] HR → `HEART_RATE_STREAM`（节流 1Hz）
- [ ] 测量过程 → `MEASURE_PROGRESS`；结束 → `MEASURE_RESULT`
- [ ] `wait_for_start` 识别 `START_MEASURE`（仍可在 18500）
- [ ] 验收：[AS 方案 T0 用例](./AndroidStudio双信道测试方案.md)

### 10.3 P0 迭代

- [ ] `tv_link` 第二 socket `bind 0.0.0.0:18501`
- [ ] 新建 `measure_fsm.py`，接入 `multi_ble_backend`
- [ ] `START_MEASURE` → `ACK` → 进度/结果走 `reply_to`
- [ ] `CANCEL_MEASURE` → `send_stop` + `MEASURE_ERROR` 或静默回 Idle
- [ ] `SCRIPT_READY.listen_port = 18501`
- [ ] 18500 仍 listen 一段时间（兼容 Legacy START）
- [ ] 验收：[AS 方案 P0 / §8 机顶盒清单](./AndroidStudio双信道测试方案.md)

### 10.4 P1 打磨

- [ ] PROGRESS 节流、MEASURE_ERROR 全集
- [ ] 托盘、gateway 版本号
- [ ] CLI 与 GUI 共用 FSM

---

## 11. 分阶段验收标准（PC 侧）

完整操作表见 **[PC网关升级测试验收清单.md](./PC网关升级测试验收清单.md)**。

---

## 12. 风险、依赖与不回退项

| 风险 | 缓解 |
|------|------|
| TV 产品 UI 未发 18501 | PC T0 先在 18500 收 `START_MEASURE`；P0 双 listen |
| Windows 防火墙拦 UDP | 文档 + 安装脚本提示放行 18500/18501 |
| bleak / WinRT 不稳定 | 保持扫描连接互斥；不为了 P0 改 BP 裸连接策略 |
| 模拟器 UDP 不可靠 | 协议验收以真机为准；PC 提供 `--tv-ip 127.0.0.1` |
| TV 与 PC 字段不一致 | 以 [通讯格式文档](./通讯格式文档.md) 为单一字段源；改 type 先改文档 |
| MainWindow 继续膨胀 | R0 必须引入 `GatewayController` |

**建议不回退项：** 血压/心率 **分路径** BLE 策略（见 [功能与实现分析 §7](./PC网关脚本功能与实现分析.md)）；`devices.json` 档案模型。

---

## 13. 推荐排期（参考 pc_gateway §9）

| 周次 | PC 交付 | 文档 / 联调 |
|------|---------|-------------|
| W1 | R0 + T0-1～T0-3（READY + HR JSON） | AS 方案阶段 1、3 |
| W2 | T0-4～T0-7（BP JSON + 双发） | AS Legacy/T0 |
| W3 | P0 18501 + FSM + ACK/PROGRESS/RESULT | AS P0 阶段 4 |
| W4 | 真机血压 + 错误处理 + P1 项 | AS §8 机顶盒清单 |

TV 端 `DEVICE_READY` 接线、产品 OK 发送可与 W2～W3 并行，但 **P0 端到端验收依赖双方同时就绪**。

---

## 14. 修订记录

| 版本 | 日期 | 变更 |
|------|------|------|
| **v1.0** | 2026-06 | 初版：UI/交互/功能/协议/优先级全量升级方案 |
