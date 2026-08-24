# 03. FOCI BLE 协议

## 1. 协议栈概览

```text
Windows / Android App
  └─ GATT write FEC7
       └─ 20-byte application chunks
            └─ FOCI outer frame (big-endian header)
                 └─ small protobuf-like envelope
                      └─ FOCI inner frame (little-endian header)
                           └─ command-specific payload

FOCI
  └─ GATT indication FEC8 / notification FED8
       └─ 同样的 outer + envelope + inner 结构
```

## 2. GATT 参数

| 项目 | 值 |
|---|---|
| Service | `0000fee7-0000-1000-8000-00805f9b34fb` |
| Write | `0000fec7-0000-1000-8000-00805f9b34fb` |
| Indicate | `0000fec8-0000-1000-8000-00805f9b34fb` |
| Read | `0000fec9-0000-1000-8000-00805f9b34fb` |
| Notify | `0000fed8-0000-1000-8000-00805f9b34fb` |
| Device Name | `00002a00-0000-1000-8000-00805f9b34fb` |
| 实机 write handle | `0x000c` |
| 实机 inbound value handle | `0x000e` |

handle 是本次固件的观察值；客户端使用 UUID，不应硬编码 handle。

## 3. Outer frame

长度固定为 8 字节，全部多字节字段为 big-endian：

| Offset | 长度 | 字段 |
|---:|---:|---|
| 0 | 1 | Magic，固定 `0xFE` |
| 1 | 1 | Flags |
| 2 | 2 | 总长度，包含 8 字节 header |
| 4 | 2 | Outer command |
| 6 | 2 | Outer sequence |
| 8 | N | Payload |

Python 等价格式：

```python
struct.pack(">BBHHH", 0xFE, flags, total, command, sequence)
```

示例，进入厂商原生协议：

```text
fe 00 00 09 67 89 00 01 19
```

- 总长度：`0x0009`
- outer command：`0x6789` = `26505`
- sequence：1
- payload：`19`

## 4. Inner frame

长度固定为 17 字节，多字节字段为 little-endian：

| Offset | 长度 | 字段 |
|---:|---:|---|
| 0 | 1 | Version，实机为 1 |
| 1 | 2 | Inner 总长度 |
| 3 | 2 | Inner command |
| 5 | 2 | Error / status |
| 7 | 8 | UID |
| 15 | 2 | Inner sequence |
| 17 | N | Command payload |

Python 等价格式：

```python
struct.pack("<BHHHQH", version, total, command, error, uid, sequence)
```

## 5. Envelope

Inner frame 通常放进 outer command `30001` 的 payload。观察到的 envelope 形态：

```text
0a 00 12 <varint length> <inner frame>
```

按 protobuf wire format 理解：

- field 1：长度为 0 的 BaseRequest；
- field 2：inner frame 原始字节。

项目只实现解析所需的 varint 和 length-delimited 字段，不依赖生成出来的 protobuf 类。

## 6. 连接与认证顺序

典型流程：

```text
Central 连接 FOCI
  ↓
订阅 FEC8 与 FED8
  ↓
发送 native request (outer 26505, payload 0x19)
  ↓
发送 challenge (inner 27514, payload = 4-byte write key)
  ↓
设备开始推送 27545 实时流
  ↓
约每 20 秒发送保活/时间命令
```

UID 与 write key 不是 Windows 的蓝牙 PIN。它们属于应用层。

归档 App 还包含 fallback write key 计算：

```text
MD5(
  decimal_unsigned_uid
  + "3BF608C70828"
  + lowercase_mac_without_colons
)[0:4]
```

前四字节按 little-endian `uint32` 使用。设备/账户也可能已有服务器下发的专用 key，
因此 fallback 不保证适用于所有设备。

公开抓包中的 UID、MAC 和 key 都是相互一致的合成值，不能控制真实设备。

## 7. 已观察命令

| 层 | Command | 方向 | 用途 | 置信度 |
|---|---:|---|---|---|
| Outer | 26505 | 电脑 → FOCI | 进入/请求厂商原生协议 | 实机确认 |
| Outer | 26509 | 电脑 → FOCI | outer heartbeat 构造 | 静态分析 |
| Outer | 30001 | 双向 envelope | 包裹 inner frame | 实机确认 |
| Inner | 27514 | 电脑 → FOCI | challenge；payload 前 4 字节是 key | 实机确认 |
| Inner | 27539 | 电脑 → FOCI | 抓到的 4 字节 Unix 秒保活/时间命令 | 实机确认 |
| Inner | 27536 | 电脑 → FOCI | 全局功能与提醒配置 | 实机确认 |
| Inner | 27545 | FOCI → 电脑 | 本固件实时数据 | 实机确认 |
| Inner | 27526/27540 | FOCI → 电脑 | 旧代码接受的实时数据变体 | 静态分析 |
| Inner | 27510 | 电脑 → FOCI | vibration intensity | 静态分析，未开放 UI |
| Inner | 27512 | 电脑 → FOCI | 另一 ping API | 静态分析 |

