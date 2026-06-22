# Android Studio 双信道开发测试方案（v1.1）

## 1. 文档说明

本文档说明如何在 **Android Studio（AS）** 中完成 **信道 A（18500）** 与 **信道 B（18501）** 的联调与模拟测试，**全部验证通过后再部署机顶盒**。

**关联文档（三份配套）：**

| 文档 | 角色 |
|------|------|
| [udp_信道设计.md](./udp_信道设计.md) | 协议与能力矩阵（**设计基准**） |
| [pc_gateway升级方案.md](./pc_gateway升级方案.md) | PC 脚本 L0→T0→P0（**现网 vs 目标**） |
| [通讯格式文档.md](./通讯格式文档.md) | UDP **包体格式**、字段样例（**格式字典**） |
| **本文档** | 怎么测、用什么环境、验收表（**操作手册**） |
| [PC网关脚本功能与实现分析.md](./PC网关脚本功能与实现分析.md) | 现网 `pc_ble_client` 能力与限制（**真机联调前必读**） |

**原则：** AS 里可用 **PC 模拟网关（mock）** 替代真实脚本做 P0 协议验收；接 **真实 PC 脚本**（`pc_ble_client`）时按 **L0/T0** 分层验收，勿一上来按 P0 硬卡。真脚本行为以 [PC网关脚本功能与实现分析](./PC网关脚本功能与实现分析.md) 为准。

**其它关联：**

| 文档 | 内容 |
|------|------|
| [心率测试方案.md](./心率测试方案.md) | 心率 UI 与 30s 会话 |
| [血压测试方案.md](./血压测试方案.md) | 血压 START → RESULT 闭环 |
| [DataMonitoring.md](./DataMonitoring.md) | TV 端现有 UDP 实现 |

---

## 1.1 按协议阶段怎么测（L0 / T0 / P0）

联调前先确认 **测的是哪一阶段**，避免「TV 按 P0 验、PC 还是 L0 文本」对不上。

| 阶段 | PC 侧典型形态 | 推荐测试工具 | TV 侧预期 | 本文用例章节 |
|------|---------------|--------------|-----------|--------------|
| **L0** | `pc_ble_client` 纯文本、**仅 18500**、双向 | **真 PC 脚本** + 真机 | 控制台文本行；START→18500 | §5.6 |
| **T0** | PC 18500 发 JSON（可双发文本） | mock 或 **升级中 PC 脚本** | 角标/图表吃 JSON；START 仍可 18500 | §5.1–§5.4（部分） |
| **P0** | 18500 A + **18501 B** 闭环 | **mock_gateway** 或 P0 PC | OK→`START_MEASURE`→ACK→RESULT | §5.2、§5.4、§5.5 |

**TV App 现状（约 2026-06）：** 已监听 18500/18501；文本心率、`HEART_RATE_STREAM` 部分可用；血压 `DEVICE_READY` / `MEASURE_PROGRESS` / `MEASURE_RESULT` **产品 Controller 未全接**；血压 OK 发 `START_MEASURE` **产品 UI 未接线**。详见 [pc_gateway升级方案 §1.4](./pc_gateway升级方案.md)。

---

## 2. 测试环境选型

### 2.1 三种环境对比

| 环境 | 适用阶段 | 信道 A 广播 | 信道 B 单播 | 推荐度 |
|------|----------|-------------|-------------|--------|
| **AS 模拟器（AVD）** | UI、Logcat | 较差（UDP/组播受限） | 需 adb 转发 | 仅 UI |
| **AS + 真机（手机/平板，同 WiFi）** | **双信道主测** | 正常 | 正常 | **强烈推荐** |
| **机顶盒（最终部署）** | 验收 | 正常 | 正常 | 上线前最后一关 |

### 2.2 推荐路线

