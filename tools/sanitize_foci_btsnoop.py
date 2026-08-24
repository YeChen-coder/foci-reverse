from __future__ import annotations

import argparse
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from foci_ble.protocol import (  # noqa: E402
    CMD_CHALLENGE,
    CMD_CONFIG,
    CMD_REALTIME,
    InnerFrame,
    OuterFrame,
    OuterFrameAssembler,
    derive_write_key,
    parse_outer,
    unwrap_inner,
)

BTSNOOP_EPOCH_DELTA_US = 0x00DC_DDB3_0F2F_8000
SAFE_UNIX_EPOCH_SECONDS = 1_735_689_600  # 2025-01-01 00:00:00 UTC
ATT_CID = 0x0004
VALUE_OPCODES = {0x12, 0x1B, 0x1D, 0x52}
CMD_PING = 27539
SYNTHETIC_UID = 0x1122334455667788
SYNTHETIC_MAC = "02:00:00:00:00:01"


@dataclass(slots=True)
class Record:
    original: int
    included: int
    flags: int
    drops: int
    timestamp: int
    packet: bytes

    @property
    def direction(self) -> str:
        return "in" if self.flags & 1 else "out"


@dataclass(slots=True)
class AttMessage:
    ordinal: int
    flags: int
    timestamp: int
    direction: str
    connection: int
    att: bytes

    @property
    def opcode(self) -> int:
        return self.att[0] if self.att else -1

    @property
    def attribute_handle(self) -> int | None:
        if self.opcode in VALUE_OPCODES and len(self.att) >= 3:
            return struct.unpack("<H", self.att[1:3])[0]
        return None

    @property
    def value(self) -> bytes:
        return self.att[3:] if self.attribute_handle is not None else b""


def read_btsnoop(path: Path) -> tuple[bytes, list[Record]]:
    data = path.read_bytes()
    if len(data) < 16 or data[:8] != b"btsnoop\0":
        raise ValueError(f"{path} is not a btsnoop file")
    header = data[:16]
    records: list[Record] = []
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
        records.append(
            Record(original, included, flags, drops, timestamp, packet)
        )
    return header, records


def extract_att_messages(records: list[Record]) -> list[AttMessage]:
    fragments: dict[tuple[str, int], dict[str, Any]] = {}
    messages: list[AttMessage] = []
    for record in records:
        packet = record.packet
        if len(packet) < 9 or packet[0] != 0x02:
            continue
        handle_flags, acl_length = struct.unpack("<HH", packet[1:5])
        connection = handle_flags & 0x0FFF
        pb = (handle_flags >> 12) & 0x3
        acl_data = packet[5 : 5 + acl_length]
        key = (record.direction, connection)
        complete: tuple[int, bytes, int, int] | None = None
        if pb in (0, 2) and len(acl_data) >= 4:
            l2_length, cid = struct.unpack("<HH", acl_data[:4])
            payload = bytearray(acl_data[4:])
            if len(payload) >= l2_length:
                complete = (
                    cid,
                    bytes(payload[:l2_length]),
                    record.timestamp,
                    record.flags,
                )
            else:
                fragments[key] = {
                    "cid": cid,
                    "expected": l2_length,
                    "payload": payload,
                    "timestamp": record.timestamp,
                    "flags": record.flags,
                }
        elif pb == 1 and key in fragments:
            current = fragments[key]
            current["payload"].extend(acl_data)
            if len(current["payload"]) >= current["expected"]:
                complete = (
                    current["cid"],
                    bytes(current["payload"][: current["expected"]]),
                    current["timestamp"],
                    current["flags"],
                )
                del fragments[key]
        if complete is None or complete[0] != ATT_CID or not complete[1]:
            continue
        messages.append(
            AttMessage(
                ordinal=len(messages),
                flags=complete[3],
                timestamp=complete[2],
                direction=record.direction,
                connection=connection,
                att=complete[1],
            )
        )
    return messages


def find_foci_frame_markers(messages: list[AttMessage]) -> list[dict[str, int]]:
    assemblers: dict[tuple[str, int, int], OuterFrameAssembler] = {}
    markers: list[dict[str, int]] = []
    for message in messages:
        handle = message.attribute_handle
        if handle is None or not message.value:
            continue
        key = (message.direction, message.connection, handle)
        assembler = assemblers.setdefault(key, OuterFrameAssembler())
        for _ in assembler.feed(message.value):
            markers.append(
                {
                    "timestamp": message.timestamp,
                    "connection": message.connection,
                }
            )
    return markers


def cluster_sessions(markers: list[dict[str, int]]) -> list[dict[str, Any]]:
    sessions: list[dict[str, Any]] = []
    for marker in sorted(markers, key=lambda item: item["timestamp"]):
        if (
            not sessions
            or marker["timestamp"] - sessions[-1]["last_frame_timestamp"]
            > 30_000_000
        ):
            sessions.append(
                {
                    "first_frame_timestamp": marker["timestamp"],
                    "last_frame_timestamp": marker["timestamp"],
                    "connections": {marker["connection"]},
                    "frame_count": 1,
                }
            )
        else:
            session = sessions[-1]
            session["last_frame_timestamp"] = marker["timestamp"]
            session["connections"].add(marker["connection"])
            session["frame_count"] += 1
    for session in sessions:
        session["start"] = session["first_frame_timestamp"] - 8_000_000
        session["end"] = session["last_frame_timestamp"] + 5_000_000
    return sessions


