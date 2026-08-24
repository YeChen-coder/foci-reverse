# Security

## Sensitive material

Never submit any of the following to this repository, an issue, or a discussion:

- `foci.local.json`;
- a real FOCI UID or write key;
- an unredacted Bluetooth MAC;
- raw Android bugreport;
- raw HCI snoop log;
- complete logcat;
- App databases, tokens or account exports.

Use the sanitizer before sharing a capture. Even after sanitization, run the privacy audit described in
`docs/06_CAPTURE_PRIVACY.md`.

## Supported operations

The UI intentionally exposes only:

- realtime streaming;
- known notification flags;
- Deep Work notification mode.

It does not expose arbitrary command injection, unbind, factory reset, erase, DFU or firmware update.

## Reporting a problem

When reporting a protocol or security problem:

1. Describe firmware/App version without posting account information.
2. Use synthetic packet bytes where possible.
3. If a raw capture is essential, do not attach it publicly.
4. Remove UID, key, MAC, absolute timestamps and unrelated Bluetooth traffic.

This is an independent interoperability project, not an official vendor security channel.
