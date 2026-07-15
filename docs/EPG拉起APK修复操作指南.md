# EPG 拉起 APK 联调排查与修复手册

> **文档用途：** 供 EPG 运维、栏目配置、应用商城运营与 APK 开发方共同联调使用。  
> **关联文件：** `openApp.jsp`（已修正）、抓包 `医鸿错误代码10071抓包.pcapng`、分析文档 `EPG拉起APK错误10071与505分析.md`  
> **版本：** v2.0 | 2026-07-07

---

## 一、背景说明

### 1.1 业务目标

用户在机顶盒 EPG 页面点击入口后，应完成以下流程之一：

```text
【路径A：APK 已预装】  EPG → openApp.jsp → 直启 APK MainActivity
【路径B：APK 未预装】  EPG → openApp.jsp → 应用商城下载安装 → 再次点击直启
```

### 1.2 目标 APK 信息

| 配置项 | 当前值 | 说明 |
|--------|--------|------|
| 包名 | `com.iknet.bloodmeasuredemo` | 与 APK `applicationId` 一致 |
| 入口类 | `com.iknet.bloodmeasuredemo.MainActivity` | Manifest 中 MAIN/LAUNCHER |
| 应用商城包名 | `com.amt.appstore.gddx` | 广东电信应用商城，一般不改 |
| 商城 jumpId | `8` | 沿用原模板，需运营确认 |
| 商城 appId | `479` | **需运营确认是否已绑定新包名** |

> 以上参数在 `openApp.jsp` 顶部常量区统一配置，部署前只需改一处。

### 1.3 当前状态

| 项目 | 状态 |
|------|------|
| 机顶盒现象 | 报错 **10071**（页面访问超时无响应） |
| 抓包结论 | `openApp.jsp` 返回 **HTTP 500**，页面未加载成功 |
| APK 拉起 | **未执行**（JS 未运行到 `STBAppManager.startAppByIntent`） |
| JSP 脚本 | 开发方已修正逻辑，**待 EPG 侧部署** |

---

## 二、问题现象与根因（各方必读）

### 2.1 错误链路

```text
用户点击 EPG 入口
    ↓
机顶盒请求：GET /EPG/jsp/CNEPG/en/openApp.jsp
    ↓
EPG 服务器 JSP 执行失败 → HTTP 500 "accessed error"    ← 【当前卡在这里】
    ↓
机顶盒 WebView 拿不到正常页面
    ↓
机顶盒显示 10071「页面访问超时无响应」
    ↓
STBAppManager.startAppByIntent() 从未执行 → APK 不会拉起
```

### 2.2 错误码对照

| 看到的错误 | 实际含义 | 责任侧 |
|-----------|----------|--------|
| **10071** | 机顶盒提示「页面访问超时」，是表象 | 由 HTTP 500 引发 |
| **HTTP 500** | EPG 服务端 JSP 编译或执行异常 | **EPG 运维** |
| **505** | 本次抓包未出现 HTTP 505，可能是 500 误读 | — |

### 2.3 抓包证据摘要

**请求：**

```http
GET /EPG/jsp/CNEPG/en/openApp.jsp?userId=075540312817&&userId=075540312817&returnurl=... HTTP/1.1
Host: 125.88.42.87:33200
```

**响应：**

```http
HTTP/1.1 500 Internal Server Error
Content-Type: text/html; charset=UTF-8

页面正文：accessed error
```

**关键结论：**

- 对 `openApp.jsp` 仅 1 次请求，返回 500
- 无应用商城相关 HTTP 流量
- 无 APK 安装/拉起流量
- **问题在 EPG 页面加载阶段，不在 APK 本身**

---

## 三、各方职责

| 角色 | 负责内容 | 当前待办 |
|------|----------|----------|
| **EPG 运维** | JSP 部署、依赖文件、服务端日志、HTTP 500 修复 | **查日志、部署修正版 JSP** |
| **EPG 栏目配置** | EPG 入口链接、returnurl 参数 | 修正重复 userId 参数 |
| **应用商城运营** | 新包名上架、appId 绑定 | 确认 appId=479 是否对应新包名 |
| **APK 开发方** | 编译签名 APK、adb 预装联调 | 提供 APK 安装包 |

---

## 四、【EPG 运维】排查步骤