def session_for_message(
    message: AttMessage, sessions: list[dict[str, Any]]
) -> int | None:
    for index, session in enumerate(sessions):
        if (
            message.connection in session["connections"]
            and session["start"] <= message.timestamp <= session["end"]
        ):
            return index
    return None


def safe_epoch_for_timestamp(timestamp: int, first_timestamp: int) -> int:
    relative_seconds = max(0, (timestamp - first_timestamp) // 1_000_000)
    return SAFE_UNIX_EPOCH_SECONDS + int(relative_seconds)


def sanitize_outer_frame(
    raw: bytes,
    *,
    frame_timestamp: int,
    first_timestamp: int,
    original_uid: int,
    original_write_key: int,
    original_mac: str,
    synthetic_write_key: int,
) -> bytes:
    outer = parse_outer(raw)
    payload = bytearray(outer.payload)
    inner = unwrap_inner(outer)
    safe_epoch = safe_epoch_for_timestamp(frame_timestamp, first_timestamp)
    if inner is not None:
        inner_payload = bytearray(inner.payload)
        if inner.command == CMD_CHALLENGE and len(inner_payload) >= 4:
            inner_payload[:4] = struct.pack("<I", synthetic_write_key)
        elif inner.command == CMD_CONFIG and len(inner_payload) >= 8:
            inner_payload[:4] = struct.pack("<I", safe_epoch)
            inner_payload[4:8] = b"\x00\x00\x00\x00"
        elif inner.command == CMD_PING and len(inner_payload) >= 4:
            inner_payload[:4] = struct.pack("<I", safe_epoch)
        elif inner.command in CMD_REALTIME and len(inner_payload) >= 25:
            possible_epoch = int.from_bytes(inner_payload[21:25], "little")
            if 1_577_836_800 <= possible_epoch <= 1_893_456_000:
                inner_payload[21:25] = struct.pack("<I", safe_epoch)
        new_inner = InnerFrame(
            command=inner.command,
            uid=SYNTHETIC_UID,
            sequence=inner.sequence,
            payload=bytes(inner_payload),
            error=inner.error,
            version=inner.version,
        )
        old_inner_bytes = inner.to_bytes()
        location = bytes(payload).find(old_inner_bytes)
        if location >= 0:
            payload[location : location + len(old_inner_bytes)] = new_inner.to_bytes()

    old_uid_le = struct.pack("<Q", original_uid)
    old_key_le = struct.pack("<I", original_write_key)
    new_uid_le = struct.pack("<Q", SYNTHETIC_UID)
    new_key_le = struct.pack("<I", synthetic_write_key)
    old_mac = bytes.fromhex(original_mac.replace(":", "").replace("-", ""))
    new_mac = bytes.fromhex(SYNTHETIC_MAC.replace(":", ""))
    replacements = (
        (old_uid_le, new_uid_le),
        (old_key_le, new_key_le),
        (old_mac, new_mac),
        (old_mac[::-1], new_mac[::-1]),
    )
    sanitized_payload = bytes(payload)
    for old, new in replacements:
        sanitized_payload = sanitized_payload.replace(old, new)
    return OuterFrame(
        outer.command,
        outer.sequence,
        sanitized_payload,
        outer.flags,
    ).to_bytes()


def sanitize_value_streams(
    messages: list[AttMessage],
    selected: list[tuple[AttMessage, int]],
    *,
    original_uid: int,
    original_write_key: int,
    original_mac: str,
    synthetic_write_key: int,
    first_timestamp: int,
) -> dict[int, bytes]:
    groups: dict[tuple[int, str, int, int], list[AttMessage]] = {}
    for message, session_index in selected:
        handle = message.attribute_handle
        if handle is None or not message.value:
            continue
        key = (session_index, message.direction, message.connection, handle)
        groups.setdefault(key, []).append(message)

    sanitized_att: dict[int, bytes] = {}
    for group in groups.values():
        stream = b"".join(message.value for message in group)
        mutable = bytearray(stream)
        ranges: list[tuple[int, int, AttMessage]] = []
        stream_offset = 0
        for message in group:
            end = stream_offset + len(message.value)
            ranges.append((stream_offset, end, message))
            stream_offset = end

        cursor = 0
        while cursor + 8 <= len(stream):
            magic = stream.find(b"\xfe", cursor)
            if magic < 0 or magic + 8 > len(stream):
                break
            total = struct.unpack(">H", stream[magic + 2 : magic + 4])[0]
            if total < 8 or magic + total > len(stream):
                cursor = magic + 1
                continue
            raw_frame = stream[magic : magic + total]
            frame_message = next(
                message
                for start, end, message in ranges
                if start <= magic < end
            )
            try:
                sanitized_frame = sanitize_outer_frame(
                    raw_frame,
                    frame_timestamp=frame_message.timestamp,
                    first_timestamp=first_timestamp,
                    original_uid=original_uid,
                    original_write_key=original_write_key,
                    original_mac=original_mac,
                    synthetic_write_key=synthetic_write_key,
                )
            except ValueError:
                cursor = magic + 1
                continue
            if len(sanitized_frame) != len(raw_frame):
                raise ValueError("sanitization changed an outer frame length")
            mutable[magic : magic + total] = sanitized_frame
            cursor = magic + total

        stream_offset = 0
        for message in group:
            end = stream_offset + len(message.value)
            new_value = bytes(mutable[stream_offset:end])
            sanitized_att[message.ordinal] = message.att[:3] + new_value
            stream_offset = end
    return sanitized_att


def write_sanitized_btsnoop(
    output: Path,
    header: bytes,
    selected: list[tuple[AttMessage, int]],
    sanitized_att: dict[int, bytes],
    first_timestamp: int,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    connection_map: dict[tuple[int, int], int] = {}
    next_connection = 1
    chunks = [header]
    for message, session_index in selected:
        map_key = (session_index, message.connection)
        if map_key not in connection_map:
            connection_map[map_key] = next_connection
            next_connection += 1
        connection = connection_map[map_key]
        att = sanitized_att.get(message.ordinal, message.att)
        l2cap = struct.pack("<HH", len(att), ATT_CID) + att
        handle_flags = connection | (2 << 12)
        packet = b"\x02" + struct.pack("<HH", handle_flags, len(l2cap)) + l2cap
        timestamp = (
            BTSNOOP_EPOCH_DELTA_US
            + SAFE_UNIX_EPOCH_SECONDS * 1_000_000
            + max(0, message.timestamp - first_timestamp)
        )
        chunks.append(
            struct.pack(
                ">IIIIQ",
                len(packet),
                len(packet),
                message.flags,
                0,
                timestamp,
            )
        )
        chunks.append(packet)
    output.write_bytes(b"".join(chunks))


def sanitize_capture(
    source: Path,
    output: Path,
    summary_path: Path,
    *,
    original_uid: int,
    original_write_key: int,
    original_mac: str,
) -> dict[str, Any]:
    header, records = read_btsnoop(source)
    messages = extract_att_messages(records)
    markers = find_foci_frame_markers(messages)
    if not markers:
        raise ValueError(f"no FOCI application frames found in {source}")
    sessions = cluster_sessions(markers)
    selected: list[tuple[AttMessage, int]] = []
    for message in messages:
        session_index = session_for_message(message, sessions)
        if session_index is not None:
            selected.append((message, session_index))
    first_timestamp = min(message.timestamp for message, _ in selected)
    synthetic_write_key, _ = derive_write_key(SYNTHETIC_UID, SYNTHETIC_MAC)
    sanitized_att = sanitize_value_streams(
        messages,
        selected,
        original_uid=original_uid,
        original_write_key=original_write_key,
        original_mac=original_mac,
        synthetic_write_key=synthetic_write_key,
        first_timestamp=first_timestamp,
    )
    write_sanitized_btsnoop(
        output, header, selected, sanitized_att, first_timestamp
    )
    summary = {
        "source_label": source.name,
        "privacy": {
            "contains_only_target_att_windows": True,
            "absolute_capture_timestamps_rebased": True,
            "application_timestamps_rebased_when_known": True,
            "timezone_zeroed_in_configuration_commands": True,
            "device_uid_replaced": True,
            "write_key_replaced": True,
            "device_mac_replaced": True,
            "pairing_and_non_att_traffic_removed": True,
            "synthetic_uid_hex": f"0x{SYNTHETIC_UID:016x}",
            "synthetic_mac": SYNTHETIC_MAC,
            "synthetic_write_key_hex": f"0x{synthetic_write_key:08x}",
        },
        "input": {
            "btsnoop_records": len(records),
            "att_pdus": len(messages),
            "foci_frames": len(markers),
        },
        "output": {
            "att_pdus": len(selected),
            "bytes": output.stat().st_size,
            "session_count": len(sessions),
        },
        "sessions": [
            {
                "index": index + 1,
                "frame_count": session["frame_count"],
                "duration_seconds": round(
                    (
                        session["last_frame_timestamp"]
                        - session["first_frame_timestamp"]
                    )
                    / 1_000_000,
                    3,
                ),
            }
            for index, session in enumerate(sessions)
        ],
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return summary


def number(value: str) -> int:
    return int(value, 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a privacy-sanitized, FOCI-only btsnoop capture."
    )
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--uid", type=number, required=True)
    parser.add_argument("--write-key", type=number, required=True)
    parser.add_argument("--mac", required=True)
    args = parser.parse_args()
    summary = sanitize_capture(
        args.source,
        args.output,
        args.summary,
        original_uid=args.uid,
        original_write_key=args.write_key,
        original_mac=args.mac,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
