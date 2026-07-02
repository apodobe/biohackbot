#!/usr/bin/env python3
"""Apply labs/LOINC_MAP.tsv to LABS_NORMALIZED rows where loinc is null."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def _load_loinc_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            key = (row.get("canonical_key") or "").strip()
            code = (row.get("loinc") or "").strip()
            if key and code:
                mapping[key] = code
    return mapping


def apply_loinc_map(corpus: Path, *, apply: bool = True) -> dict[str, int]:
    labs_path = corpus / "LABS_NORMALIZED.json"
    map_path = corpus / "labs" / "LOINC_MAP.tsv"
    if not labs_path.exists():
        raise FileNotFoundError(labs_path)
    if not map_path.exists():
        raise FileNotFoundError(map_path)

    loinc_map = _load_loinc_map(map_path)
    data: dict[str, Any] = json.loads(labs_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = data.get("rows") or []

    stats = {
        "rows_total": len(rows),
        "loinc_before": sum(1 for r in rows if r.get("loinc")),
        "loinc_null_before": sum(1 for r in rows if not r.get("loinc")),
        "applied": 0,
        "unmapped_keys": 0,
    }
    unmapped: set[str] = set()

    for row in rows:
        if row.get("loinc"):
            continue
        key = row.get("canonical_key") or ""
        code = loinc_map.get(key)
        if code:
            row["loinc"] = code
            stats["applied"] += 1
        elif key:
            unmapped.add(key)

    stats["unmapped_keys"] = len(unmapped)
    stats["loinc_after"] = sum(1 for r in rows if r.get("loinc"))
    stats["loinc_null_after"] = sum(1 for r in rows if not r.get("loinc"))

    if apply:
        labs_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Apply LOINC_MAP.tsv to LABS_NORMALIZED.json")
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
        stats = apply_loinc_map(corpus, apply=not args.dry_run)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"{mode}: rows={stats['rows_total']} "
        f"loinc {stats['loinc_before']}->{stats['loinc_after']} "
        f"applied={stats['applied']} unmapped_keys={stats['unmapped_keys']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
