from __future__ import annotations

import hashlib
import struct
import time
from dataclasses import asdict, dataclass
from typing import Any

OUTER_MAGIC = 0xFE
OUTER_HEADER_SIZE = 8
INNER_HEADER_SIZE = 17

CMD_NATIVE_REQUEST = 26505
CMD_HEARTBEAT = 26509
CMD_SEND_DATA = 30001
CMD_CHALLENGE = 27514
CMD_PING = 27512
CMD_CONFIG = 27536
CMD_VIBRATION_INTENSITY = 27510
# ProtocolV2Processor accepts all three as FnRealTimeDataEntity. The live
# Galaxy S22 capture from this FOCI firmware uses 27545.
CMD_REALTIME = {27526, 27540, 27545}

ALERT_MASKS = {
    "distraction": 0x0010,
    "early_distraction": 0x1000,
    "focus_slip": 0x0440,
    "tense": 0x0080,
    "fatigue": 0x0200,
}

STATE_LABELS = {
    0: "recalculating",
    1: "not_worn",
    2: "adapting",
    3: "in_motion",
    4: "distracted",
    5: "calm",
    6: "focused",
    7: "stressed",
    9: "fatigued",
    10: "flow",
}


@dataclass(slots=True)
class OuterFrame:
    command: int
    sequence: int
    payload: bytes
    flags: int = 0

    def to_bytes(self) -> bytes:
        total = OUTER_HEADER_SIZE + len(self.payload)
        return struct.pack(
            ">BBHHH", OUTER_MAGIC, self.flags, total, self.command, self.sequence
        ) + self.payload


@dataclass(slots=True)
class InnerFrame:
    command: int
    uid: int
    sequence: int
    payload: bytes
    error: int = 0
    version: int = 1

    def to_bytes(self) -> bytes:
        total = INNER_HEADER_SIZE + len(self.payload)
        return struct.pack(
            "<BHHHQH",
            self.version,
            total,
            self.command,
            self.error,
            self.uid,
            self.sequence,
        ) + self.payload


class OuterFrameAssembler:
    """Reassemble FOCI outer frames split across BLE notifications."""

    def __init__(self) -> None:
        self.buffer = bytearray()

    def feed(self, chunk: bytes | bytearray) -> list[OuterFrame]:
        self.buffer.extend(chunk)
        frames: list[OuterFrame] = []
        while True:
            while self.buffer and self.buffer[0] != OUTER_MAGIC:
                del self.buffer[0]
            if len(self.buffer) < OUTER_HEADER_SIZE:
                break
            _, flags, total, command, sequence = struct.unpack(
                ">BBHHH", self.buffer[:OUTER_HEADER_SIZE]
            )
            if total < OUTER_HEADER_SIZE or total > 65535:
                del self.buffer[0]
                continue
            if len(self.buffer) < total:
                break
            payload = bytes(self.buffer[OUTER_HEADER_SIZE:total])
            del self.buffer[:total]
            frames.append(OuterFrame(command, sequence, payload, flags))
        return frames


def encode_varint(value: int) -> bytes:
    if value < 0:
        raise ValueError("varint must be non-negative")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def decode_varint(data: bytes, offset: int = 0) -> tuple[int, int]:
    value = 0
    shift = 0
    while offset < len(data) and shift < 70:
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, offset
        shift += 7
    raise ValueError("truncated or invalid varint")


def protobuf_length_fields(data: bytes) -> dict[int, list[bytes]]:
    """Extract length-delimited fields from the tiny protobuf envelope."""
    fields: dict[int, list[bytes]] = {}
    offset = 0
    while offset < len(data):
        key, offset = decode_varint(data, offset)
        field_number, wire_type = key >> 3, key & 7
        if wire_type == 2:
            length, offset = decode_varint(data, offset)
            end = offset + length
            if end > len(data):
                raise ValueError("truncated protobuf field")
            fields.setdefault(field_number, []).append(data[offset:end])
            offset = end
        elif wire_type == 0:
            _, offset = decode_varint(data, offset)
        elif wire_type == 1:
            offset += 8
        elif wire_type == 5:
            offset += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire_type}")
        if offset > len(data):
            raise ValueError("truncated protobuf value")
    return fields


def parse_outer(data: bytes) -> OuterFrame:
    if len(data) < OUTER_HEADER_SIZE:
        raise ValueError("outer frame is shorter than 8 bytes")
    magic, flags, total, command, sequence = struct.unpack(">BBHHH", data[:8])
    if magic != OUTER_MAGIC:
        raise ValueError("bad outer frame magic")
    if total != len(data):
        raise ValueError(f"outer length says {total}, received {len(data)}")
    return OuterFrame(command, sequence, data[8:], flags)