```
阶段 0  AS 模拟器     → 只看界面、图表、遥控器按键（无 UDP）
阶段 1  AS + 真机     → mock_gateway，测齐信道 A + B（P0 协议）
阶段 2  AS + 真机     → 接真实 PC 脚本 pc_ble_client（L0 文本 / T0 JSON）
阶段 3  机顶盒        → 同网段完整演示（P0 + 真实硬件）
```

**结论：** 双信道 UDP **不要在模拟器上硬扛**；用一台与 PC **同一 WiFi** 的 Android 真机代替机顶盒开发，成功率最高。

### 2.2.1 两种 PC 端对比（mock vs 真实脚本）

| 对比项 | mock_gateway | pc_ble_client（你的脚本） |
|--------|--------------|---------------------------|
| 用途 | TV 开发自测 **P0 JSON** | 真实蓝牙 + 网关 |
| 蓝牙 | 无，假进度/假结果 | 手环 + 瑞光血压计 |
| 端口 | 18500 发 + 18501 听 | **L0：仅 18500** |
| 格式 | JSON | **L0：纯文本行**；升级后 T0/P0 JSON |
| 何时用 | TV 未接 PC、验 P0 协议 | 验真实测压、验 L0 文本推送 |
| 文档 | 本文 §4 | [pc_gateway升级方案](./pc_gateway升级方案.md) |

### 2.3 网络拓扑（阶段 1–2）

```
┌──────────── PC（Windows） ────────────┐
│  mock_gateway.py                      │
│    发送 → 255.255.255.255:18500  (A)  │
│    监听 ← 真机IP:18501  (B)           │
│    回复 → 真机IP:18501  (B)           │
└──────────────────┬────────────────────┘
                   │ 同一 WiFi 路由器
┌──────────────────▼────────────────────┐
│  Android 真机（AS Run 安装 APK）       │
│    监听 18500、18501                   │
│    tv_heart_rate 控制台 + 图表         │
└───────────────────────────────────────┘
```

### 2.4 模拟器若必须用（仅 UI）

| 问题 | 说明 |
|------|------|
| 255.255.255.255 广播 | 模拟器内不一定等同于局域网广播 |
| MulticastLock | 模拟器行为与真机不一致 |
| PC → 模拟器 UDP | 需 `adb forward udp:18500 udp:18500`，**不稳定** |

**模拟器仅用于：** 布局、HeartRateTrendView 绘制、按键事件。UDP 通过 Logcat 确认时，仍建议换真机。

---

## 3. 前置准备

### 3.1 Android 工程

| 项 | 要求 |
|----|------|
| 权限 | 已声明 `INTERNET`、`ACCESS_WIFI_STATE`、`CHANGE_WIFI_MULTICAST_STATE`（见 `AndroidManifest.xml`） |
| 运行 | AS 点击 Run，安装到真机 |
| 页面 | 进入健康监测详情页（遥控器或鼠标点进 `layout_heart_rate`） |
| 控制台 | 观察 `tv_heart_rate` 日志输出 |

### 3.2 PC 端

| 项 | 要求 |
|----|------|
| Python | 3.8+（用于模拟网关，下文提供脚本） |
| 防火墙 | 允许 Python 入站/出站 UDP **18500、18501** |
| 查 PC IP | `ipconfig` → 如 `192.168.1.100`（记为 `PC_IP`） |
| 查真机 IP | 手机设置 → WLAN → IP，如 `192.168.1.50`（记为 `TV_IP`） |

### 3.3 真机与 PC 必须在同一网段

示例：PC `192.168.1.100`，真机 `192.168.1.50`，掩码 `255.255.255.0`。  
若 PC 开热点给手机连，也可，但需确认广播能到达。

---

## 4. PC 模拟网关（核心工具）

在 PC 上运行 **`mock_gateway.py`**，同时扮演：

- **信道 A：** 向 `255.255.255.255:18500` 发广播
- **信道 B：** 在 `18501` 监听 TV 的 `START_MEASURE`，再单播回 TV

**脚本存放建议：** `tools/mock_gateway.py`（实施时可创建；测试按下面内容自建即可）。

