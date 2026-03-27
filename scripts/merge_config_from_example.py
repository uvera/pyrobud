#!/usr/bin/env python3
"""Add missing config keys from config.example.toml into an existing config.toml.

Never overwrites keys that already exist (any value). Only inserts keys and
subsections that are absent so your api_id, prefix, version, comments on
existing lines, etc. stay untouched.

Usage (from repo root):
  python scripts/merge_config_from_example.py
  python scripts/merge_config_from_example.py --config /path/to/config.toml --dry-run
"""

from __future__ import annotations

import argparse
import copy
import os
import sys
from pathlib import Path
from typing import List

import tomlkit
from tomlkit.items import Table
from tomlkit.toml_document import TOMLDocument

_REPO_ROOT = Path(__file__).resolve().parents[1]


def _is_table(value: object) -> bool:
    return isinstance(value, Table)


def add_missing_keys(dst: Table, src: Table, trail: str) -> List[str]:
    """Recursively copy from src into dst only keys missing in dst. Returns dotted paths added."""
    added: List[str] = []
    for key, value in src.items():
        path = f"{trail}.{key}" if trail else key
        if key not in dst:
            dst[key] = copy.deepcopy(value)
            added.append(path)
        elif _is_table(value) and _is_table(dst[key]):
            added.extend(add_missing_keys(dst[key], value, path))
    return added


def _atomic_write(path: Path, text: str) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    done = False
    try:
        with tmp_path.open("w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        tmp_path.replace(path)
        done = True
    finally:
        if not done and tmp_path.exists():
            tmp_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.toml"),
        help="Existing config to update (default: ./config.toml)",
    )
    parser.add_argument(
        "--example",
        type=Path,
        default=_REPO_ROOT / "config.example.toml",
        help="Template with defaults (default: repo config.example.toml)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print keys that would be added; do not write",
    )
    args = parser.parse_args()

    cfg_path = args.config.resolve()
    ex_path = args.example.resolve()

    if not cfg_path.is_file():
        print(f"error: config not found: {cfg_path}", file=sys.stderr)
        return 1
    if not ex_path.is_file():
        print(f"error: example not found: {ex_path}", file=sys.stderr)
        return 1

    existing = tomlkit.parse(cfg_path.read_text(encoding="utf-8"))
    example = tomlkit.parse(ex_path.read_text(encoding="utf-8"))

    if not isinstance(existing, TOMLDocument):
        print("error: parsed config is not a TOML document", file=sys.stderr)
        return 1

    added = add_missing_keys(existing, example, "")

    if not added:
        print("Nothing to add; config already has every key from the example.")
        return 0

    print("Keys to add (existing values were not changed):")
    for p in added:
        print(f"  + {p}")

    if args.dry_run:
        print("\n(dry-run: no file written)")
        return 0

    _atomic_write(cfg_path, existing.as_string())
    print(f"\nUpdated {cfg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