> 按顺序执行，上一步未通过不做下一步。

### 步骤 1：确认访问路径与部署路径一致

抓包显示机顶盒访问的是：

```text
/EPG/jsp/CNEPG/en/openApp.jsp
```

请在 EPG 服务器上确认：

```bash
# 示例：确认文件是否存在（路径按实际环境调整）
ls -l /path/to/EPG/jsp/CNEPG/en/openApp.jsp
```

**检查点：**

- [ ] 文件存在
- [ ] 文件权限可读
- [ ] 部署路径与 EPG 栏目配置的 URL 一致

> 若原厂模板路径为 `specialarea/yishiteng/openApp.jsp`，而实际访问的是 `CNEPG/en/openApp.jsp`，需统一：**要么改部署目录，要么改栏目链接，要么改 JSP 内 include 相对路径**。

---

### 步骤 2：检查 JSP 依赖文件是否齐全

`openApp.jsp` 依赖以下文件（从 `/EPG/jsp/CNEPG/en/` 出发，`../../../` 解析到 `/EPG/`）：

| 序号 | JSP 中的引用 | 服务器上应对应路径 |
|------|-------------|-------------------|
| 1 | `<%@ include file="../../../hwdatajsp/checkReport.jsp" %>` | `/EPG/hwdatajsp/checkReport.jsp` |
| 2 | `<jsp:include page="../../../util/passwordEncryption.jsp" />` | `/EPG/util/passwordEncryption.jsp` |
| 3 | `<script src="../../../js/report.js">` | `/EPG/js/report.js` |
| 4 | `<script src="../../../js/WkEpg.js">` | `/EPG/js/WkEpg.js` |
| 5 | `<script src="../../../config/config.js">` | `/EPG/config/config.js` |

**检查点：**

- [ ] 以上 5 个文件全部存在
- [ ] 路径大小写正确（Linux 环境区分大小写）

**缺任何一个 → JSP 执行异常 → HTTP 500。**

---

### 步骤 3：检查华为 EPG Java 类库

`openApp.jsp` 头部引用了：

```jsp
<%@ page import="com.huawei.iptvmw.epg.bean.info.UserProfile"%>
```

请在 EPG 应用容器的 `WEB-INF/lib` 中确认相关 jar 包存在。

**检查点：**

- [ ] `com.huawei.iptvmw.epg.bean.info.UserProfile` 类可加载
- [ ] JSP 容器为华为 IPTV EPG 标准环境（非普通 Tomcat 裸部署）

---

### 步骤 4：查服务端异常日志（最关键）

在机顶盒复现 10071 的同时，查看 EPG 服务器日志：

```bash
# 常见日志位置（按实际环境）
tail -f /path/to/tomcat/logs/catalina.out
tail -f /path/to/tomcat/logs/localhost.*.log
```

**重点搜索关键字：**

| 日志关键字 | 说明 | 处理方向 |
|-----------|------|----------|
| `FileNotFoundException` | include 文件找不到 | 补文件或改路径 |
| `ClassNotFoundException` | 华为 Java 类缺失 | 检查 WEB-INF/lib |
| `JasperException` | JSP 编译错误 | 检查 JSP 语法与标签库 |
| `NullPointerException` | 运行时空指针 | 检查 UserProfile、session 等 |

**请将完整异常堆栈反馈给开发方，便于精确定位。**

---

### 步骤 5：部署最小测试页验证环境

在 `openApp.jsp` 同目录新建 `openApp_test.jsp`：

```jsp
<%@ page language="java" pageEncoding="UTF-8"%>
<html>
<body>
<h3>EPG JSP 环境测试</h3>
<script>
  document.write("STBAppManager = " + typeof STBAppManager + "<br/>");
  document.write("Authentication = " + typeof Authentication + "<br/>");
</script>
</body>
</html>
```

机顶盒访问：

```text
http://125.88.42.87:33200/EPG/jsp/CNEPG/en/openApp_test.jsp
```

| 结果 | 判断 | 下一步 |
|------|------|--------|
| 仍 HTTP 500 | 容器/路径/权限问题 | 继续查日志 |
| HTTP 200，显示 `STBAppManager=object` | JSP 环境正常 | 部署正式 `openApp.jsp` |
| HTTP 200，但 `STBAppManager=undefined` | 在 PC 浏览器测的，非机顶盒环境 | 回机顶盒复测 |