```python
#!/usr/bin/env python3
# mock_gateway.py — PC 端双信道模拟网关（开发测试用）
# 用法: python mock_gateway.py --pc-ip 192.168.1.100 --tv-ip 192.168.1.50

import argparse, json, socket, threading, time, uuid

PORT_A = 18500
PORT_B = 18501

def send_broadcast(pc_ip, payload):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    sock.sendto(data, ("255.255.255.255", PORT_A))
    # 同时单播一份到 TV，提高真机收到概率
    if "tv_ip" in globals() and TV_IP:
        sock.sendto(data, (TV_IP, PORT_A))
    sock.close()

def listen_channel_b():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT_B))
    print(f"[B] 监听 {PORT_B}，等待 TV 指令…")
    while True:
        data, addr = sock.recvfrom(4096)
        try:
            msg = json.loads(data.decode("utf-8"))
        except Exception:
            print(f"[B] 非 JSON 来自 {addr}: {data}")
            continue
        print(f"[B] 收到 {addr}: {msg}")
        handle_tv_command(sock, addr, msg)

def handle_tv_command(sock, tv_addr, msg):
    t = msg.get("type", "")
    req = msg.get("request_id") or str(int(time.time() * 1000))
    if t == "START_MEASURE":
        device = msg.get("target_device", "BP")
        reply_to = msg.get("reply_to") or {"ip": tv_addr[0], "port": tv_addr[1]}
        target = (reply_to["ip"], int(reply_to["port"]))
        # ACK
        ack = {"type": "ACK", "request_id": req, "message": f"{device} started"}
        sock.sendto(json.dumps(ack).encode(), target)
        if device == "BP":
            simulate_bp_measure(sock, target, req)
        else:
            print(f"[B] 忽略非 BP 设备: {device}")

def simulate_bp_measure(sock, target, req):
    for phase, prog in [("inflating", 30), ("inflating", 60), ("deflating", 80), ("analyzing", 95)]:
        time.sleep(1.5)
        p = {"type": "MEASURE_PROGRESS", "request_id": req, "device_category": "BP",
             "phase": phase, "progress": prog}
        sock.sendto(json.dumps(p).encode(), target)
    time.sleep(1)
    result = {"type": "MEASURE_RESULT", "request_id": req, "device_category": "BP",
              "payload": {"systolic": 120, "diastolic": 80, "pulse": 72,
                          "timestamp": int(time.time() * 1000)}}
    sock.sendto(json.dumps(result).encode(), target)
    print(f"[B] 已发送 MEASURE_RESULT → {target}")

def loop_channel_a(pc_ip):
    # 1. SCRIPT_READY
    send_broadcast(pc_ip, {
        "type": "SCRIPT_READY",
        "script_ip": pc_ip,
        "listen_port": PORT_B,
        "device_type": "BP",
        "devices": ["BP", "Band"]
    })
    print(f"[A] SCRIPT_READY (script_ip={pc_ip})")
    time.sleep(2)
    # 2. DEVICE_READY 血压
    send_broadcast(pc_ip, {"type": "DEVICE_READY", "device": "BP",
                           "device_name": "Mock-Omron", "timestamp": int(time.time() * 1000)})
    print("[A] DEVICE_READY(BP)")
    # 3. 心率流
    bpm = 70
    while True:
        send_broadcast(pc_ip, {
            "type": "HEART_RATE_STREAM",
            "timestamp": int(time.time() * 1000),
            "heart_rate": bpm,
            "device": "Band"
        })
        bpm = 68 + (bpm % 10)
        time.sleep(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--pc-ip", required=True, help="本机局域网 IP")
    parser.add_argument("--tv-ip", default="", help="真机 IP，建议填写")
    args = parser.parse_args()
    PC_IP = args.pc_ip
    TV_IP = args.tv_ip
    threading.Thread(target=listen_channel_b, daemon=True).start()
    loop_channel_a(PC_IP)
```

