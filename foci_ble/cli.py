from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from pathlib import Path
from typing import Any

from .client import FOCIClient, discover_foci
from .dashboard import run_dashboard
from .protocol import derive_write_key

LOCAL_CONFIG = Path(__file__).resolve().parents[1] / "foci.local.json"


def number(value: str) -> int:
    return int(value, 0)


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--address", help="BLE address; auto-detects FOCI when omitted")
    parser.add_argument("--uid", type=number, help="account/device UID, decimal or 0x...")
    parser.add_argument(
        "--write-key", type=number, help="four-byte app write key, decimal or 0x..."
    )


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="python -m foci_ble",
        description="Experimental Tinylogics FOCI BLE desktop client",
    )
    sub = root.add_subparsers(dest="command", required=True)

    scan = sub.add_parser("scan", help="scan for FOCI advertisements")
    scan.add_argument("--timeout", type=float, default=8)

    inspect_device = sub.add_parser("inspect", help="connect read-only and list GATT")
    inspect_device.add_argument("--address")

    listen = sub.add_parser("listen", help="print decoded BLE events")
    add_connection_args(listen)
    listen.add_argument("--duration", type=float, default=30)
    listen.add_argument("--csv", type=Path, help="append real-time samples to CSV")

    key = sub.add_parser("derive-key", help="derive the fallback app write key")
    key.add_argument("--uid", required=True, type=number)
    key.add_argument("--mac", required=True)

    dash = sub.add_parser("dashboard", help="run the local live dashboard")
    add_connection_args(dash)
    dash.add_argument("--demo", action="store_true", help="use synthetic sample data")
    dash.add_argument("--host", default="127.0.0.1")
    dash.add_argument("--port", default=8765, type=int)
    dash.add_argument("--no-open", action="store_true")
    return root


def apply_local_config(args: argparse.Namespace) -> None:
    if args.command not in {"listen", "dashboard"} or not LOCAL_CONFIG.exists():
        return
    data = json.loads(LOCAL_CONFIG.read_text(encoding="utf-8"))
    if args.address is None:
        args.address = data.get("address")
    if args.uid is None and data.get("uid") is not None:
        args.uid = int(data["uid"])
    if args.write_key is None and data.get("write_key") is not None:
        value = data["write_key"]
        args.write_key = int(value, 0) if isinstance(value, str) else int(value)


def csv_handler(path: Path | None):
    fields = [
        "received_at",
        "state",
        "state_label",
        "focus_depth",
        "calm",
        "signal",
        "signal_quality",
        "mp_score",
        "tension_score",
    ]

    def handler(event: dict[str, Any]) -> None:
        print(json.dumps(event, ensure_ascii=False))
        if path is None or event.get("kind") != "realtime":
            return
        exists = path.exists()
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow(event)

    return handler


async def main_async(args: argparse.Namespace) -> None:
    if args.command == "scan":
        found = await discover_foci(args.timeout)
        clean = [{k: v for k, v in item.items() if k != "device"} for item in found]
        print(json.dumps(clean, indent=2, ensure_ascii=False))
        return
    if args.command == "inspect":
        async with FOCIClient(args.address) as client:
            print(json.dumps(await client.inspect(), indent=2, ensure_ascii=False))
        return
    if args.command == "listen":
        async with FOCIClient(args.address, handler=csv_handler(args.csv)) as client:
            print(f"Connected to {client.address}", file=sys.stderr)
            await client.listen(
                args.duration, uid=args.uid, write_key=args.write_key
            )
        return
    if args.command == "derive-key":
        key, raw = derive_write_key(args.uid, args.mac)
        print(json.dumps({"write_key": key, "hex_le": raw.hex()}, indent=2))
        return
    if args.command == "dashboard":
        await run_dashboard(
            address=args.address,
            uid=args.uid,
            write_key=args.write_key,
            demo=args.demo,
            host=args.host,
            port=args.port,
            open_browser=not args.no_open,
        )


def main() -> None:
    args = parser().parse_args()
    apply_local_config(args)
    try:
        asyncio.run(main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
