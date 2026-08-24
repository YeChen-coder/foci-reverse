# Sanitized Bluetooth Captures

这里的 `.btsnoop` 可以用 Wireshark 打开，但不是原始手机日志。

## 文件

| 文件 | Session | ATT PDU | FOCI frame | 说明 |
|---|---:|---:|---:|---|
| `capture_01_ring_buffer.btsnoop` | 2 | 43,186 | 7,267 | 环形日志：初始认证/实时 session，以及功能实验 session 的前半段 |
| `capture_02_rotation_continuation.btsnoop` | 1 | 6,117 | 1,006 | 日志轮转后的连续部分 |
| **合计** | — | **49,303** | **8,273** | 完整公开数据集 |

`capture_01` 的第二个 session 与 `capture_02` 在时间上连续。Android Bluetooth logger
在固定大小处轮转，因此分成 `.last` 和当前文件。本包保留轮转边界，不把两个容器强行
拼接。

更早提取的一份较短日志是 `capture_01` 第一个 session 的子集，因此没有重复放入。

## 文件经过的转换

- 只保留已识别 FOCI session 的 ATT；
- 删除 HCI event、SMP、非 ATT L2CAP 和其他连接；
- 重组 HCI ACL fragment；
- 每条 ATT PDU 重新封装为一条 H4 ACL btsnoop record；
- UID、write key 和 MAC 替换为合成值；
- connection handle 重新映射；
- btsnoop 绝对时间平移到固定日期；
- 已知 App epoch 重写；
- 配置 timezone 清零。

完整说明见 [../docs/06_CAPTURE_PRIVACY.md](../docs/06_CAPTURE_PRIVACY.md)。

## Wireshark

直接打开：

```text
capture_01_ring_buffer.btsnoop
```

显示过滤器：

```text
btatt
```

你会看到：

- Write Request / Write Response；
- Notification / Indication / Confirmation；
- handle `0x000c` 的 App → FOCI characteristic chunks；
- handle `0x000e` 的 FOCI → App characteristic chunks。

FOCI outer frame 可能跨多条 ATT characteristic value，因此单看一条 `0x12` 或 `0x1B`
不一定能看到完整业务结构。使用仓库解析器：

```powershell
python tools\analyze_foci_btsnoop.py `
  captures\capture_01_ring_buffer.btsnoop
```

## 可读导出

`decoded/`：

- `*.decoded_frames.jsonl`：一行一个重组完成的 FOCI outer frame；
- `*.att_pdus.csv.gz`：全部 ATT PDU 的相对时间、方向、opcode、handle 和 hex。

`../datasets/`：

- `capture_counts.csv`
- `configuration_transitions.csv`
- `realtime_samples.csv`

JSONL 的 `event` 同时保留 `payload_hex`、`body_hex` 与已解释字段。UID/key 是合成值。

## 时间

每个公开文件以 `2025-01-01T00:00:00Z` 附近作为合成起点。包间间隔和 session 内相对
时序保留，不能用这些文件推断真实实验日期或时区。

## 数据内容提醒

虽然已经去除直接身份，这些文件仍含一段真实 FOCI session 的去标识化状态序列，
例如 distracted/focused、calm 和 tension score。它们适合协议验证，不代表通用人群数据，
也不应用于识别或评价原参与者。
