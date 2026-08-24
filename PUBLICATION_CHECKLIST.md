# GitHub publication checklist

## Required before upload

- [ ] Read `PRIVACY_AUDIT.md`.
- [ ] Decide a license and replace `LICENSE_NOT_SELECTED.md`.
- [x] Confirm `foci.local.json` is absent.
- [x] Confirm no raw bugreport, logcat, APK, DEX, database or phone UI dump is present.
- [x] Confirm only the two sanitized `.btsnoop` files are under `captures/`.
- [x] Run `python -m pytest -q` (10 tests passed).
- [x] Re-run `tools/analyze_foci_btsnoop.py` on both public captures.
- [ ] Review `DATA_INVENTORY.md` and file hashes.

## Create an independent repository

Run these commands from this public folder, not from the private research folder:

```powershell
git init
git add .
git status
```

Before committing:

```powershell
git ls-files
```

Inspect every file. In particular, the list must not contain:

```text
foci.local.json
bugreport
logcat
btsnoop_hci.log
APK / DEX
decompiled/
raw-captures/
```

Then create the first commit:

```powershell
git commit -m "Initial public FOCI reverse-engineering release"
```

## Recommended repository description

> Unofficial FOCI 2A Bluetooth LE protocol research, Windows desktop dashboard, and privacy-sanitized HCI captures.

## Suggested topics

```text
bluetooth-low-energy
ble
iot
reverse-engineering
gatt
python
wearable
wireshark
```

## Release archive

The ZIP next to this folder is a convenience artifact. Git history should be created from the folder contents,
not by committing the ZIP into the repository.