---

### 步骤 6：修正 EPG 栏目入口链接（栏目配置同事）

抓包发现 URL 参数重复：

```text
错误：openApp.jsp?userId=075540312817&&userId=075540312817&returnurl=...
正确：openApp.jsp?userId=075540312817&returnurl=...
```

请栏目配置同事去掉多余的 `&userId=...`。

---

## 五、【EPG 运维】修复步骤

### 5.1 部署修正版 openApp.jsp

开发方已提供修正版，主要修复了：

| 修复项 | 原版问题 | 修正后 |
|--------|----------|--------|
| 包名判断 | `judgeApk()` 仍判断旧酷喵包 `com.video.ytlook_SZDX` | 改为判断目标包 `com.iknet.bloodmeasuredemo` |
| 包名配置 | 包名散落在多处，容易不一致 | 顶部常量 `APP_PACKAGE` 统一管理 |
| 直启方式 | 手拼 JSON 字符串 | 改用 `JSON.stringify()`，避免特殊字符出错 |
| 商城参数 | appPkg/appId 硬编码 | 抽出 `APP_STORE_APP_ID` 常量 |

**部署操作：**

```text
1. 备份服务器上现有 openApp.jsp
2. 上传开发方提供的 openApp.jsp（docs 目录下最新版）
3. 放到步骤1确认的正确目录（如 /EPG/jsp/CNEPG/en/）
4. 按平台要求重启服务或清理 JSP 编译缓存
5. 机顶盒复测
```

**部署后无需改代码的情况：** 当前 JSP 已配置为 `com.iknet.bloodmeasuredemo`，与开发方 APK 一致。

---

### 5.2 openApp.jsp 业务分支说明（便于运维理解日志）

```text
机顶盒打开 openApp.jsp（onload 自动执行 openApp()）
    │
    ├─【分支1】高清盒子（fn_checkSTB=true）
    │     → 跳转 guide.jsp 提示页
    │
    ├─【分支2】未安装应用商城（com.amt.appstore.gddx）
    │     → 跳转 guide2.jsp 提示页
    │
    ├─【分支3】商城已装，目标 APK 未装（judgeApk=false）
    │     → STBAppManager 打开应用商城，传 appPkg + appId 下载
    │
    └─【分支4】目标 APK 已装（judgeApk=true）
          → STBAppManager 直启 com.iknet.bloodmeasuredemo.MainActivity
```

---

### 5.3 阶段通过标准

| 阶段 | 通过标准 | 验证方式 |
|------|----------|----------|
| **阶段1：页面加载** | `openApp.jsp` 返回 HTTP **200**，机顶盒不再报 10071 | Wireshark 或浏览器开发者工具 |
| **阶段2：APK 直启** | 机顶盒已预装 APK，点击入口能打开应用 | 肉眼观察 + adb |
| **阶段3：商城下载** | 卸载 APK 后，点击入口能打开商城并下载 | 肉眼观察 |
| **阶段4：正式验收** | 复抓包确认全链路正常 | Wireshark |

---

## 六、【APK 开发方】需配合事项

### 6.1 提供安装包

- 包名：`com.iknet.bloodmeasuredemo`
- 入口：`com.iknet.bloodmeasuredemo.MainActivity`
- 提供 debug 或 release 签名 APK 供联调

### 6.2 adb 预装验证（EPG 页面 200 后执行）

```bash
# 连接机顶盒
adb connect <机顶盒IP>

# 安装 APK
adb install -r app-release.apk

# 确认包名
adb shell pm list packages | grep iknet

# 手动测试能否启动（不经过 EPG）
adb shell am start -n com.iknet.bloodmeasuredemo/.MainActivity
```

手动能启动 + EPG 点击不能启动 → 问题在 JSP/EPG 侧。  
手动也不能启动 → 问题在 APK 侧。

---

## 七、【应用商城运营】需配合事项

仅「未预装 → 走商城下载」分支需要：

| 需提供 | 当前值 | 说明 |
|--------|--------|------|
| 包名 | `com.iknet.bloodmeasuredemo` | 商城后台登记 |
| APK 文件 | 开发方提供 | 签名 release 包 |
| jumpId | `8` | 沿用原模板，请确认是否仍有效 |
| appId | `479` | **请确认是否已绑定新包名，否则需换新 appId** |

