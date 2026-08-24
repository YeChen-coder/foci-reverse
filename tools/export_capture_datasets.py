from __future__ import annotations

import argparse
import csv
import gzip
import json
import struct
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from foci_ble.protocol import decode_alert_flags  # noqa: E402
from tools.analyze_foci_btsnoop import analyze, att_messages  # noqa: E402


def export_capture(capture: Path, output_dir: Path) -> dict[str, Any]:
    result = analyze(capture)
    frames = result["decoded_frames"]
    first_timestamp = min(
        (frame["timestamp"] for frame in frames),
        default=0,
    )
    stem = capture.stem
    output_dir.mkdir(parents=True, exist_ok=True)

    decoded_path = output_dir / f"{stem}.decoded_frames.jsonl"
    with decoded_path.open("w", encoding="utf-8", newline="\n") as handle:
        for frame in frames:
            entry = {
                "capture": capture.name,
                "relative_seconds": round(
                    (frame["timestamp"] - first_timestamp) / 1_000_000, 6
                ),
                "direction": frame["direction"],
                "connection": frame["connection"],
                "attribute_handle": frame["attribute_handle"],
                "event": frame["event"],
            }
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    att_path = output_dir / f"{stem}.att_pdus.csv.gz"
    att_rows = list(att_messages(capture))
    with gzip.open(att_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "relative_seconds",
                "direction",
                "connection",
                "opcode_hex",
                "attribute_handle_hex",
                "att_hex",
            ],
        )
        writer.writeheader()
        for message in att_rows:
            att = message["att"]
            attribute_handle = ""
            if att and att[0] in {0x12, 0x1B, 0x1D, 0x52} and len(att) >= 3:
                attribute_handle = f"0x{struct.unpack('<H', att[1:3])[0]:04x}"
            writer.writerow(
                {
                    "relative_seconds": round(
                        (message["timestamp"] - first_timestamp) / 1_000_000,
                        6,
                    ),
                    "direction": message["direction"],
                    "connection": message["connection"],
                    "opcode_hex": f"0x{att[0]:02x}" if att else "",
                    "attribute_handle_hex": attribute_handle,
                    "att_hex": att.hex(" "),
                }
            )

    return {
        "capture": capture.name,
        "decoded_frames": len(frames),
        "att_pdus": len(att_rows),
        "decoded_path": decoded_path,
        "att_path": att_path,
        "frames": frames,
        "first_timestamp": first_timestamp,
    }


def export_combined_datasets(
    capture_results: list[dict[str, Any]], datasets_dir: Path
) -> None:
    datasets_dir.mkdir(parents=True, exist_ok=True)
    realtime_fields = [
        "capture",
        "relative_seconds",
        "state",
        "state_label",
        "focus_depth",
        "calm",
        "signal",
        "signal_quality",
        "mp_score",
        "tension_score",
        "focus_ev",
        "mp_s_bit",
        "v_s",
        "t_progress",
    ]
    with (datasets_dir / "realtime_samples.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=realtime_fields)
        writer.writeheader()
        for item in capture_results:
            for frame in item["frames"]:
                event = frame["event"]
                if event.get("kind") != "realtime":
                    continue
                row = {
                    "capture": item["capture"],
                    "relative_seconds": round(
                        (
                            frame["timestamp"]
                            - item["first_timestamp"]
                        )
                        / 1_000_000,
                        6,
                    ),
                }
                row.update(
                    {
                        field: event.get(field, "")
                        for field in realtime_fields[2:]
                    }
                )
                writer.writerow(row)

    alert_names = [
        "distraction",
        "early_distraction",
        "focus_slip",
        "tense",
        "fatigue",
    ]
    config_fields = [
        "capture",
        "relative_seconds",
        "default_flags_hex",
        "session_flags_hex",
        "notification_mode",
        "pacer_mode",
        "force_harvest",
        "mindfulness_level",
    ]
    config_fields += [
        f"default_{name}" for name in alert_names
    ] + [f"session_{name}" for name in alert_names]
    with (datasets_dir / "configuration_transitions.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=config_fields)
        writer.writeheader()
        for item in capture_results:
            for frame in item["frames"]:
                event = frame["event"]
                if event.get("inner_command") != 27536:
                    continue
                body = bytes.fromhex(event["body_hex"])
                if len(body) < 36:
                    continue
                default_flags, session_flags = struct.unpack("<II", body[24:32])
                default_alerts = decode_alert_flags(default_flags)
                session_alerts = decode_alert_flags(session_flags)
                row: dict[str, Any] = {
                    "capture": item["capture"],
                    "relative_seconds": round(
                        (
                            frame["timestamp"]
                            - item["first_timestamp"]
                        )
                        / 1_000_000,
                        6,
                    ),
                    "default_flags_hex": f"0x{default_flags:08x}",
                    "session_flags_hex": f"0x{session_flags:08x}",
                    "pacer_mode": body[32],
                    "force_harvest": body[33],
                    "notification_mode": body[34],
                    "mindfulness_level": body[35],
                }
                row.update(
                    {
                        f"default_{name}": int(default_alerts[name])
                        for name in alert_names
                    }
                )
                row.update(
                    {
                        f"session_{name}": int(session_alerts[name])
                        for name in alert_names
                    }
                )
                writer.writerow(row)

    with (datasets_dir / "capture_counts.csv").open(
        "w", encoding="utf-8", newline=""
    ) as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["capture", "att_pdus", "decoded_frames"],
        )
        writer.writeheader()
        for item in capture_results:
            writer.writerow(
                {
                    "capture": item["capture"],
                    "att_pdus": item["att_pdus"],
                    "decoded_frames": item["decoded_frames"],
                }
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Export readable datasets from sanitized FOCI btsnoop files."
    )
    parser.add_argument("captures", nargs="+", type=Path)
    parser.add_argument("--decoded-dir", required=True, type=Path)
    parser.add_argument("--datasets-dir", required=True, type=Path)
    args = parser.parse_args()
    results = [
        export_capture(capture, args.decoded_dir)
        for capture in args.captures
    ]
    export_combined_datasets(results, args.datasets_dir)
    for result in results:
        print(
            f"{result['capture']}: "
            f"{result['att_pdus']} ATT PDUs, "
            f"{result['decoded_frames']} frames"
        )


if __name__ == "__main__":
    main()
