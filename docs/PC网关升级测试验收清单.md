# PC 网关 P0 测试验收清单（v2.0 直接 P0）

默认交付为 **P0 双信道**（`gateway.json` → `protocol_stage: P0`）。L0/T0 仅工程师调试。

## 启动

```powershell
cd pc_ble_client
# 真机同 WiFi（默认 P0，开机自动 bind 18500+18501）
.\.venv\Scripts\python.exe run_gui.py

# Android Studio 模拟器 + adb forward
.\.venv\Scripts\python.exe run_gui.py --emulator
```

`--emulator` 等价于：`P0` + 单播 `127.0.0.1` + `script_ip=10.0.2.2` + 禁用广播。

TV 侧需执行：

```powershell
adb forward udp:18500 udp:18500
adb forward udp:18501 udp:18501
```

---

## P0 Gate（必过）

| # | 检查项 | 期望 |
|---|--------|------|
| G1 | 启动后底部 **B: 已监听** 为绿 | bind `0.0.0.0:18501` |
| G2 | TV 协议 Tab 见 `SCRIPT_READY` | `listen_port: 18501`，`script_ip` 为 PC 局域网 IP（模拟器为 `10.0.2.2`） |
| G3 | 连接血压计 | 信道 A 出现 `DEVICE_READY` |
| G4 | 勾选推送心率并连接手环 | 信道 A 出现 `HEART_RATE_STREAM`（约 1Hz） |
| G5 | TV 联调 → **模拟 START_MEASURE** | 日志 ACK；若已连 BP 则真实测压 |
| G6 | 测压过程 | **仅 B 信道** 出现 `MEASURE_PROGRESS` / `MEASURE_RESULT` |
| G7 | `request_id` | ACK、PROGRESS、RESULT 一致 |
| G8 | 真机 TV 发 `START_MEASURE@PC_IP:18501` | 完整闭环 |

---

## 信道职责（P0）

```
A · 18500  PC→TV
  SCRIPT_READY / HEART_RATE_STREAM / DEVICE_READY / DEVICE_OFFLINE

B · 18501  双向
  TV→PC  START_MEASURE / CANCEL_MEASURE
  PC→TV  ACK / MEASURE_PROGRESS / MEASURE_RESULT / MEASURE_ERROR
```

---

## 常见问题

| 现象 | 处理 |
|------|------|
| B 未监听 | 确认协议阶段为 P0；端口 18501 是否被占用 |
| TV 收不到 A 信道 | 真机填 TV IP 到「单播IP」；模拟器用 `--emulator` |
| START 发 18500 无反应 | **P0 预期行为**；应发 `START_MEASURE` 到 **18501** |
| 进度出现在 A | 非 P0 或旧配置；删 `gateway.json` 重启或手动选 P0 |

---

## 修订

| 版本 | 说明 |
|------|------|
| v2.0 | 对齐 pc_gateway升级方案 v2.0 直接 P0 |
