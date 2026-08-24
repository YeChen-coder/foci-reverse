# 05. 桌面客户端

## 1. 目录结构

```text
foci_ble/
├── cli.py          命令行入口与本地配置
├── client.py       Bleak 扫描、连接、GATT 收发和保活
├── protocol.py     outer/inner frame、解析器和配置构造
├── dashboard.py    aiohttp、本地 API、WebSocket 和设备状态
└── static/
    └── index.html  无构建步骤的本地仪表盘
```

辅助工具：

```text
tools/
├── analyze_foci_btsnoop.py
├── sanitize_foci_btsnoop.py
└── export_capture_datasets.py
```

## 2. 启动流程

真实仪表盘执行：

```text
读取 foci.local.json
        ↓
启动 127.0.0.1:8765 HTTP 服务
        ↓
页面显示“连接 FOCI”按钮
        ↓
用户点击按钮
        ↓
按地址查找设备，或扫描 FEE7 / 名称 FOCI
        ↓
BleakClient.connect()
        ↓
检查 FEE7 service
        ↓
订阅 FEC8 + FED8
        ↓
发送 native request
        ↓
发送 challenge
        ↓
启动约 20 秒保活任务
        ↓
解码实时流并经 WebSocket 推送到页面
```

HTTP 服务和设备连接已经解耦。服务器启动后不会自动占用 FOCI；用户点击按钮才会扫描、
连接、发送 challenge 并订阅实时流。连接失败时服务继续运行，页面显示可读错误并允许重试。

## 3. 本地配置

`foci.local.json` 示例：

```json
{
  "address": "YOUR_DEVICE_ADDRESS",
  "uid": 123456789,
  "write_key": "0x12345678"
}
```

文件被 `.gitignore` 排除。三个字段的敏感性：

| 字段 | 敏感性 | 原因 |
|---|---|---|
| address | 中 | 可用于设备跟踪和定向连接 |
| uid | 高 | 应用层身份，出现在每个 inner frame |
| write_key | 高 | challenge 所需，可授权写入 |

不要把真实值放进 issue、截图、终端录屏或 CI 日志。

## 4. FOCIClient

`FOCIClient` 负责：

- 设备发现；
- BLE 连接与服务检查；
- Notify/Indicate 订阅；
- 20 字节写入分片；
- outer frame 重组；
- challenge、配置和 ping；
- 断开时停止订阅与后台任务。

写入使用：

```python
await client.write_gatt_char(
    WRITE_CHAR,
    chunk,
    response=True,
)
```

`response=True` 对应 ATT Write Request，便于知道标准 GATT 写入是否被接受。
这不表示厂商业务命令一定成功；业务层错误仍可能在后续 inner frame 中返回。

## 5. 通知回调与重组

Bleak 回调收到 `(characteristic, bytearray)`。回调本身尽量轻量：

1. 按 characteristic 选择独立 `OuterFrameAssembler`；
2. 把 chunk 加进缓冲区；
3. 对每个完整 outer frame 调用 `decode_event()`；
4. 用 asyncio task 把事件交给上层。

FEC8 和 FED8 分别维护缓冲区，避免两个特征值的字节互相拼接。

## 6. Dashboard 状态

服务端保存：

- 最近一条 realtime event；
- 当前 default/session flags；
- 当前 Deep Work mode；
- 已连接 WebSocket 集合；
- 当前 FOCIClient；
- `disconnected / connecting / connected / error` 连接状态和最近一次错误。

页面初始加载时：

1. `GET /api/status` 读取当前控制状态；
2. WebSocket 接收实时样本；
3. 如果设备主动上报配置，再同步表单；
4. 普通实时样本只更新图表，不覆盖用户尚未保存的 checkbox。

第 4 点很重要：早期版本曾把配置附在每一条实时样本上，导致 checkbox 每 1–2 秒被旧值
覆盖。回归测试确保普通样本不再触发表单同步。

## 7. 本地 API

| Method | Path | 用途 |
|---|---|---|
| GET | `/` | 仪表盘 |
| GET | `/ws` | 实时 WebSocket |
| GET | `/api/status` | 连接与提醒设置 |
| POST | `/api/connect` | 扫描、认证并连接 FOCI；失败返回 JSON 错误 |
| POST | `/api/alerts` | 写默认或 Deep Work 提醒 |
| POST | `/api/deep-work` | 开始/结束设备 session mode |

提醒 API 示例：

```json
{
  "profile": "session",
  "alerts": {
    "distraction": true,
    "early_distraction": true,
    "focus_slip": false,
    "tense": false,
    "fatigue": false
  }
}
```

服务端只接受已知名字，使用 mask 修改已知位，保留 flag 中的其他未知位。

## 8. 为什么不让浏览器发送 raw hex

任意 hex 输入看似方便，风险却很高：

- 用户可能把长度、字节序或 command 写错；
- 可能误触发升级、解绑或清除；
- 浏览器端很难区分可恢复与不可恢复命令；
- 会把“已验证功能”和“猜测协议”混在一起。

因此页面只提供有实机证据的高层动作。研究者仍可在独立脚本中调用协议构造器，
但应明确承担风险。

## 9. Deep Work 计时器

页面的计时器属于电脑 UI：

- 开始：写 `notification_mode = 1` 并开始本地倒计时；
- 暂停：只暂停倒计时；
- 继续：只继续倒计时；
- 结束或倒计时归零：写 mode 0，并带一次 force harvest。

刷新页面会丢失本地倒计时，但设备 mode 可能仍保持 1。当前实现没有把计时器持久化到磁盘。

## 10. 并发与设备占用

FOCI 通常只允许一个活动 central。常见冲突：

- 官方 App 在后台自动重连；
- 另一台手机仍打开蓝牙；
- 前一个 Python 进程未正常断开；
- Windows 缓存了短暂的“连接中”状态。

排查顺序：

1. 彻底关闭官方 App 或关闭手机蓝牙。
2. 停止所有旧 dashboard 进程。
3. 等待数秒让 FOCI 重新广播。
4. 运行 `scan`。
5. 打开 dashboard 并点击“连接 FOCI”或“重新连接”。

## 11. 当前限制

- 主要在 Windows + 一台 FOCI 2A 上验证。
- UID/write key 的首次获取仍需要用户自己的官方 App 连接记录。
- 未实现历史数据同步、账户报告或云端个性化模型。
- 扩展 realtime payload 只部分解析。
- 未实现自动重连循环；断线或失败后需要在页面点击“重新连接”。
- Deep Work 倒计时刷新后不恢复。
- 不包含通知延迟的 UI；设备如何持久化延迟仍需进一步验证。
- 振动强度 command 已识别，但安全范围没有实机验证，因此未开放。

## 12. 建议的后续工程改进

- 自动重连和指数退避；
- 本地 SQLite/Parquet 历史存储；
- CSV/JSON 导出按钮；
- 持久化 Deep Work 计时器；
- 对设备状态响应建立完整 schema；
- 多固件版本兼容测试；
- Linux/macOS 实机测试；
- 将高层命令与固件能力协商绑定。