def parse_inner(data: bytes) -> InnerFrame:
    if len(data) < INNER_HEADER_SIZE:
        raise ValueError("inner frame is shorter than 17 bytes")
    version, total, command, error, uid, sequence = struct.unpack(
        "<BHHHQH", data[:INNER_HEADER_SIZE]
    )
    if total != len(data):
        raise ValueError(f"inner length says {total}, received {len(data)}")
    return InnerFrame(command, uid, sequence, data[17:], error, version)


def wrap_inner(inner: InnerFrame, outer_sequence: int = 1) -> bytes:
    raw = inner.to_bytes()
    # SendDataRequest: field 1 is an empty BaseRequest; field 2 is Data.
    envelope = b"\x0a\x00\x12" + encode_varint(len(raw)) + raw
    return OuterFrame(CMD_SEND_DATA, outer_sequence, envelope).to_bytes()


def unwrap_inner(outer: OuterFrame) -> InnerFrame | None:
    try:
        values = protobuf_length_fields(outer.payload).get(2, [])
    except ValueError:
        return None
    for value in values:
        try:
            return parse_inner(value)
        except ValueError:
            continue
    return None


def build_native_request(sequence: int = 1) -> bytes:
    return OuterFrame(CMD_NATIVE_REQUEST, sequence, b"\x19").to_bytes()


def build_heartbeat(timestamp_ms: int, sequence: int = 1) -> bytes:
    return OuterFrame(
        CMD_HEARTBEAT, sequence, struct.pack(">I", timestamp_ms & 0xFFFFFFFF)
    ).to_bytes()


def build_inner_command(
    command: int,
    uid: int,
    payload: bytes = b"",
    *,
    inner_sequence: int = 1,
    outer_sequence: int = 1,
) -> bytes:
    return wrap_inner(
        InnerFrame(command, uid, inner_sequence, payload),
        outer_sequence=outer_sequence,
    )


def build_challenge(
    uid: int,
    write_key: int,
    *,
    inner_sequence: int = 1,
    outer_sequence: int = 1,
) -> bytes:
    return build_inner_command(
        CMD_CHALLENGE,
        uid,
        struct.pack("<I", write_key & 0xFFFFFFFF),
        inner_sequence=inner_sequence,
        outer_sequence=outer_sequence,
    )


def decode_alert_flags(flags: int) -> dict[str, bool]:
    return {
        name: (flags & mask) == mask
        for name, mask in ALERT_MASKS.items()
    }


def update_alert_flags(flags: int, alerts: dict[str, bool]) -> int:
    result = flags
    for name, enabled in alerts.items():
        if name not in ALERT_MASKS:
            raise ValueError(f"unknown alert: {name}")
        mask = ALERT_MASKS[name]
        result = result | mask if enabled else result & ~mask
    return result


def build_config_payload(
    *,
    default_flags: int,
    session_flags: int,
    notification_mode: int = 0,
    pacer_mode: int = 0,
    force_harvest: int = 0,
    mindfulness_level: int = 3,
    current_time: int | None = None,
    timezone_offset_ms: int | None = None,
    scores: tuple[int, int, int, int] = (0, 0, 0, 0),
) -> bytes:
    """Serialize TrackerFnConfigEntity exactly as the archived App does."""
    if current_time is None:
        current_time = int(time.time())
    if timezone_offset_ms is None:
        # Android's captured config uses TimeZone.getRawOffset(), i.e. the
        # standard offset without daylight-saving adjustment.
        timezone_offset_ms = -time.timezone * 1000
    for name, value in {
        "notification_mode": notification_mode,
        "pacer_mode": pacer_mode,
        "force_harvest": force_harvest,
        "mindfulness_level": mindfulness_level,
    }.items():
        if not 0 <= value <= 255:
            raise ValueError(f"{name} must fit in one byte")
    return struct.pack(
        "<ii4iII4B",
        current_time,
        timezone_offset_ms,
        *scores,
        default_flags & 0xFFFFFFFF,
        session_flags & 0xFFFFFFFF,
        pacer_mode,
        force_harvest,
        notification_mode,
        mindfulness_level,
    )


