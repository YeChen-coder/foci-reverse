# 04. 逆向方法与证据链

## 1. 为什么同时需要静态分析和抓包

只看 APK：

- 可以发现类名、命令号、结构序列化顺序和 UI 文案；
- 但不知道当前固件实际走哪条路径；
- 也无法确认某个开关最终改了哪一位。

只看抓包：

- 可以看到真实字节；
- 但面对几十个未知字段，很难知道它们的名称与业务含义；
- 同一时刻多个 UI 状态变化会造成因果不明确。

本项目采用“静态分析提出假设，单变量抓包验证”的方法。

## 2. 静态分析得到的关键线索

归档 Android App 中最有价值的不是 UI，而是：

- `TrackerFnConfigEntity.toBytes()`：给出 36 字节配置顺序；
- `FnRealTimeDataEntity` / `ProtocolV2Processor`：给出实时命令与字段类型；
- `GlobalNotificationSettingManager` /
  `SessionNotificationSettingManager` 的调用关系；
- `NotificationSetting` 与 UI 字符串：给出五种提醒名称；
- `HashUtils.getBoxValidKey()`：给出 fallback key 计算；
- GATT service/characteristic UUID；
- App 对 Notify/Indicate 的订阅与 20 字节分片方式。

没有在公开包中分发 APK、DEX 或反编译代码。文档记录的是互操作所需的行为和结构。

## 3. 第一次实机阶段：建立最小链路

建议顺序：

1. 扫描广播，确认设备服务 UUID。
2. 只读连接并枚举 GATT。
3. 发送最小的 native request。
4. 验证设备是否响应 FOCI 名称与 MAC。
5. 从一段成功官方 App 连接中识别 challenge。
6. 实现 outer/inner 帧和认证。
7. 只接收实时流，不写任何配置。

这样可以把风险限制在“连接和读取”，不会一开始就尝试固件升级或未知写入。

## 4. 第二次实机阶段：逐个开关

提醒位映射使用严格单变量流程：

```text
记录基线
↓
只切换 Distraction
↓
等待并记录一条配置写入
↓
只切换 Early distraction
↓
重复
↓
依次切换 Focus slip / Tense / Fatigue
↓
按反方向逐项恢复
↓
再次确认最终基线
```

抓到的 session flag 序列：

| 操作后 | Flag |
|---|---:|
| 基线 | `0x1010` |
| Distraction off | `0x1000` |
| Early distraction off | `0x0000` |
| Focus slip on | `0x0440` |
| Tense on | `0x04c0` |
| Fatigue on | `0x06c0` |
| Focus slip off | `0x0280` |
| Tense off | `0x0200` |
| Fatigue off | `0x0000` |
| Distraction on | `0x0010` |
| Early distraction on | `0x1010` |

由相邻值异或可得到每种提醒的确切 mask。正向与恢复方向互相验证，
避免把 App 的其他周期写入误认成开关变化。

## 5. Deep Work 控制实验

操作序列：

1. 进入 Deep Work。
2. 记录 mode。
3. 暂停并等待。
4. 继续并等待。
5. 再次暂停。
6. 结束。

结果：

- 开始和结束出现配置写入；
- 暂停和继续没有相关 BLE 配置；
- 结束时 `force_harvest` 短暂为 1。

因此桌面实现不应在暂停时关闭 session mode，否则会偏离官方行为。

## 6. 时间标记为什么重要

HCI 日志只有包的时间戳，不知道用户当时点了什么。实验时通过 Android logcat 插入
自定义步骤标记：

```text
SESSION_ALERT_3_FOCUS_SLIP_OFF_TO_ON_BEGIN
SESSION_ALERT_3_FOCUS_SLIP_OFF_TO_ON_END
```

然后把标记时间与 `27536` 写入时间对齐。这样比“凭肉眼猜顺序”可靠得多。

公开包不包含原始 logcat，因为它可能记录其他 App、系统通知、账户和手机状态。
公开文档只保留经过验证的操作—字节对应关系。

## 7. 如何判断字段已经确认

本项目使用三档证据：

### 实机确认

- 抓包中确实出现；
- 可由电脑重放或读取；
- 操作结果与官方 App 一致；
- 最好有正反两个方向或重复实验。

### 静态分析

- App 中有明确类、字段或命令；
- 尚未在实机主动执行；
- 可能受固件版本、服务器配置或产品代际影响。

### 推测

- 由名字、数值范围或相邻字段猜测；
- 还没有唯一因果证据；
- 文档必须明确标注，不应作为写入依据。

## 8. 为什么没有测试所有命令

逆向 IoT 设备时，能够构造一个命令不代表应该发送。高风险类别包括：

- unbind / factory reset；
- firmware update；
- bootloader / DFU；
- rename / persistent identity；
- erase history；
- power off；
- 未知长度的配置。

唯一一台停产设备没有方便的恢复渠道，因此本项目只暴露已经抓到且可恢复的提醒配置。

## 9. 从“抓到字节”到可维护代码

代码实现遵循：

- 每种 header 都用显式 `struct` 格式；
- 字节序写在代码和测试中；
- 重组器对截断和非法长度失败关闭；
- command 常量集中定义；
- 解析结果保留 `raw_hex`；
- 配置 mask 有逐步序列测试；
- challenge 使用合成公开样本测试；
- 仪表盘 API 验证输入，不提供任意命令通道。

## 10. 公开数据的选择

原始数据的研究价值与隐私风险不同：

| 数据 | 研究价值 | 隐私风险 | 公开包 |
|---|---|---|---|
| 原始 bugreport | 高 | 极高 | 不包含 |
| 原始 HCI ring buffer | 高 | 高 | 不包含 |
| 全量 logcat | 中 | 极高 | 不包含 |
| App 截图/UI XML | 中 | 中到高 | 不包含 |
| FOCI-only ATT | 高 | 可处理 | 脱敏后包含 |
| 配置变化 CSV | 高 | 低 | 包含 |
| 去标识实时样本 | 中 | 中 | 明示后包含 |
| APK/反编译代码 | 高 | 版权风险 | 不包含 |

具体转换见 [06_CAPTURE_PRIVACY.md](06_CAPTURE_PRIVACY.md)。