运营确认 appId 后，告知 EPG 运维是否需要修改 `openApp.jsp` 顶部 `APP_STORE_APP_ID`。

---

## 八、联调验收清单（签字用）

### 8.1 EPG 侧验收

| 序号 | 检查项 | 期望结果 | 通过 |
|------|--------|----------|:----:|
| 1 | `openApp.jsp` 文件已部署到正确目录 | 文件存在 | □ |
| 2 | 5 个依赖文件齐全 | 全部存在 | □ |
| 3 | 访问 `openApp.jsp` HTTP 状态码 | **200**（非 500） | □ |
| 4 | 机顶盒不再报 10071 | 无超时提示 | □ |
| 5 | `openApp_test.jsp` 显示 STBAppManager=object | 环境正常 | □ |
| 6 | EPG 入口链接无重复 userId | URL 参数正确 | □ |

### 8.2 APK 拉起验收

| 序号 | 检查项 | 期望结果 | 通过 |
|------|--------|----------|:----:|
| 7 | 机顶盒已安装应用商城 | `com.amt.appstore.gddx` 存在 | □ |
| 8 | 机顶盒已预装目标 APK | `com.iknet.bloodmeasuredemo` 存在 | □ |
| 9 | EPG 点击入口，APK 正常打开 | 进入 MainActivity | □ |
| 10 | 退出 APK 后回到 returnurl 页面 | 返回正常 | □ |
| 11 | （可选）卸载 APK 后走商城下载 | 商城能下载安装 | □ |

---

## 九、常见问题速查

| 现象 | 可能原因 | 处理方 | 处理办法 |
|------|----------|--------|----------|
| 机顶盒 10071 | openApp.jsp 返回 500 | EPG 运维 | 查服务端日志，补依赖文件 |
| HTTP 500 + FileNotFoundException | include 路径错误 | EPG 运维 | 对照第四节步骤2补文件 |
| HTTP 500 + ClassNotFoundException | 华为类库缺失 | EPG 运维 | 检查 WEB-INF/lib |
| 200 但跳 guide2.jsp | 未装应用商城 | 机顶盒预装 | 安装 `com.amt.appstore.gddx` |
| 200 但跳 guide.jsp | 高清盒子被拦截 | EPG 开发 | 确认 fn_checkSTB 逻辑 |
| 打开商城但找不到应用 | appId 未绑定新包名 | 商城运营 | 更新后台 appId |
| 200 但 APK 不启动 | 包名/类名与 APK 不一致 | 开发方 | 核对 APP_PACKAGE 常量 |
| 启动后闪退 | APK 自身崩溃 | 开发方 | `adb logcat` 查崩溃栈 |

---

## 十、建议联调顺序

```text
第1天  EPG 运维：查 500 日志 → 补依赖 → 部署 openApp_test.jsp → 确认 200
第2天  EPG 运维：部署修正版 openApp.jsp
       开发方：  adb 预装 APK
       双方：    联调「已预装直启」分支
第3天  商城运营：确认 appId
       双方：    联调「商城下载」分支（如需要）
第4天  双方：    Wireshark 复抓包 → 填写第八节验收清单
```

---

## 十一、附件清单

| 文件 | 说明 | 提供方 |
|------|------|--------|
| `openApp.jsp` | 修正版 EPG 拉起脚本（待部署） | 开发方 |
| `医鸿错误代码10071抓包.pcapng` | Wireshark 抓包原始文件 | 开发方 |
| `EPG拉起APK错误10071与505分析.md` | 详细技术分析 | 开发方 |
| `app-release.apk` | 签名安装包 | 开发方提供 |

---

## 十二、联系方式与反馈

联调过程中请反馈以下信息，便于快速定位：

```text
1. 复现时间（精确到分钟）
2. EPG 服务器日志中的完整异常堆栈
3. 机顶盒型号 / STBType
4. openApp.jsp 实际部署路径
5. Wireshark 中 openApp.jsp 的 HTTP 状态码
```

---

## 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-07-07 | 初版操作指南 |
| v2.0 | 2026-07-07 | 重构为 EPG 联调手册，明确各方职责与排查/fix 步骤 |