**启动命令（PowerShell，在项目根目录）：**

```powershell
python tools/mock_gateway.py --pc-ip 192.168.1.100 --tv-ip 192.168.1.50
```

将 IP 换成你的 `PC_IP`、`TV_IP`。

---

## 5. 分阶段测试用例

### 5.0 阶段 0：纯 UI（无 UDP）

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | AS Run 到模拟器或真机 | App 启动 |
| 2 | 进入健康监测详情页 | 长期心率图、控制台可见 |
| 3 | 不启动 mock_gateway | 控制台停留「正在监听 18500…」 |

**通过标准：** 界面与导航正常，不依赖网络。

---

### 5.1 阶段 1：信道 A 单测（发现 + 心率流）

**目的：** 验证 TV **只听 18500** 即可收到 PC 广播。

| 步骤 | 操作 | 预期（tv_heart_rate 或 Logcat） |
|------|------|--------------------------------|
| 1 | 真机安装 App，进入详情页 | 监听中 |
| 2 | PC 运行 mock_gateway | — |
| 3 | 等待 2s | `[发现] 脚本上线广播: 192.168.x.x` |
| 4 | 持续 | `[广播非标数据]` 或后续实现 `[HEART_RATE_STREAM]` 解析日志 |
| 5 | 停 mock_gateway | 日志停止增加 |

**Logcat 过滤：**

```
Tag: UDPReceiver
```

**AS 操作：** View → Tool Windows → Logcat → 下拉选真机 → 输入 `UDPReceiver`。

**当前代码注意：** 现版 `DataMonitoring` 对非 `SCRIPT_READY` 的 JSON 会打 `[广播非标数据]`；`HEART_RATE_STREAM` 属预期。协议解析按 [udp_信道设计.md](./udp_信道设计.md) 实现后，应变为结构化日志。

**通过标准：** 至少稳定收到 `SCRIPT_READY` 且 `script_ip` 正确。

---

### 5.2 阶段 2：信道 B 单测（TV 发 START → PC 回 RESULT）

**目的：** 验证 **18501 双向**；与信道 A 的 `script_ip` 衔接。

| 步骤 | 操作 | 预期 |
|------|------|------|
| 1 | mock_gateway 运行中，且已收到 SCRIPT_READY | scriptIp 已缓存 |
| 2 | **点击** `tv_heart_rate` 控制台 | 现版触发 `sendStartMeasureInstruction()` |
| 3 | PC 终端 | `[B] 收到 ... START_MEASURE` |
| 4 | TV 控制台 | `[发送] 指令 -> PC_IP:18501 ...` |
| 5 | TV 控制台 | `[接收] 18501返回: ... MEASURE_RESULT ...` |
| 6 | TV 控制台 | `[解析血压] 收缩压:120 舒张压:80 脉搏:72` |

**通过标准：** TV→PC→TV 闭环一次；不要求图表已接血压 UI。

**若发送失败「未发现可用脚本IP」：** 先确认阶段 1 的 SCRIPT_READY 已成功。

---

### 5.3 阶段 3：信道 A 心率域（实现后验收）

对照 [心率测试方案.md](./心率测试方案.md)：

| 用例 ID | 模拟方式 | 预期 UI |
|---------|----------|---------|
| HR-A1 | mock 持续 `HEART_RATE_STREAM` | 心率卡片角标「可测量」 |
| HR-A2 | 10s 无 stream | 角标熄灭 |
| HR-B1 | 焦点在心率卡片 + OK | 30s 倒计时、短期折线 |
| HR-B2 | 30s 结束 | 写 hr_history.json，长期图更新 |
| HR-B3 | 测量中 BACK | 取消，JSON 不变 |

**模拟：** mock_gateway 已含 1s 心率流；Ready/会话由 TV 端实现后逐项测。

---

### 5.4 阶段 4：信道 A+B 血压域（实现后验收）

对照 [血压测试方案.md](./血压测试方案.md)：