def build_config_command(
    uid: int,
    *,
    default_flags: int,
    session_flags: int,
    notification_mode: int = 0,
    pacer_mode: int = 0,
    force_harvest: int = 0,
    mindfulness_level: int = 3,
    current_time: int | None = None,
    timezone_offset_ms: int | None = None,
    inner_sequence: int = 1,
    outer_sequence: int = 1,
) -> bytes:
    payload = build_config_payload(
        default_flags=default_flags,
        session_flags=session_flags,
        notification_mode=notification_mode,
        pacer_mode=pacer_mode,
        force_harvest=force_harvest,
        mindfulness_level=mindfulness_level,
        current_time=current_time,
        timezone_offset_ms=timezone_offset_ms,
    )
    return build_inner_command(
        CMD_CONFIG,
        uid,
        payload,
        inner_sequence=inner_sequence,
        outer_sequence=outer_sequence,
    )


def derive_write_key(uid: int, mac: str) -> tuple[int, bytes]:
    """Reproduce HashUtils.getBoxValidKey() from the archived Android app."""
    unsigned_uid = uid if uid >= 0 else uid + (1 << 64)
    mac_bytes = bytes.fromhex(mac.replace(":", "").replace("-", ""))
    material = f"{unsigned_uid}3BF608C70828{mac_bytes.hex()}".encode()
    first_four = hashlib.md5(material).digest()[:4]
    return int.from_bytes(first_four, "little"), first_four


def parse_realtime_payload(payload: bytes) -> dict[str, Any]:
    if len(payload) < 21:
        raise ValueError(f"real-time body needs at least 21 bytes, got {len(payload)}")
    (
        display_scale,
        raw_state,
        focus_depth,
        calm,
        signal,
        ar1,
        p_m,
        bz,
        ar3,
        ktype,
        e_progress,
        signal_quality,
        mp_score,
        tens_score,
        focus_ev,
        mp_s_bit,
        v_s,
        t_progress,
    ) = struct.unpack("<BBBBBhBBhBBhBBBBBB", payload[:21])
    data_type = raw_state & 0xE0
    state = raw_state & 0x1F
    result: dict[str, Any] = {
        "kind": "realtime",
        "display_scale": display_scale,
        "raw_state": raw_state,
        "data_type": data_type,
        "state": state,
        "state_label": STATE_LABELS.get(state, f"unknown_{state}"),
        "focus_depth": focus_depth,
        "calm": calm,
        "signal": signal,
        "ar1": ar1,
        "p_m": p_m,
        "bz": bz,
        "ar3": ar3,
        "ktype": ktype,
        "e_progress": max(0, e_progress),
        "signal_quality": signal_quality,
        "mp_score": mp_score,
        "tension_score": tens_score,
        "focus_ev": focus_ev,
        "mp_s_bit": mp_s_bit,
        "v_s": v_s,
        "t_progress": t_progress if t_progress <= 100 else 0,
        "raw_hex": payload.hex(" "),
    }
    if data_type == 0x20 and len(payload) >= 8:
        default_flags, session_flags = struct.unpack("<II", payload[-8:])
        result["device_config"] = {
            "default_flags": default_flags,
            "session_flags": session_flags,
            "default_alerts": decode_alert_flags(default_flags),
            "session_alerts": decode_alert_flags(session_flags),
        }
    if data_type == 0x40 and len(payload) >= 30:
        (
            focus_level,
            focus_graph_ea,
            focus_graph_eb,
            batt_discount_factor,
            ar4,
            ar5,
        ) = struct.unpack("<Bbbhhh", payload[21:30])
        result["minute"] = {
            "focus_level": min(100, focus_level),
            "focus_graph_ea": focus_graph_ea,
            "focus_graph_eb": focus_graph_eb,
            "battery_discount_factor": batt_discount_factor,
            "ar4": ar4,
            "ar5": ar5,
        }
    return result


def decode_event(outer: OuterFrame) -> dict[str, Any]:
    event: dict[str, Any] = {
        "kind": "outer",
        "outer_command": outer.command,
        "outer_sequence": outer.sequence,
        "payload_hex": outer.payload.hex(" "),
    }
    inner = unwrap_inner(outer)
    if inner is None:
        return event
    event.update(
        {
            "kind": "inner",
            "inner_command": inner.command,
            "uid": inner.uid,
            "inner_sequence": inner.sequence,
            "error": inner.error,
            "body_hex": inner.payload.hex(" "),
        }
    )
    if inner.command in CMD_REALTIME:
        event.update(parse_realtime_payload(inner.payload))
        event["inner_command"] = inner.command
        event["uid"] = inner.uid
    return event


def dataclass_dict(value: OuterFrame | InnerFrame) -> dict[str, Any]:
    result = asdict(value)
    result["payload"] = value.payload.hex(" ")
    return result
