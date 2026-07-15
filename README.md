# BlueToothDemo — 家庭端医疗健康蓝牙网关

[![GitHub](https://img.shields.io/badge/GitHub-BlueTooth__pc__terminal-blue)](https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal)
[![Release](https://img.shields.io/github/v/release/HUANGYIHAO382/BlueTooth_pc_terminal)](https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal/releases/latest)

本仓库是**家庭端医疗健康场景**下的蓝牙设备接入与联调工程，包含两部分：

| 子项目 | 技术栈 | 作用 |
|--------|--------|------|
| **PC 网关** `pc_ble_client/` | Python 3.10+ / PySide6 / bleak | Windows 桌面网关：连接血压计/手环，通过 UDP 向 TV 机顶盒推送数据 |
| **Android 血压计 Demo** `app/` + `baseble/` | Java / Android Gradle | 厂家参考 Demo：瑞光血压计 BLE 扫描、握手、测量（可独立在手机上运行） |

PC 端与 Android Demo **互不依赖**：PC 按厂家 PDF 与 Android Demo 对齐协议，日常联调 TV 时只需运行 PC 网关。

**不想装 Python？** 直接下载 [Releases 绿色版](https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal/releases/latest)，解压后双击 `PCBleGateway.exe` 即可（见下方「发布版」）。

---

## 目录

- [整体架构](#整体架构)
- [发布版（绿色 exe，推荐多数用户）](#发布版绿色-exe推荐多数用户)
- [从源码运行（PC 网关）](#从源码运行pc-网关)
- [快速开始（Android Demo）](#快速开始android-demo)
- [PC 网关功能说明](#pc-网关功能说明)
- [支持的设备与 BLE 协议](#支持的设备与-ble-协议)
- [TV 联动与 UDP 协议阶段](#tv-联动与-udp-协议阶段)
- [项目目录结构](#项目目录结构)
- [配置说明](#配置说明)
- [文档索引](#文档索引)
- [常见问题](#常见问题)
- [版本与维护](#版本与维护)

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        家庭局域网 (WLAN)                           │
│                                                                 │
│  ┌──────────────┐    BLE      ┌─────────────┐                   │
│  │ 瑞光血压计    │◄──────────►│             │   UDP 18500/18501 │
│  │ 心率手环      │◄──────────►│  PC 网关     │◄─────────────────►│ TV 机顶盒 App
│  └──────────────┘             │ pc_ble_client│                   │
│                               └─────────────┘                   │
└─────────────────────────────────────────────────────────────────┘

Android Demo（独立）：手机 ──BLE──► 瑞光血压计（参考实现，不参与上图 UDP 链路）
```

**数据流向简述：**

1. PC 通过蓝牙连接医疗设备，采集心率或血压数据；
2. PC 桌面 GUI 展示实时数值、协议日志、设备状态；
3. 勾选「推送到 TV」后，PC 将格式化后的数据经 **UDP** 发给局域网内的 TV App；
4. 联动模式下，TV 发送 `START` / `START_MEASURE`，PC 再触发真实血压测量。

---

## 发布版（绿色 exe，推荐多数用户）

适合：**不需要安装 Python**、只想拷贝即用的联调/演示人员。

| 项 | 说明 |
|----|------|
| 最新发布 | [v1.0.0](https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal/releases/tag/v1.0.0) / [全部 Releases](https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal/releases) |
| 下载文件 | `PCBleGateway-*-win64.zip`（Windows 64 位便携包） |
| 系统要求 | Windows 10/11，本机蓝牙支持 BLE；与 TV 联调时需同一局域网 |

### 如何下载并运行

```text
1. 打开 Releases 页面，下载最新的 PCBleGateway-*-win64.zip
2. 解压到任意目录（例如 D:\PCBleGateway\）
3. 双击 PCBleGateway.exe 启动
4. 若 Windows SmartScreen 提示「未知发布者」，选择「仍要运行」
```

直达：https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal/releases/latest

### 解压后目录说明

| 文件 / 目录 | 作用 |
|-------------|------|
| `PCBleGateway.exe` | 主程序，双击启动 |
| `gateway.json` | TV IP、端口、协议阶段等（可用记事本修改） |
| `devices.json` | 已保存的蓝牙设备档案 |
| `README.txt` | 英文简要说明 |
| `_internal\` | 运行库（勿删、勿单独移动 exe） |

**整份文件夹一起拷贝**到其他电脑即可，不要只拷贝单个 `.exe`。

### 首次使用（与源码版相同）

1. 打开 Windows 系统蓝牙；确保血压计/手环 **未被手机占用**；
2. 在界面扫描设备 → 右键标为「血压计」或「手环」→ 连接；
3. 底部栏填写 TV 的局域网 IP，勾选推送到 TV；
4. 开始测量，或等待 TV 发来的联动指令。

---

## 从源码运行（PC 网关）

适合：需要改代码、调试协议，或自行重新打包绿色版的开发者。

### 环境要求

| 项 | 要求 |
|----|------|
| 操作系统 | Windows 10/11（需开启系统蓝牙） |
| Python | **3.10 及以上**（推荐 3.12）；启动脚本会自动探测本机 Python |
| 网络 | PC 与 TV 在同一局域网（联调 UDP 时） |
| 硬件 | 支持 BLE 的蓝牙适配器；瑞光血压计或标准心率手环 |

### 方式一：一键启动（推荐）

```text
1. 进入目录 pc_ble_client/
2. 双击 setup_venv.bat        # 创建独立虚拟环境 .venv（不污染系统 Python）
3. 双击 start_pc_demo.bat     # 安装依赖并启动图形界面
```

脚本会优先使用项目内 `.venv`；若本机没有写死路径的 Python，也会通过 `py` 启动器或 PATH 自动查找 3.10+。

### 方式二：命令行启动

```powershell
cd pc_ble_client
.\setup_venv.ps1                              # 首次：创建虚拟环境
.\.venv\Scripts\python.exe run_gui.py         # 安装依赖 + 启动 GUI
```

可选：设置环境变量 `PC_BLE_PYTHON` 为某台机器上 `python.exe` 的完整路径，再运行 `setup_venv.ps1`。

### 方式三：模拟器联调模式

与 Android Studio 模拟器联调 TV 端时，可加 `--emulator` 参数（脚本 IP 默认 `10.0.2.2`）：

```powershell
.\.venv\Scripts\python.exe run_gui.py --emulator
```

### 自行打包绿色版（开发者）

```powershell
cd pc_ble_client
.\build_exe.ps1                # 完整打包（需已有 .venv）
# .\build_exe.ps1 -SkipBuild   # 仅重新拷贝默认配置并打 zip
```

产物在 `pc_ble_client/dist/`：可运行目录 `PCBleGateway\`，以及上传 Releases 用的 zip。

### 界面四区说明

启动后主窗口分为四个区域（见 `bp_demo_app.py` / `ui_panels.py`）：

| 区域 | 名称 | 功能 |
|------|------|------|
| 区域 1 | 设备池 | BLE 扫描、过滤、设备列表；右键可设置设备类型（血压计/手环） |
| 区域 2 | 会话 | 当前已连接设备（只读展示 MAC、角色、状态） |
| 区域 3 | 功能面板 | 连接设置 + 业务操作（按设备类型切换心率/血压 Tab） |
| 区域 4 | 底部栏 | 全局操作、TV 推送开关、协议阶段与 IP/端口配置 |

---

## 快速开始（Android Demo）

### 环境要求

- Android Studio（建议 Arctic Fox 及以上）
- Android SDK（`compileSdk` 见 `app/build.gradle`）
- 真机或模拟器（**BLE 功能需真机**）

### 编译运行

```text
1. 用 Android Studio 打开本仓库根目录（含 settings.gradle）
2. 等待 Gradle 同步完成
3. 连接真机，运行 app 模块
```

### 模块说明

| 模块 | 说明 |
|------|------|
| `app` | 血压测量 Demo 主程序（`MainActivity`、`BluetoothConnMeasureActivity` 等） |
| `baseble` | 第三方 BLE 基础库（ViseBle），封装扫描、连接、GATT 通道 |

Android 端协议细节见 [`docs/安卓SDK蓝牙扫描与握手说明.txt`](docs/安卓SDK蓝牙扫描与握手说明.txt) 与 [`docs/瑞光康泰家用血压计蓝牙通讯协议.pdf`](docs/瑞光康泰家用血压计蓝牙通讯协议.pdf)。

---

## PC 网关功能说明

### 核心能力

- **多设备 BLE 管理**：同时维护血压计（Server 角色）与心率手环（Client 角色）连接；
- **设备档案持久化**：`devices.json` 记录 MAC、类型、自动连接等，扫描时即可识别「已配置设备」；
- **瑞光血压计全链路**：扫描 → 握手 → 加压过程数值 → 最终结果（对齐厂家协议）；
- **标准心率服务**：使用 BLE SIG 标准 `0x180D` / `0x2A37` 读取 BPM；
- **TV UDP 推送**：纯文本（L0）或 JSON（T0/P0）双模式；
- **TV 联动测量**：TV 发 START 后 PC 触发血压测量，结果回推 TV；
- **测量状态机**：`measure_fsm.py` 管理 READY → MEASURING → RESULT 状态流转。

### 模块关系

```text
pc_ble_client/
├── run_gui.py              # 入口：检查 pip、安装依赖、启动 GUI
├── bp_demo_app.py          # 主窗口：四区 UI 总线与业务接线
├── ui_panels.py            # 四个区域的面板控件
├── multi_ble_backend.py    # 多设备 BLE 编排（BP + HR 分路径）
├── gateway_controller.py   # 网关编排：BLE 事件 → UI + TV + 状态机
├── gateway_config.py       # gateway.json 配置加载与持久化
├── measure_fsm.py          # 血压测量有限状态机
├── tv_link.py              # UDP 收发（广播/单播、双端口）
├── tv_messages.py          # TV 协议 JSON 消息构造
├── reading_format.py       # 心率/血压读数格式化
├── bp_protocol.py          # 瑞光血压计透传帧解析
├── hr_ble.py / hr_ble_backend.py  # 标准心率 BLE
├── device_profile.py       # devices.json 设备档案
├── ruiguang_bp_pc.py       # 命令行版：仅血压计单次测量
├── gateway.json            # 网关运行参数（协议阶段、端口、TV IP）
└── devices.json            # 已配对设备档案
```

技术栈：**PySide6**（界面）+ **qasync**（Qt 与 asyncio 合并）+ **bleak**（Windows WinRT BLE）。

---

## 支持的设备与 BLE 协议

### 瑞光家用血压计

| 项 | 值 |
|----|-----|
| 服务 UUID | 厂商透传 `FFF0`（128 位形式与 SIG 基底混排，代码内已做规范比较） |
| 特征 UUID | 写 `FFF2`、通知 `FFF1` |
| 角色 | BLE **Peripheral（Server）**，PC 作为 Central 连接 |
| 协议文档 | [`docs/瑞光康泰家用血压计蓝牙通讯协议.pdf`](docs/瑞光康泰家用血压计蓝牙通讯协议.pdf) |

### 心率手环 / 胸带

| 项 | 值 |
|----|-----|
| 服务 UUID | `0000180d-0000-1000-8000-00805f9b34fb`（标准心率服务） |
| 特征 UUID | `00002a37-0000-1000-8000-00805f9b34fb`（心率测量） |
| 角色 | PC 订阅通知，被动接收 BPM |
| 注意 | 设备类型须在界面标为「手环」，勿与血压计 MAC 混用 |

---

## TV 联动与 UDP 协议阶段

PC 与 TV 通过 **UDP** 通信，默认端口：

| 端口 | 用途 |
|------|------|
| **18500** | 信道 A：发现、遥测、Legacy 双向控制 |
| **18501** | 信道 B：P0 血压控制闭环（`START_MEASURE` → `ACK` → `PROGRESS` → `RESULT`） |

### 协议阶段对照

| 阶段 | 名称 | 行为摘要 |
|------|------|----------|
| **L0** | Legacy 纯文本 | 仅 18500；包体为中文可读行，如 `心率,72,2026-06-22 12:00:00` |
| **T0** | JSON 过渡 | 18500 发 JSON（`SCRIPT_READY`、`HEART_RATE_STREAM` 等）；可选保留文本 |
| **P0** | 双信道产品协议 | A=18500 发现/遥测；B=18501 血压测量闭环 |

当前网关默认配置见 `pc_ble_client/gateway.json`（`protocol_stage` 字段）。包体字段与样例详见 [`docs/通讯格式文档.md`](docs/通讯格式文档.md)。

### 联调地址参考

| 场景 | PC 脚本 IP | TV 目标 IP |
|------|------------|------------|
| 真机同网 | `ipconfig` 查看，如 `192.168.1.100` | TV 设置中的 WLAN IP |
| AS 模拟器访问宿主机 | — | TV 发往 `10.0.2.2:18500` |
| PC 发往模拟器 | `127.0.0.1`（配合 `adb forward`） | — |

---

## 项目目录结构

```text
BlueToothDemo/
├── README.md                 # 本文件
├── pc_ble_client/            # ★ PC 网关（Python 桌面程序）
├── app/                      # Android 血压计 Demo 主模块
├── baseble/                  # Android BLE 基础库
├── docs/                     # 设计文档、协议说明、测试方案
│   ├── 通讯格式文档.md
│   ├── udp_信道设计.md
│   ├── pc_gateway升级方案.md
│   ├── PC网关脚本功能与实现分析.md
│   ├── AndroidStudio双信道测试方案.md
│   └── ...
├── settings.gradle
└── build.gradle
```

---

## 配置说明

### `pc_ble_client/gateway.json` — 网关参数

```json
{
  "protocol_stage": "P0",
  "tv_mode": "unicast",
  "tv_ip": "255.255.255.255",
  "tv_unicast_ip": "127.0.0.1",
  "port_a": 18500,
  "port_b": 18501,
  "text_mode": false,
  "json_mode": true,
  "script_ip": "10.0.2.2",
  "auto_start_gateway": true
}
```

| 字段 | 说明 |
|------|------|
| `protocol_stage` | 协议阶段：`L0` / `T0` / `P0` |
| `tv_unicast_ip` | TV 单播地址（真机填 TV 的局域网 IP） |
| `script_ip` | PC 在 `SCRIPT_READY` 中广播的本机 IP |
| `text_mode` / `json_mode` | 是否发送文本行 / JSON 包 |

也可在 GUI 底部栏修改，保存后写回 `gateway.json`。

### `pc_ble_client/devices.json` — 设备档案

记录已扫描设备的 MAC、名称、类型（`bp` / `band`）、是否自动连接等。首次连接后自动更新，一般无需手改。

---

## 文档索引

| 文档 | 内容 |
|------|------|
| [PC网关脚本功能与实现分析.md](docs/PC网关脚本功能与实现分析.md) | 现网 PC 脚本模块、运行方式、L0 行为 |
| [通讯格式文档.md](docs/通讯格式文档.md) | UDP 包体格式字典（L0 文本 / JSON） |
| [udp_信道设计.md](docs/udp_信道设计.md) | 双信道架构、心率/血压能力拆分 |
| [pc_gateway升级方案.md](docs/pc_gateway升级方案.md) | L0 → T0 → P0 升级清单 |
| [AndroidStudio双信道测试方案.md](docs/AndroidStudio双信道测试方案.md) | 模拟器/真机联调步骤 |
| [PC网关升级测试验收清单.md](docs/PC网关升级测试验收清单.md) | 升级后验收项 |
| [项目结构与模块解耦说明.md](docs/项目结构与模块解耦说明.md) | 心率参考项目解耦思路 |
| [安卓SDK蓝牙扫描与握手说明.txt](docs/安卓SDK蓝牙扫描与握手说明.txt) | Android BLE 扫描与握手流程 |

---

## 常见问题

**Q：扫描不到设备？**  
确认 Windows 蓝牙已开启；设备未被手机占用；血压计处于可配对/广播状态。

**Q：连接报 `Unreachable`？**  
多为设备已被其他终端连接。关闭手机蓝牙 App 或断开连接后重试。

**Q：TV 收不到 UDP？**  
检查防火墙是否放行 UDP 18500/18501；确认 PC 与 TV 同网段；`gateway.json` 中 `tv_unicast_ip` 是否填对。

**Q：绿色版双击没反应 / 被拦截？**  
先看 Windows SmartScreen 是否拦截；杀毒软件可能误报。请保持 `_internal` 与 exe 在同一文件夹。仍不行可改用下方「从源码运行」。

**Q：`pip` 或 `bleak` 安装失败？**  
使用项目内 `.venv`，避免 Anaconda base 环境；或执行 `py -3.12 run_gui.py` 指定 Python 3.12。也可用环境变量 `PC_BLE_PYTHON` 指向正确的 `python.exe`。

**Q：手环 MAC 选了血压计角色？**  
心率服务 `0x180D` 与瑞光 `FFF0` 在 UUID 比较时易混淆，务必在设备池右键设置正确类型。

**Q：本仓库是 Vue 前端吗？**  
不是。PC 端为 **PySide6 桌面 GUI**，TV 端由团队单独开发；Android 部分为 Java 原生 Demo。

---

## 版本与维护

| 项 | 当前值 |
|----|--------|
| 公开发布 | **[v1.0.0](https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal/releases/tag/v1.0.0)**（Windows 绿色版首发） |
| 网关内部版本号 | `2.3.0`（见 `gateway_config.GATEWAY_VERSION`，与配置/协议演进对应） |
| 远程仓库 | https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal |
| 主分支 | `main` |

### Python 依赖（`pc_ble_client/requirements.txt`）

```
bleak>=0.21.0
PySide6>=6.5.0
qasync>=0.27.0
```

---

## 许可证

本仓库包含第三方 BLE 库（`baseble` / ViseBle）及厂家协议参考资料，商用前请自行确认设备授权与协议合规性。

如有问题或改进建议，欢迎在 [GitHub Issues](https://github.com/HUANGYIHAO382/BlueTooth_pc_terminal/issues) 反馈。
