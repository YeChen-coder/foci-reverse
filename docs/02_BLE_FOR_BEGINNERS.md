# 02. 面向初学者的 Bluetooth Low Energy

这份文档用 FOCI 做具体例子，解释逆向一个 BLE IoT 设备时哪些信息重要。

## 1. BLE 与“传统蓝牙配对”不是一回事

传统印象中的蓝牙通常是耳机、键盘或音箱：先在系统设置中配对，之后系统长期记住设备。
BLE IoT 设备常采用另一种模式：

1. 设备周期性广播“我在这里”。
2. 手机或电脑扫描广播。
3. 手机/电脑主动建立短连接。
4. 连接后通过 GATT 读、写或订阅数据。
5. 产品还可能在 GATT 之上实现自己的登录/challenge。

所以三个概念必须分开：

- **无线连接**：BLE 控制器是否建立连接。
- **BLE 配对/加密**：Bluetooth 标准层是否交换长期密钥。
- **应用层认证**：厂商协议是否接受 UID、token 或 challenge。

FOCI 的实机流程中，Windows 不必先在系统设置里传统配对，但实时流需要应用层 UID 与
write key。系统显示“未配对”并不等于协议无法使用。

## 2. Central、Peripheral、Client、Server

这两组角色很容易混淆：

| 层 | FOCI | 手机/电脑 |
|---|---|---|
| 链路发起关系 | Peripheral（广播、被连接） | Central（扫描、发起连接） |
| GATT 关系 | GATT Server（保存属性表） | GATT Client（读写属性） |

“Server”不是说 FOCI 在运行网站；它只是持有一张 GATT 属性表。

## 3. 广播为什么重要

未连接时，电脑只能通过 Advertising 发现设备。扫描结果里最有价值的信息通常包括：

- 本地名称；
- BLE 地址；
- RSSI（接收信号强度，只能粗略表示距离）；
- Service UUID；
- 厂商自定义数据。

本设备广播自定义服务 `FEE7`。地址是单台设备的身份信息，因此公开包中用合成地址替换。

如果扫描不到设备，常见原因是：

- 设备正在被手机占用；
- 设备休眠，需要移动、佩戴或离开充电器；
- Windows 蓝牙关闭；
- 距离过远；
- 设备使用随机地址，而程序仍在使用旧地址。

## 4. GATT：服务、特征值和描述符

Bluetooth SIG 的 BLE Primer 对 GATT 的结构可概括为：

```text
GATT Server
└── Service
    ├── Characteristic
    │   ├── Value
    │   └── Descriptor(s)
    └── Characteristic
```

官方入门资料：

- <https://www.bluetooth.com/bluetooth-le-primer/>
- <https://www.bluetooth.com/wp-content/uploads/Files/Specification/HTML/Core_v6.3/out/en/host/generic-attribute-profile--gatt-.html>

在 FOCI 中，最重要的是自定义服务和四个特征值：

| UUID | 方向/用途 |
|---|---|
| `0000fee7-0000-1000-8000-00805f9b34fb` | 自定义主服务 |
| `0000fec7-0000-1000-8000-00805f9b34fb` | 电脑写入设备 |
| `0000fec8-0000-1000-8000-00805f9b34fb` | 设备 Indicate 到电脑 |
| `0000fec9-0000-1000-8000-00805f9b34fb` | 电脑读取 |
| `0000fed8-0000-1000-8000-00805f9b34fb` | 设备 Notify 到电脑 |
| `00002a00-0000-1000-8000-00805f9b34fb` | 标准 Device Name |

16 位样式 UUID 被扩展到 Bluetooth Base UUID
`0000xxxx-0000-1000-8000-00805f9b34fb`。

## 5. ATT 与 Attribute Handle

GATT 是“数据模型和操作流程”，ATT 是承载读写的底层协议。每个属性在一次 GATT 数据库
布局中有一个 16 位 handle。抓包中可看到：

- App 写入的目标 value handle：`0x000c`
- 设备推送的 value handle：`0x000e`

UUID 通常更稳定，handle 可能随固件或数据库布局改变。因此客户端运行时按 UUID 找特征值，
抓包分析时再用 handle 定位。