| 用例 ID | 信道 | 模拟方式 | 预期 |
|---------|------|----------|------|
| BP-A1 | A | `DEVICE_READY(BP)` | 血压卡片角标「可测量」 |
| BP-A2 | A | `DEVICE_OFFLINE(BP)` | 角标灭 |
| BP-B1 | B | OK → `START_MEASURE(BP)` | PC 打 ACK |
| BP-B2 | B | mock 发 PROGRESS | 加压动画/进度 |
| BP-B3 | B | mock 发 RESULT | 120/80，写 bp_history.json |
| BP-B4 | B | BACK → `CANCEL_MEASURE` | 取消（mock 需扩展） |
| BP-B5 | B | 无 ACK 5s | TV 提示「脚本无响应」 |

---

### 5.5 阶段 5：双信道联合场景（上线前必测）

| 场景 | 操作 | 预期 |
|------|------|------|
| **并行** | 心率流 + 血压 Ready 同时存在 | 两卡片角标独立，互不覆盖 |
| **先心率后血压** | 完成 30s 心率 → 再测血压 | 两 JSON 各写各的 |
| **先血压后心率** | 测完 BP → 再 OK 心率 | 会话不串 |
| **网关重启** | 停 mock 30s 再开 | TV 显示离线再上线 |
| **错网段** | PC 换 4G 热点不同网段 | 收不到，验证错误提示 |

---

### 5.6 阶段 L0：真实 PC 脚本（pc_ble_client）文本联调

**目的：** 验证 **现网 Legacy** 行为，与 P0 mock **分开验收**。

**前置：** PC 运行 `pc_ble_client`（`run_gui.py`）；蓝牙已连手环/血压计；TV 与 PC **同 WiFi**；底部 TV 推送配置为 **单播 TV_IP** 或广播。

| 步骤 | 操作 | 预期 |
|------|------|------|
| L0-HR | PC 勾选「推送心率到 TV」 | TV 控制台出现 `[xx:xx:xx] 心率: xx BPM` 文本行 |
| L0-BP | PC 勾选「推送血压到 TV」，开始测量 | 文本行：`加压中: xx mmHg` → `血压: xxx/xx mmHg，脉搏 xx BPM` |
| L0-START | TV 发 `START` 到 **PC_IP:18500**（工程师控制台） | PC 运行日志「收到 TV 端 START」；若 PC 开联动则开始测压 |
| L0-NEG | 用 P0 标准在 **18501** 发 `START_MEASURE` | **L0 PC 未 listen 18501 时无反应** — 属预期，非 bug |

**通过标准：** 文本信息流稳定；**不要求** JSON 图表、**不要求** 18501 ACK/PROGRESS。

**升级后（T0）：** 同一脚本在 18500 追加 JSON → 按 §5.1、§5.4 验收角标与图表。

---

## 6. Android Studio 操作速查

### 6.1 运行与调试

| 操作 | 说明 |
|------|------|
| Run `app` | 安装 Debug APK 到选中设备 |
| Logcat 过滤 `UDPReceiver` | 看 UDP 收发 |
| Breakpoint | 可打在 `DataMonitoring.handleBroadcastMessage`、`sendStartMeasureInstruction` |
| Network Inspector | 对 UDP 支持有限，**以 Logcat + PC 打印为准** |

### 6.2 现版可测功能（未实现产品 UI 前）

| 功能 | 如何测 | 信道 |
|------|--------|------|
| 发现脚本 | mock 发 SCRIPT_READY | A |
| 收心率 JSON | mock 发 HEART_RATE_STREAM | A |
| 发 START_MEASURE | **点击 tv_heart_rate** | B |
| 收血压结果 | mock 回 MEASURE_RESULT | B |

### 6.3 关于 Postman

Postman **不支持标准 UDP Request** 作为日常工具。双信道测试请用：

- **本方案 mock_gateway.py**（推荐）
- 或第三方 **Packet Sender**（Windows）、**netcat/ncat**

