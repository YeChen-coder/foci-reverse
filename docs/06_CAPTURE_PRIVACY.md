# 06. 抓包隐私与脱敏

## 1. 结论先行

不要公开原始 Android bugreport、原始 btsnoop、完整 logcat 或手机 UI dump。

公开包中的 `.btsnoop` 是重新生成的隐私处理文件，不是原始手机文件的改名副本。
它们仅保留与 FOCI 协议研究有关的 ATT PDU。

## 2. 原始文件为什么危险

Android HCI snoop 位于手机蓝牙主机与控制器之间。启用 full 模式后，它可能同时记录：

- FOCI；
- 耳机、手表、汽车、键盘和其他 BLE 设备；
- 手机与设备的地址；
- 配对与安全管理流量；
- 音频、电话簿、通知等 profile 数据；
- GATT 中的健康、位置或账户相关内容；
- 精确连接时间。

bugreport 的范围更大，可能额外包含：

- 手机序列号、型号、系统构建；
- 已安装包、系统服务状态；
- Wi-Fi、运营商和网络状态；
- 通知、崩溃记录和部分 App 日志；
- 文件路径与账户标识。

logcat 还可能记录其他 App 在同一时间的日志。即使你只操作 FOCI，也不代表日志只包含
FOCI。

Android 官方也把 HCI snoop 作为调试数据处理，而不是面向公开发布的数据：

<https://source.android.com/docs/core/connect/bluetooth/verifying_debugging>

## 3. 本公开包排除了什么

没有复制：

- 两个原始 Android bugreport ZIP；
- 原始 btsnoop 环形日志；
- 完整 logcat；
- `dumpsys bluetooth_manager`；
- Developer Options / UIAutomator XML；
- 手机截图；
- PC 运行日志和 PID；
- 官方 APK、DEX、资源与反编译目录；
- `foci.local.json`；
- 真实 Windows 用户路径；
- 真实手机序列号、蓝牙地址、运营商或账户信息。

## 4. 公开 btsnoop 的生成步骤

`tools/sanitize_foci_btsnoop.py` 的流水线：

### 4.1 解析 btsnoop

读取 H4 记录，重组 HCI ACL 和 L2CAP。只考虑固定 ATT CID `0x0004`。

### 4.2 找到 FOCI 连接窗口

在 ATT characteristic value 中重组以 `0xFE` 开头的合法 FOCI outer frame。
以连续帧的时间聚类识别 FOCI session，保留每个 session 前后很短的 GATT 建连窗口。

### 4.3 删除其他层与其他设备

输出只含目标 session 的 ATT PDU。不保留：

- HCI advertising/scan report；
- connection complete/disconnect event；
- SMP；
- 非 ATT L2CAP；
- 其他连接 handle；
- 同一手机上的其他 Bluetooth profile。

### 4.4 规范化分片

原日志可能把一个 ATT PDU 拆成多个 HCI ACL fragment。公开文件将其规范化成：

```text
一条 H4 ACL record
  └── 一条 L2CAP ATT PDU
```

ATT 内容和顺序保留，底层 controller 分片边界不保留。这样更容易分析，也避免意外带入
同一 ACL 流中的无关 channel。

### 4.5 替换身份与认证

| 原字段 | 公开值 |
|---|---|
| UID | `0x1122334455667788` |
| Device MAC | `02:00:00:00:00:01` |
| Write key | 与上述合成 UID/MAC 一致的合成 fallback key |
| Connection handle | 每个 session 从 1 重新映射 |

正向和反向 MAC 字节都被替换。challenge 中的 key 与所有 inner frame 中的 UID
保持一致，因此协议结构仍可复现，但不能连接真实设备。

### 4.6 时间与位置弱标识

- btsnoop record 绝对时间统一平移到 `2025-01-01T00:00:00Z` 附近；
- 保留包间相对时间；
- 已知的 config/ping/application epoch 被改写；
- config timezone offset 被置 0；
- session 之间的相对间隔保留。

## 5. 仍然保留了什么

为了维持研究价值，公开文件仍包含：

- FOCI 固件/产品字符串；
- GATT handle 与 ATT opcode；
- outer/inner command、sequence 和 error；
- 配置 flags；
- 去标识化后的 realtime 状态和评分；
- 包之间的相对时间；
- 设备在这些 session 中状态变化的顺序。

其中实时状态属于行为/生理推断遥测。它已经去掉直接身份和绝对时间，但不能说“完全没有
个人数据含义”。如果研究只需要协议结构，可以只使用配置 CSV 或合成测试样本。

## 6. 自动审计

发布前执行：

1. 对所有二进制文件搜索真实 UID little-endian；
2. 搜索真实 write key little-endian；
3. 搜索真实 MAC 正序与逆序；
4. 对所有文本搜索 UID 十进制/十六进制、MAC、key、手机序列号和本机用户名；
5. 检查是否存在 `bugreport`、`logcat`、APK、DEX、SQLite、XML dump；
6. 用解析器重新解析公开 btsnoop；
7. 比较 FOCI frame 数量；
8. 检查 Git 忽略规则。

本包生成时，真实 UID/key/MAC 的二进制命中数均为 0。最终报告记录在
`PRIVACY_AUDIT.md`。

## 7. 安全边界与诚实限制

没有任何自动脱敏工具能对未知厂商 payload 做数学意义上的“零风险证明”。本项目的保证
建立在以下事实：

- 只输出目标连接 ATT；
- 已知身份/认证字段有结构化替换；
- 已知时间/时区字段有结构化替换；
- 原始系统文件完全不进入发布目录；
- 最终包做文本、二进制和文件类型审计。

仍可能存在一个尚未理解的 FOCI 私有字段，它编码了设备特有状态。公开前应阅读审计报告，
并理解公开数据仍含去标识化 FOCI telemetry。

## 8. 自己复现时的建议

- 在单独测试手机上抓包风险最低；
- 临时断开耳机、手表和汽车；
- 只开启 HCI snoop 所需时间；
- 操作结束立即关闭并重启蓝牙；
- 原始文件放在加密存储；
- 永远先运行 sanitizer，再准备 Git commit；
- 在 `git status` 和 GitHub 上传列表中逐项确认文件。
