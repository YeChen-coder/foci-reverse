from __future__ import annotations

import hashlib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = PROJECT_ROOT / "DATA_INVENTORY.md"
EXCLUDED_NAMES = {"DATA_INVENTORY.md"}
EXCLUDED_DIRS = {".git", ".pytest_cache", "__pycache__"}


def digest(path: Path) -> str:
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha256.update(block)
    return sha256.hexdigest()


def main() -> None:
    files = sorted(
        (
            path
            for path in PROJECT_ROOT.rglob("*")
            if path.is_file()
            and path.name not in EXCLUDED_NAMES
            and not any(part in EXCLUDED_DIRS for part in path.parts)
        ),
        key=lambda path: path.relative_to(PROJECT_ROOT).as_posix(),
    )
    total_bytes = sum(path.stat().st_size for path in files)
    lines = [
        "# 发布包数据清单",
        "",
        "本表由 `tools/build_inventory.py` 生成。SHA-256 覆盖当前公开目录内除",
        "`DATA_INVENTORY.md` 自身之外的所有发布文件；ZIP 外层容器不在表内。",
        "",
        f"- 文件数：{len(files)}",
        f"- 总字节数：{total_bytes:,}",
        "",
        "| 相对路径 | 字节数 | SHA-256 |",
        "| --- | ---: | --- |",
    ]
    for path in files:
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        lines.append(
            f"| `{relative}` | {path.stat().st_size:,} | `{digest(path)}` |"
        )
    lines.append("")
    OUTPUT.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Wrote {OUTPUT.name}: {len(files)} files, {total_bytes} bytes")


if __name__ == "__main__":
    main()
