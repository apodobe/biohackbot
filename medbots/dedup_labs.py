#!/usr/bin/env python3
"""Deduplicate LABS_NORMALIZED rows by canonical_key + specimen_date."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from medbots.corpus_io import manifest_vendor_index

_SOURCE_TIER = {
    "medsi": 0,
    "gemotest": 1,
    "emias": 2,
}


def _detect_vendor(row: dict[str, Any], manifest_index: dict[str, str]) -> str:
    source_path = str(row.get("source_path") or "").lower()
    for vendor in _SOURCE_TIER:
        if vendor in source_path:
            return vendor

    facility = str(row.get("facility") or "").lower()
    if "медси" in facility or "medsi" in facility:
        return "medsi"
    if "гемотест" in facility or "gemotest" in facility:
        return "gemotest"
    if "емиас" in facility or "emias" in facility:
        return "emias"

    basename = Path(source_path).name
    if basename in manifest_index:
        return manifest_index[basename]

    m = re.match(r"^\d{4}-\d{2}-\d{2}__(.+?)__[0-9a-f]+\.pdf$", basename)
    if m and m.group(1) in manifest_index:
        return manifest_index[m.group(1)]

    return "other"


def _row_score(row: dict[str, Any], manifest_index: dict[str, str]) -> tuple[int, int, int]:
    vendor = _detect_vendor(row, manifest_index)
    tier = _SOURCE_TIER.get(vendor, 9)
    completeness = sum(
        1
        for field in ("value", "unit", "ref_low", "ref_high", "loinc", "facility")
        if row.get(field) not in (None, "")
    )
    has_ref = 1 if row.get("ref_low") is not None or row.get("ref_high") is not None else 0
    return (tier, -completeness, -has_ref)


def dedup_labs(corpus: Path, *, apply: bool = True) -> dict[str, int]:
    labs_path = corpus / "LABS_NORMALIZED.json"
    if not labs_path.exists():
        raise FileNotFoundError(labs_path)

    manifest_index = manifest_vendor_index(corpus)
    data: dict[str, Any] = json.loads(labs_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = data.get("rows") or []

    groups: dict[tuple[str, str | None], list[dict[str, Any]]] = {}
    for row in rows:
        key = (str(row.get("canonical_key") or ""), row.get("specimen_date"))
        groups.setdefault(key, []).append(row)

    kept: list[dict[str, Any]] = []
    removed = 0
    dup_groups = 0
    for group_rows in groups.values():
        if len(group_rows) == 1:
            kept.append(group_rows[0])
            continue
        dup_groups += 1
        best = min(group_rows, key=lambda r: _row_score(r, manifest_index))
        kept.append(best)
        removed += len(group_rows) - 1

    stats = {
        "rows_before": len(rows),
        "rows_after": len(kept),
        "removed": removed,
        "dup_groups": dup_groups,
    }

    if apply:
        data["rows"] = kept
        labs_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Deduplicate LABS_NORMALIZED.json")
    ap.add_argument(
        "--corpus",
        type=Path,
        default=None,
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    from medbots.corpus_io import default_corpus_root
    if getattr(args, "corpus", None) is None:
        args.corpus = default_corpus_root()
    corpus = args.corpus.expanduser().resolve()
    if not corpus.is_dir():
        print(f"ERROR: corpus not found: {corpus}", file=sys.stderr)
        return 1
    try:
        stats = dedup_labs(corpus, apply=not args.dry_run)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"{mode}: rows {stats['rows_before']}->{stats['rows_after']} "
        f"removed={stats['removed']} dup_groups={stats['dup_groups']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