常见 ATT opcode：

| Opcode | 名称 | 是否等待协议响应 |
|---:|---|---|
| `0x12` | Write Request | 是 |
| `0x13` | Write Response | 对 `0x12` 的响应 |
| `0x52` | Write Command | 否 |
| `0x1B` | Notification | 否 |
| `0x1D` | Indication | 需要 Confirmation |
| `0x1E` | Confirmation | 对 `0x1D` 的确认 |

Notification 更轻量；Indication 有协议确认。两者都是设备主动向客户端推送数据。

## 6. CCCD 与订阅

设备不会因为连接成功就自动发送所有 Notify/Indicate。客户端通常需要设置
Client Characteristic Configuration Descriptor（CCCD，标准 UUID `0x2902`）。

Bleak 的 `start_notify()` 会通过系统 API完成这件事。FOCI 客户端对 `FEC8` 和 `FED8`
都调用订阅，然后把回调收到的字节送进帧重组器。

## 7. MTU 与为什么仍要分片

ATT_MTU 决定一条 ATT 消息可承载的最大大小。经典默认值是 23 字节，其中写入 value
常只剩 20 字节。实机协商出的 MTU 更大，但官方 App 仍把厂商协议包按 20 字节切片。

这意味着逆向时必须区分两层分片：

1. HCI ACL / L2CAP 层可能把一个 ATT PDU 分成多条控制器记录。
2. 官方 App 又把一个 FOCI 外层帧拆成多个 20 字节的 characteristic write。

不能假设“一条蓝牙通知就是一条完整业务消息”。本项目的 `OuterFrameAssembler`
会持续缓存字节，直到外层 header 声明的总长度全部到齐。

## 8. 字节序

同一个协议可以混合 big-endian 与 little-endian：

- FOCI outer header：big-endian。
- FOCI inner header 和业务结构：little-endian。
- ATT handle：little-endian。
- btsnoop 文件记录 header：big-endian。
- HCI ACL header：little-endian。

例如字节 `50 04 00 00` 作为 little-endian `uint32` 是 `0x00000450`。
如果按 big-endian 读，会得到完全错误的 `0x50040000`。

## 9. 抓包里哪些层最有价值

逆向 BLE IoT 设备时，建议按层看：

```text
HCI packet
└── ACL data
    └── L2CAP channel
        └── ATT PDU
            └── Characteristic value
                └── 厂商自定义协议
                    ├── FOCI outer frame
                    ├── protobuf-like envelope
                    └── FOCI inner frame / payload
```

本项目关心的固定 L2CAP CID 是 ATT 的 `0x0004`。原始 HCI 日志还可能含：

- 其他蓝牙设备；
- SMP 配对交换；
- 音频、电话簿、通知等 profile；
- 控制器事件和本机地址。

这就是为什么不能把手机原始 btsnoop 直接发布。

## 10. btsnoop 与 Wireshark

Android 的 Bluetooth HCI snoop log 记录主机与蓝牙控制器之间的 HCI 包。Android
官方说明：

<https://source.android.com/docs/core/connect/bluetooth/verifying_debugging>

公开包里的 `.btsnoop` 仍采用 H4 btsnoop 容器，可以直接用 Wireshark 打开。
推荐先使用显示过滤器：

```text
btatt
```

公开文件只保留目标连接的 ATT PDU，因此不需要从大量耳机、手表或系统事件中寻找 FOCI。

## 11. Bleak 在这里做什么

Bleak 把 Windows WinRT、Linux BlueZ 和 macOS CoreBluetooth 统一成 Python API：

- `BleakScanner` 扫描；
- `BleakClient` 连接；
- `start_notify()` 订阅；
- `write_gatt_char(..., response=True)` 写入并等待 ATT 响应。

官方文档：

- <https://bleak.readthedocs.io/en/latest/api/client.html>
- <https://bleak.readthedocs.io/en/latest/backends/windows.html>

Bleak 处理标准 BLE/GATT；本项目的主要逆向工作是 Bleak 回调里的厂商字节如何重组和解释。
