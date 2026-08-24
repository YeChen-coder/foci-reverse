import struct

from foci_ble.protocol import (
    CMD_CHALLENGE,
    CMD_SEND_DATA,
    InnerFrame,
    OuterFrameAssembler,
    build_challenge,
    build_config_command,
    build_config_payload,
    build_heartbeat,
    build_native_request,
    parse_outer,
    parse_realtime_payload,
    decode_alert_flags,
    update_alert_flags,
    unwrap_inner,
)


def test_native_request_matches_app_packet():
    assert build_native_request(1).hex() == "fe0000096789000119"


def test_heartbeat_direct_outer_packet():
    assert build_heartbeat(0x12345678, 3).hex() == "fe00000c678d000312345678"


def test_challenge_round_trip():
    raw = build_challenge(
        0x1122334455667788,
        0xA1B2C3D4,
        inner_sequence=7,
        outer_sequence=9,
    )
    outer = parse_outer(raw)
    assert outer.command == CMD_SEND_DATA
    assert outer.sequence == 9
    inner = unwrap_inner(outer)
    assert isinstance(inner, InnerFrame)
    assert inner.command == CMD_CHALLENGE
    assert inner.uid == 0x1122334455667788
    assert inner.sequence == 7
    assert inner.payload == struct.pack("<I", 0xA1B2C3D4)


def test_challenge_matches_sanitized_capture():
    raw = build_challenge(
        0x1122334455667788,
        0x89DB6C54,
        inner_sequence=1,
        outer_sequence=2,
    )
    assert raw.hex() == (
        "fe000021753100020a0012150115007a6b0000"
        "88776655443322110100546cdb89"
    )


def test_split_notification_reassembly():
    raw = bytes.fromhex(
        "fe010023271100010a0018848004200128023a06"
        "0200000000016207464f4349203241"
    )
    assembler = OuterFrameAssembler()
    assert assembler.feed(raw[:20]) == []
    frames = assembler.feed(raw[20:])
    assert len(frames) == 1
    assert frames[0].command == 0x2711
    assert frames[0].payload.endswith(b"FOCI 2A")


def test_realtime_payload_layout():
    payload = struct.pack(
        "<BBBBBhBBhBBhBBBBBB",
        100,
        6,
        72,
        63,
        88,
        -123,
        5,
        9,
        456,
        6,
        42,
        91,
        67,
        23,
        4,
        1,
        2,
        85,
    )
    result = parse_realtime_payload(payload)
    assert result["state_label"] == "focused"
    assert result["focus_depth"] == 72
    assert result["signal_quality"] == 91
    assert result["t_progress"] == 85


def test_alert_masks_match_individual_s22_switch_capture():
    baseline = 0x1010
    flags = update_alert_flags(baseline, {"distraction": False})
    assert flags == 0x1000
    flags = update_alert_flags(flags, {"early_distraction": False})
    assert flags == 0
    flags = update_alert_flags(flags, {"focus_slip": True})
    assert flags == 0x0440
    flags = update_alert_flags(flags, {"tense": True})
    assert flags == 0x04C0
    flags = update_alert_flags(flags, {"fatigue": True})
    assert flags == 0x06C0
    assert decode_alert_flags(flags) == {
        "distraction": False,
        "early_distraction": False,
        "focus_slip": True,
        "tense": True,
        "fatigue": True,
    }


def test_config_payload_matches_s22_deep_work_capture():
    payload = build_config_payload(
        current_time=0x67748580,
        timezone_offset_ms=0,
        default_flags=0x0450,
        session_flags=0x0440,
        notification_mode=1,
    )
    assert payload.hex(" ") == (
        "80 85 74 67 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 "
        "50 04 00 00 40 04 00 00 00 00 01 03"
    )
    packet = build_config_command(
        0x1122334455667788,
        current_time=0x67748580,
        timezone_offset_ms=0,
        default_flags=0x0450,
        session_flags=0x0440,
        notification_mode=1,
    )
    inner = unwrap_inner(parse_outer(packet))
    assert inner is not None
    assert inner.command == 27536
    assert inner.payload == payload
