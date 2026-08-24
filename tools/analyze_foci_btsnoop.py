from __future__ import annotations

import json
import struct
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from foci_ble.protocol import (  # noqa: E402
    CMD_CHALLENGE,
    OuterFrameAssembler,
    dataclass_dict,
    decode_event,
    unwrap_inner,
)

ATT_CID = 0x0004
ATT_VALUES = {
    0x12: "write_request",
    0x1B: "notification",
    0x1D: "indication",
    0x52: "write_command",
}

BTSNOOP_UNIX_EPOCH_US = 0x00DC_DDB3_0F2F_8000


def timestamp_iso(timestamp: int) -> str:
    unix_us = timestamp - BTSNOOP_UNIX_EPOCH_US
    return (
        datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=unix_us)
    ).isoformat(timespec="microseconds")


def btsnoop_records(path: Path):
    data = path.read_bytes()
    if data[:8] != b"btsnoop\0":
        raise ValueError("not a btsnoop file")
    offset = 16
    while offset + 24 <= len(data):
        original, included, flags, drops, timestamp = struct.unpack(
            ">IIIIQ", data[offset : offset + 24]
        )
        offset += 24
        packet = data[offset : offset + included]
        offset += included
        if len(packet) != included:
            break
        yield {
            "original": original,
            "included": included,
            "direction": "in" if flags & 1 else "out",
            "drops": drops,
            "timestamp": timestamp,
            "packet": packet,
        }


def att_messages(path: Path):
    fragments: dict[tuple[str, int], dict[str, Any]] = {}
    for record in btsnoop_records(path):
        packet = record["packet"]
        if len(packet) < 9 or packet[0] != 0x02:
            continue
        handle_flags, acl_length = struct.unpack("<HH", packet[1:5])
        connection = handle_flags & 0x0FFF
        pb = (handle_flags >> 12) & 0x3
        acl_data = packet[5 : 5 + acl_length]
        key = (record["direction"], connection)
        complete: tuple[int, bytes] | None = None
        if pb in (0, 2) and len(acl_data) >= 4:
            l2_length, cid = struct.unpack("<HH", acl_data[:4])
            payload = bytearray(acl_data[4:])
            if len(payload) >= l2_length:
                complete = (cid, bytes(payload[:l2_length]))
            else:
                fragments[key] = {
                    "cid": cid,
                    "expected": l2_length,
                    "payload": payload,
                    "timestamp": record["timestamp"],
                }
        elif pb == 1 and key in fragments:
            current = fragments[key]
            current["payload"].extend(acl_data)
            if len(current["payload"]) >= current["expected"]:
                complete = (
                    current["cid"],
                    bytes(current["payload"][: current["expected"]]),
                )
                del fragments[key]
        if complete is None or complete[0] != ATT_CID or not complete[1]:
            continue
        yield {
            "direction": record["direction"],
            "connection": connection,
            "timestamp": record["timestamp"],
            "timestamp_iso": timestamp_iso(record["timestamp"]),
            "att": complete[1],
        }


def analyze(path: Path) -> dict[str, Any]:
    assemblers: dict[tuple[str, int, int], OuterFrameAssembler] = defaultdict(
        OuterFrameAssembler
    )
    foci_att: list[dict[str, Any]] = []
    frames: list[dict[str, Any]] = []
    credentials: list[dict[str, Any]] = []

    for message in att_messages(path):
        att = message["att"]
        opcode = att[0]
        if opcode not in ATT_VALUES or len(att) < 3:
            continue
        attribute_handle = struct.unpack("<H", att[1:3])[0]
        value = att[3:]
        if not value:
            continue
        key = (message["direction"], message["connection"], attribute_handle)
        found_frames = assemblers[key].feed(value)
        looks_foci = value.startswith(b"\xfe") or bool(found_frames)
        if looks_foci:
            foci_att.append(
                {
                    "direction": message["direction"],
                    "connection": message["connection"],
                    "timestamp": message["timestamp"],
                    "timestamp_iso": message["timestamp_iso"],
                    "att_operation": ATT_VALUES[opcode],
                    "attribute_handle": f"0x{attribute_handle:04x}",
                    "value_hex": value.hex(" "),
                }
            )
        for outer in found_frames:
            event = decode_event(outer)
            entry = {
                "direction": message["direction"],
                "connection": message["connection"],
                "timestamp": message["timestamp"],
                "timestamp_iso": message["timestamp_iso"],
                "attribute_handle": f"0x{attribute_handle:04x}",
                "outer": dataclass_dict(outer),
                "event": event,
            }
            frames.append(entry)
            inner = unwrap_inner(outer)
            if inner and inner.command == CMD_CHALLENGE and len(inner.payload) >= 4:
                credentials.append(
                    {
                        "uid": inner.uid,
                        "uid_hex": f"0x{inner.uid:016x}",
                        "write_key": int.from_bytes(inner.payload[:4], "little"),
                        "write_key_hex": f"0x{int.from_bytes(inner.payload[:4], 'little'):08x}",
                        "raw_key_le": inner.payload[:4].hex(),
                        "connection": message["connection"],
                        "attribute_handle": f"0x{attribute_handle:04x}",
                    }
                )

    return {
        "source": str(path),
        "foci_att_messages": foci_att,
        "decoded_frames": frames,
        "credentials": credentials,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} btsnoop.log")
    result = analyze(Path(sys.argv[1]))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
