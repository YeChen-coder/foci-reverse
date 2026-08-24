# Installation and local configuration

This document intentionally contains only installation, configuration, and operation details.
Project background and narrative belong in `README.md`, which is intentionally left blank for the repository owner.

## Requirements

- Windows 10 or Windows 11
- Bluetooth Low Energy hardware supported by Windows
- Python 3.11 or newer
- A FOCI device
- The UID and write key for that specific device

The desktop dashboard uses Python, `aiohttp`, and `bleak`. It runs entirely on the local computer and serves the UI at `http://127.0.0.1:8765/`.

## 1. Download the repository

With Git installed:

```powershell
git clone https://github.com/YeChen-coder/foci-reverse.git
Set-Location foci-reverse
```

Alternatively, download the repository as a ZIP from GitHub and extract it.

## 2. Create the Python environment

Run these commands from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `python` is not found, install a current Python release from <https://www.python.org/downloads/windows/> and enable the installer option that adds Python to `PATH`.

## 3. Create the private device configuration

Copy the supplied example:

```powershell
Copy-Item foci.local.example.json foci.local.json
```

Edit `foci.local.json`:

```json
{
  "address": "YOUR_DEVICE_ADDRESS",
  "uid": 123456789,
  "write_key": "0x12345678"
}
```

- `address` is the BLE address or Windows device identifier discovered for the user's FOCI.
- `uid` is the device/account UID used by the archived FOCI protocol.
- `write_key` is the four-byte write credential, written as a decimal integer or `0x` hexadecimal string.

`foci.local.json` is deliberately ignored by Git. It grants write access to the configured device and must never be committed, pasted into an issue, or shared in a capture.

This repository cannot provide another person's UID or write key. A new user must obtain the values for their own device by inspecting their own archived App data or performing the documented capture/research workflow. See `docs/07_REPRODUCING_THE_CAPTURE.md` and the protocol documentation for the relevant fields.

## 4. Check that Windows can see FOCI

Disconnect the official phone App first. A FOCI normally accepts only one active BLE central connection.

Wake the device and scan:

```powershell
.\.venv\Scripts\python.exe -m foci_ble scan
```

For a read-only GATT inspection:

```powershell
.\.venv\Scripts\python.exe -m foci_ble inspect --address "YOUR_DEVICE_ADDRESS"
```

Traditional pairing from Windows Settings is normally unnecessary. The program connects using BLE GATT directly.

## 5. Start the dashboard

Double-click:

```text
Start FOCI Dashboard.cmd
```

The script starts the local server in the background, waits until it is ready, and opens the dashboard. It does not connect to FOCI automatically. Press **Connect FOCI** in the page to scan, authenticate, subscribe to notifications, and begin the real-time stream. A failed connection is reported in the page and can be retried.

The equivalent command is:

```powershell
.\.venv\Scripts\python.exe -m foci_ble dashboard
```

To stop the background dashboard process, double-click:

```text
Stop FOCI Dashboard.cmd
```

## Demo mode

The UI can be tested without a physical device:

```powershell
.\.venv\Scripts\python.exe -m foci_ble dashboard --demo
```

Demo mode produces synthetic values and disables connection to a real FOCI.

## Tests

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## Common connection problems

### No FOCI advertisement found

- Disconnect or fully close the official mobile App.
- Move the device away from its charger and wake it.
- Confirm Bluetooth is enabled on Windows.
- Keep the device near the computer during the initial scan.
- Check that `address` belongs to the intended device, or temporarily omit it to use name/service discovery.

### Authentication or configuration write fails

- Recheck `uid` and `write_key` in `foci.local.json`.
- Do not use the synthetic credentials contained in the public captures; they cannot control a physical device.
- Confirm that the JSON contains no trailing commas and that hexadecimal keys are quoted strings.

### Port 8765 is already in use

Stop the existing dashboard with `Stop FOCI Dashboard.cmd`, or select another port:

```powershell
.\.venv\Scripts\python.exe -m foci_ble dashboard --port 8766
```

### Bluetooth disconnects after initially working

Make sure the phone App has not reclaimed the connection. Return to the dashboard and press the reconnect button.

## Privacy reminder

Do not publish raw Android bugreports, raw HCI snoop logs, logcat output, App databases, APK/decompiled data, screenshots containing phone identifiers, or `foci.local.json`. The captures already committed under `captures/` are purpose-built sanitized research fixtures; additional captures are ignored by default.
