#!/usr/bin/env python3
"""Validate Apple Health fitness files after import."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from medbots.corpus_io import resolve_corpus


def validate(corpus: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    fitness = corpus / "fitness"

    meta_path = fitness / "APPLE_HEALTH_META.json"
    if not meta_path.exists():
        errors.append("APPLE_HEALTH_META.json missing — run: medbots import-apple-health --zip export.zip")
        return errors, warnings

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    q = meta.get("quality", {})
    if q.get("status") == "fail":
        errors.extend(q.get("issues", []))
    warnings.extend(q.get("warnings", []))

    bm_path = fitness / "BODY_METRICS.json"
    if not bm_path.exists():
        errors.append("BODY_METRICS.json missing")
        return errors, warnings

    bm = json.loads(bm_path.read_text(encoding="utf-8"))
    apple_entries = [e for e in bm.get("entries", []) if e.get("source") == "apple_health"]
    if not apple_entries:
        warnings.append("No apple_health entries in BODY_METRICS.json")
    ids = [e.get("external_id") for e in apple_entries if e.get("external_id")]
    if len(ids) != len(set(ids)):
        errors.append("Duplicate external_id in BODY_METRICS (apple_health)")

    wo_path = fitness / "WORKOUTS.json"
    if wo_path.exists():
        wo = json.loads(wo_path.read_text(encoding="utf-8"))
        apple_wo = [s for s in wo.get("sessions", []) if s.get("source") == "apple_health"]
        if meta.get("workouts") and len(apple_wo) != meta.get("workouts"):
            warnings.append(
                f"WORKOUTS count mismatch: meta={meta.get('workouts')} file={len(apple_wo)}"
            )

    summary = fitness / "APPLE_HEALTH_SUMMARY.md"
    if not summary.exists() or summary.stat().st_size < 100:
        errors.append("APPLE_HEALTH_SUMMARY.md missing or too small")

    return errors, warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate Apple Health import output")
    ap.add_argument("--corpus", type=Path, default=None)
    args = ap.parse_args()
    corpus = resolve_corpus(args.corpus)
    errors, warnings = validate(corpus)
    if errors:
        print("ERRORS:")
        for e in errors:
            print(f"  - {e}")
    if warnings:
        print("WARNINGS:")
        for w in warnings:
            print(f"  - {w}")
    if not errors and not warnings:
        print("OK: Apple Health validation passed")
    elif not errors:
        print("OK with warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
