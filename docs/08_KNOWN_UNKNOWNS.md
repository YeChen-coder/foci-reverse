# 08. 已知、推测与未知

## 1. 已经有强证据的部分

- FEE7 service 与 FEC7/FEC8/FEC9/FED8 characteristic UUID。
- outer frame 的 8 字节 big-endian header。
- inner frame 的 17 字节 little-endian header。
- envelope field 2 包裹 inner frame。
- native request、challenge、config 和本固件 realtime command。
- challenge payload 的 4 字节 write key。
- UID 在 inner header 中。
- 配置 payload 的 36 字节顺序。
- 五种提醒的 bit mask。
- Deep Work start/end 的 notification mode。
- 暂停/继续不产生相关 config 写入。
- 实时 payload 前 21 字节的类型与偏移。
- 官方 App 使用 20 字节应用分片。

## 2. 有静态代码但未充分实机验证

- 旧实时命令 `27526`、`27540`。
- vibration intensity `27510` 的安全取值范围。
- 另一 ping command `27512`。
- 固件升级协议。
- rename、bind/unbind。
- pacer mode 的全部值。
- mindfulness level 的全部值。
- force harvest 完整生命周期。
- score3–score6 的来源与标定。

这些代码路径可能属于旧产品、旧固件或开发功能。

## 3. 实时字段的语义未知

虽然字段名来自 App，以下问题仍没有答案：

- `focus_depth` 的数值如何计算；
- `calm` 是呼吸平稳度、模型概率还是综合评分；
- `signal` 的单位；
- `signal_quality` 为何在许多样本中是 0；
- `ar1/ar3/ar4/ar5` 的滤波器或模型含义；
- `ktype` 的枚举；
- `p_m`、`bz`、`mp_s_bit`、`v_s` 的位定义；
- `e_progress` 与 `t_progress` 的完整状态机；
- data type 高 3 位分别代表哪些扩展 payload。

代码故意保留原始字节，以便后续研究者提出更好的 schema。

## 4. 原始传感器是否可取得

当前实时流看起来是已经处理过的指标，而不是标准 XYZ 加速度样本。尚未发现：

- 明确的三轴原始流 command；
- 加速度量程和采样率；
- 校准矩阵；
- 物理单位；
- 原始呼吸波形的固定格式。

App 的“Real Time Breathing Signal”可能由某个处理后 signal 绘制，也可能来自尚未解析的
扩展数据。需要同步录屏与更精细的字段相关实验。

## 5. 分类发生在设备还是 App

设备实时 payload 已直接包含 state 和多个评分，提醒配置也写入设备，因此至少一部分
分类/提醒逻辑在设备固件中。

App 同时包含：

- 个性化学习；
- 连续状态/streak；
- 报告和 session 统计；
- Biofeedback 课程；
- 服务器账户数据。

所以更合理的模型是“设备提供实时估计，App 再做产品层聚合”，而不是完全在某一端。

## 6. 配置是否永久保存

实机确认配置写入后立即生效，并能在后续连接状态中读回 flag。尚未系统测试：

- 完全断电后的保留；
- 恢复出厂后的默认值；
- 不同账户绑定后的迁移；
- 固件升级后的兼容性。

## 7. 提醒触发延迟

App 文案建议只开 1–2 个提醒，并提到约 1–3 分钟延迟和连续状态。当前 36 字节配置没有
明显独立 delay 字段。可能性：

- 延迟由固件固定；
- 延迟编码在 score3–score6；
- App 本地控制；
- 来自另一条未抓到的配置命令。

不要在没有逐变量实验前为它命名。

## 8. 安全模型

观察到应用层 challenge，但尚未证明：

- 链路是否总是加密；
- write key 是否每台设备唯一；
- key 是否会轮换；
- UID 是否是账户、设备或两者组合；
- 是否存在 replay 防护；
- sequence 是否用于安全校验；
- 设备是否限制失败次数。

公开抓包使用合成认证值。安全研究应在自有设备、物理近距离和合法授权范围内进行。

## 9. 跨平台兼容性

协议代码本身是 Python，但 BLE 平台行为不同：

- Windows：WinRT 缓存与设备查找；
- Linux：BlueZ 权限、adapter 与 D-Bus；
- macOS：CoreBluetooth 使用 UUID 标识，不直接暴露公共 MAC。

目前只有 Windows 得到完整实机验证。

## 10. 有价值的后续实验

低风险：

- 不同佩戴/呼吸/走动状态与字段相关性；
- 记录 App breathing graph 与 payload；
- 断电后读取配置；
- Linux/macOS 只读连接；
- 多台 FOCI 比较 UUID/handle/firmware；
- 对公开数据做聚类和状态转移分析。

中风险，需备用设备：

- 振动强度范围；
- pacer mode；
- mindfulness level；
- 未知 score 字段。

高风险，不建议在唯一设备上：

- DFU/firmware；
- bind/unbind；
- factory reset；
- erase；
- bootloader；
- 未知命令 fuzzing。