“静态分析”表示归档 App 存在代码路径，但不等于已在这台设备上安全验证。

## 8. 实时 payload

主实时命令 `27545` 的前 21 字节：

| Offset | 类型 | 字段 |
|---:|---|---|
| 0 | `u8` | display scale |
| 1 | `u8` | raw state：低 5 位 state，高 3 位 data type |
| 2 | `u8` | focus depth |
| 3 | `u8` | calm |
| 4 | `u8` | signal |
| 5 | `i16le` | ar1 |
| 7 | `u8` | p_m |
| 8 | `u8` | bz |
| 9 | `i16le` | ar3 |
| 11 | `u8` | ktype |
| 12 | `u8` | e_progress |
| 13 | `i16le` | signal quality |
| 15 | `u8` | mp score |
| 16 | `u8` | tension score |
| 17 | `u8` | focus_ev |
| 18 | `u8` | mp_s_bit |
| 19 | `u8` | v_s |
| 20 | `u8` | t_progress |

解析格式：

```python
struct.unpack("<BBBBBhBBhBBhBBBBBB", payload[:21])
```

较长 payload 还包含状态、固件、名称、配置、分钟数据或时间。部分扩展结构仍未完全解释，
因此解析器只暴露已经有证据的字段，并保留 `raw_hex`。

## 9. 配置命令 27536

payload 恰好 36 字节：

| Offset | 长度 | 类型 | 字段 |
|---:|---:|---|---|
| 0 | 4 | `i32le` | current Unix time（秒） |
| 4 | 4 | `i32le` | raw timezone offset（毫秒） |
| 8 | 4 | `i32le` | score3 |
| 12 | 4 | `i32le` | score4 |
| 16 | 4 | `i32le` | score5 |
| 20 | 4 | `i32le` | score6 |
| 24 | 4 | `u32le` | default notification flags |
| 28 | 4 | `u32le` | session notification flags |
| 32 | 1 | `u8` | pacer mode |
| 33 | 1 | `u8` | force harvest |
| 34 | 1 | `u8` | notification mode |
| 35 | 1 | `u8` | mindfulness level |

归档类 `TrackerFnConfigEntity.toBytes()` 的顺序与实机抓包逐字节一致。

## 10. 五种提醒位

默认和 Deep Work 使用相同掩码，但分别存放在两个 32 位 flag 字段中。

| 提醒 | 掩码 | App 描述 |
|---|---:|---|
| Distraction | `0x0010` | 形成分心连续状态时 1 次长震 |
| Early distraction | `0x1000` | 即将分心时 2 次短震 |
| Focus slip | `0x0440` | 专注/心流连续状态中断时 3 次短震 |
| Tense | `0x0080` | 形成紧张连续状态时 4 次短震 |
| Fatigue | `0x0200` | 形成疲劳连续状态时 5 次短震 |

`Focus slip` 必须同时设置 `0x0040` 与 `0x0400`。这是逐个开关抓包发现的，
只切换一个 bit 会产生未验证状态。

实机基线：

```text
default_flags = 0x0450
  distraction = on
  focus_slip  = on

session_flags = 0x1010
  distraction       = on
  early_distraction = on
```

这些只是测试设备当时的用户设置，不是所有 FOCI 的出厂默认值。

## 11. Deep Work 的真实蓝牙行为

观察结果：

- 进入 Deep Work：`notification_mode = 1`
- 暂停：没有配置写入
- 继续：没有配置写入
- 结束：`notification_mode = 0`，该次写入 `force_harvest = 1`

所以官方 App 的暂停主要是手机端计时/UI 状态；设备仍保持 session notification mode。
桌面端按相同行为实现。

## 12. 分片重组规则

官方 App 把完整 outer frame 按 20 字节写入 FEC7。设备侧推送也可能拆分。
重组器：

1. 丢弃 magic `0xFE` 前的字节。
2. 至少等待 8 字节 header。
3. 读取 big-endian `total`。
4. 缓冲区不足 `total` 时继续等待下一 chunk。
5. 取出一帧后继续解析余下字节。
6. 拒绝小于 8 或异常大的长度。

不能依赖 BLE notification 边界作为厂商帧边界。

## 13. Sequence 与错误字段

outer sequence 和 inner sequence 分开递增。当前客户端从 1 开始，16 位回绕。
设备实时流也带自己的 sequence。

inner error 在正常实机流中为 0。错误码集合尚未系统映射。