不推荐使用 Postman 测 UDP。

---

## 7. 模拟器专用：adb 转发（备选）

> 完整说明见 [pc_gateway升级方案 §3.6](./pc_gateway升级方案.md)。

仅当没有真机时尝试：

```powershell
adb forward udp:18500 udp:18500
adb forward udp:18501 udp:18501
```

PC 发往 `127.0.0.1:18500` / `18501`。  
**注意：** 部分 Android 版本 adb UDP 转发不可靠，失败则必须用真机。

---

## 8. 机顶盒部署前检查清单

全部在 **AS + 真机 + mock_gateway** 通过后，再刷机顶盒：

| 序号 | 检查项 | AS 真机 | 机顶盒 |
|------|--------|:-------:|:------:|
| 1 | SCRIPT_READY 发现 | □ | □ |
| 2 | HEART_RATE_STREAM 持续收 | □ | □ |
| 3 | START_MEASURE 发出 | □ | □ |
| 4 | MEASURE_RESULT 解析 | □ | □ |
| 5 | 心率 30s 会话 + JSON | □ | □ |
| 6 | 血压加压 UI + JSON | □ | □ |
| 7 | 两卡片角标独立 | □ | □ |
| 8 | onPause 关闭 Socket 无泄漏 | □ | □ |
| 9 | 同 WiFi 真实 PC 脚本（非 mock） | 可选（§5.6 L0） | □ |
| 10 | 遥控器 OK/BACK 全流程 | □ | □ |

**机顶盒与 AS 真机差异关注：**

| 项 | 说明 |
|----|------|
| 网口/WiFi | 确认与 PC 同网段；机顶盒常以太网 |
| 系统时间 | 影响「N月」写入 JSON |
| 遥控器 | 用真遥控器测 OK/BACK，不用鼠标 |
| MulticastLock | 机顶盒 ROM 必须保留现有权限 |

---

## 9. 常见问题

| 现象 | 原因 | 处理 |
|------|------|------|
| 完全收不到 18500 | 不同 WiFi / 防火墙 | 同网段；关 PC 防火墙试 |
| 只收到 SCRIPT_READY 无后续 | mock 未循环 | 检查 mock 是否在跑 |
| 点击控制台发送失败 | 未发现 scriptIp | 先测阶段 1 |
| 18501 收不到 RESULT | PC 回包地址错 | mock 用 TV 源地址或填 `--tv-ip` |
| `[广播非标数据]` | 现版未识别 HEART_RATE_STREAM | 正常，实现解析后消失 |
| 模拟器不通 | UDP 限制 | 换真机 |
| onPause 后不再收包 | 现版 stop 不 restart | 回前台重启 App 或后续 onResume 重连 |
| L0 脚本无 JSON 图表 | PC 仍为 text_mode | 按 §5.6 验文本；T0 后再验 JSON |
| TV OK 无 START_MEASURE | 产品 UI 未接线 | 用工程师控制台发 START；或等 TV U2 |

---

## 10. 测试交付物建议

实施阶段可在仓库中维护：

```
tools/
  mock_gateway.py      # PC 模拟网关
  send_once.py         # 可选：单条消息调试
docs/
  AndroidStudio双信道测试方案.md   # 本文档
```

**每个 Sprint 结束应能演示：**

1. AS 真机 + mock_gateway 跑通阶段 1、2  
2. 产品功能实现后跑通阶段 3、4、5 对应用例  
3.  checklist §8 全勾选后再交机顶盒  

---

## 11. 修订记录

| 版本 | 变更 |
|------|------|
| **v1.1** | §1.1 L0/T0/P0 测试分层；§2.2.1 mock vs pc_ble_client；§5.6 L0 真实脚本用例；文档三角链接；§9 FAQ 补充 |
| v1 | 初版：AS/真机/机顶盒三阶段；mock_gateway；分阶段用例；Postman 说明 |
