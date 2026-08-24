# 07. 用自己的 Android 设备复现实验

## 1. 风险提示

这套流程会生成包含手机蓝牙活动的调试文件。请先阅读
[06_CAPTURE_PRIVACY.md](06_CAPTURE_PRIVACY.md)。不要把原始 bugreport 或 snoop log
上传到 issue。

推荐：

- 使用备用 Android 手机；
- 暂时断开其他蓝牙设备；
- 关闭会自动连接的耳机/手表；
- 只在必要时间开启 full HCI snoop；
- 原始文件只保留在本地。

## 2. 准备 ADB

安装 Google Android SDK Platform Tools，并确认：

```powershell
adb devices
```

手机需要：

1. 开启 Developer options；
2. 开启 USB debugging；
3. 接受这台电脑的调试授权；
4. USB 连接稳定。

不要在不信任的电脑上授权 USB debugging。

## 3. 开启 Bluetooth HCI snoop

不同厂商菜单名字略有差异。典型路径：

```text
Settings
→ Developer options
→ Enable Bluetooth HCI snoop log
→ Enabled / Full
```

更改后必须关闭再开启 Bluetooth 才生效。Android 官方步骤：

<https://source.android.com/docs/core/connect/bluetooth/verifying_debugging>

## 4. 设计单变量实验

不要随意点击所有页面。先写实验表：

| 步骤 | 操作 | 预期观察 |
|---:|---|---|
| 1 | 启动 App 并连接 | native + challenge + realtime |
| 2 | 等待 30 秒 | 纯实时基线 |
| 3 | 只切一个提醒 | 单条 config 差异 |
| 4 | 等待 3 秒 | 分隔相邻写入 |
| 5 | 恢复该提醒 | 反方向验证 |
| 6 | 开始 Deep Work | notification mode |
| 7 | 暂停/继续 | 是否出现 BLE 写入 |
| 8 | 结束 | mode 与 force harvest |

每次只改变一个变量。操作之间留出时间。

## 5. 插入 logcat 标记

电脑可写入不含隐私的步骤标记：

```powershell
adb shell log -t CODEX_FOCI_STEP SESSION_ALERT_DISTRACTION_OFF_BEGIN
```

操作完成再写：

```powershell
adb shell log -t CODEX_FOCI_STEP SESSION_ALERT_DISTRACTION_OFF_END
```

标记用于时间对齐。公开时只摘录步骤时间表，不公开完整 logcat。

## 6. 生成 bugreport

操作完成后：

1. 关闭手机 Bluetooth；
2. 停止 App 操作；
3. 生成 bugreport；
4. 在本地从 ZIP 中定位 `btsnoop_hci.log` / `.last`。

Android 也提供 `btsnooz.py` 从文本 bugreport 提取 snoop 的流程。不同系统版本和厂商的
ZIP 路径可能不同。

## 7. 初步解析

```powershell
python tools\analyze_foci_btsnoop.py raw_btsnoop.log > analysis.json
```

输出会包含 UID 和 challenge key。原始分析 JSON 同样是敏感文件，不要上传。

关注：

- `decoded_frames` 是否出现；
- `inner_command`；
- direction；
- attribute handle；
- config body；
- realtime 数量；
- credentials。

## 8. 识别自己的 UID 与 key

成功 App 连接中：

- inner header 的 UID 会在多数帧重复；
- challenge command `27514` 的 payload 前 4 字节是 write key。

它们是高敏感值。放进本地 `foci.local.json`，不要写入源码或测试。

如果 App 使用 fallback key，可验证：

```powershell
python -m foci_ble derive-key --uid YOUR_UID --mac YOUR_MAC
```

专用服务器 key 可能与 fallback 不同，以实机 challenge 为准。

## 9. 生成隐私处理版抓包

示意命令：

```powershell
python tools\sanitize_foci_btsnoop.py `
  raw_btsnoop.log `
  public_capture.btsnoop `
  --summary public_capture.summary.json `
  --uid YOUR_UID `
  --write-key YOUR_WRITE_KEY `
  --mac YOUR_DEVICE_MAC
```

注意：直接把秘密放在命令行可能进入 shell history。更安全的做法是写一个本地、被
`.gitignore` 排除的小包装脚本，从 `foci.local.json` 读取后调用 `sanitize_capture()`。

## 10. 验证脱敏结果

必须同时做：

```powershell
python tools\analyze_foci_btsnoop.py public_capture.btsnoop
```

以及二进制搜索：

- 原 UID 的 little-endian 8 字节；
- 原 key 的 little-endian 4 字节；
- 原 MAC 正序和逆序。

还要用 Wireshark 打开，确认：

- 能看到 `btatt`；
- characteristic value 中仍能看到 `FE` outer frame；
- 不存在 SMP、音频和其他连接；
- 时间已经平移。

## 11. 关闭调试

完成后：

1. Developer options 中把 HCI snoop 改为 Disabled；
2. 关闭再开启 Bluetooth 使设置生效；
3. 关闭 USB debugging；
4. 拔掉 USB；
5. 原始文件转移到安全位置。

不要因为“以后也许还会抓”而长期保持 full HCI snoop。
