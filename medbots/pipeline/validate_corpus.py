#!/usr/bin/env python3
"""Validate structured_database corpus before VPS deploy."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from medbots.corpus_io import default_corpus_root


def corpus_root() -> Path:
    return default_corpus_root()


def _report(errors: list[str], warnings: list[str], stats: list[str]) -> None:
    if stats:
        print("STATS:")
        for line in stats:
            print(f"  {line}")
    if errors:
        print("ERRORS:")
        for item in errors:
            print(f"  - {item}")
    if warnings:
        print("WARNINGS:")
        for item in warnings:
            print(f"  - {item}")
    if not errors:
        if warnings:
            print("OK with warnings: critical corpus checks passed")
        else:
            print("OK: corpus validation passed")
    else:
        print("FAIL: corpus validation failed")


def main() -> int:
    root = corpus_root()
    errors: list[str] = []
    warnings: list[str] = []
    stats: list[str] = []

    if not root.is_dir():
        errors.append(f"Corpus directory missing: {root}")
        _report(errors, warnings, stats)
        return 1

    stats.append(f"corpus_path={root}")

    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        errors.append("manifest.json missing")
        _report(errors, warnings, stats)
        return 1

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    pdfs = manifest.get("pdfs", [])
    meta = manifest.get("meta", {})
    expected_count = meta.get("pdf_count")
    actual_count = len(pdfs)

    stats.append(f"manifest_pdfs={actual_count}")
    if expected_count is None:
        warnings.append("manifest.meta.pdf_count missing")
    elif expected_count != actual_count:
        errors.append(
            f"manifest pdf count mismatch: meta.pdf_count={expected_count}, len(pdfs)={actual_count}"
        )
    else:
        stats.append(f"manifest_meta_pdf_count={expected_count} (matches)")

    missing_txt: list[str] = []
    missing_txt_files: list[str] = []
    missing_ingest: list[str] = []
    for entry in pdfs:
        source_pdf = entry.get("source_pdf", "<unknown>")
        extracted = entry.get("extracted_txt")
        if not extracted:
            missing_txt.append(source_pdf)
            continue
        txt_path = root / extracted
        if not txt_path.is_file() or txt_path.stat().st_size == 0:
            missing_txt_files.append(extracted)
        if not entry.get("grok_ingested_at") and not entry.get("structured_locally_at"):
            missing_ingest.append(source_pdf)

    if missing_txt:
        errors.append(f"{len(missing_txt)} manifest PDF(s) missing extracted_txt field")
        for name in missing_txt[:5]:
            errors.append(f"  no extracted_txt: {name}")
        if len(missing_txt) > 5:
            errors.append(f"  ... and {len(missing_txt) - 5} more")
    if missing_txt_files:
        errors.append(f"{len(missing_txt_files)} pdf_text file(s) missing or empty")
        for rel in missing_txt_files[:5]:
            errors.append(f"  missing pdf_text: {rel}")
        if len(missing_txt_files) > 5:
            errors.append(f"  ... and {len(missing_txt_files) - 5} more")
    else:
        stats.append(f"pdf_text_files_ok={actual_count - len(missing_txt)}")

    if missing_ingest:
        errors.append(
            f"{len(missing_ingest)} manifest PDF(s) without grok_ingested_at or structured_locally_at"
        )
        for name in missing_ingest[:5]:
            errors.append(f"  not ingested: {name}")
        if len(missing_ingest) > 5:
            errors.append(f"  ... and {len(missing_ingest) - 5} more")
    else:
        stats.append("ingest_status=all_pdfs_grok_or_structured_locally")

    labs_path = root / "LABS_NORMALIZED.json"
    if not labs_path.is_file():
        errors.append("LABS_NORMALIZED.json missing")
    else:
        labs = json.loads(labs_path.read_text(encoding="utf-8"))
        rows = labs.get("rows", [])
        if not rows:
            errors.append("LABS_NORMALIZED.json has no rows")
        else:
            loinc_filled = sum(1 for row in rows if row.get("loinc"))
            loinc_pct = 100.0 * loinc_filled / len(rows)
            stats.append(f"labs_rows={len(rows)}")
            stats.append(f"labs_loinc_filled={loinc_filled}/{len(rows)} ({loinc_pct:.1f}%)")
            if loinc_pct < 10.0:
                warnings.append(
                    f"Low LOINC coverage in LABS_NORMALIZED: {loinc_pct:.1f}% "
                    "(expected higher after labs/LOINC_MAP.tsv)"
                )

    loinc_map = root / "labs" / "LOINC_MAP.tsv"
    if loinc_map.is_file():
        stats.append(f"labs_loinc_map={loinc_map} ({loinc_map.stat().st_size} bytes)")
    else:
        warnings.append("labs/LOINC_MAP.tsv missing (phase 2.1 artifact)")

    living_summary = root / "LIVING_HEALTH_SUMMARY.md"
    if living_summary.is_file() and living_summary.stat().st_size >= 100:
        stats.append(f"living_health_summary={living_summary.stat().st_size} bytes")
    else:
        warnings.append("LIVING_HEALTH_SUMMARY.md missing or too small (phase 2.6 artifact)")

    for required in ("GOALS_REMINDERS.json", "DISCREPANCIES.json"):
        path = root / required
        if not path.is_file():
            errors.append(f"{required} missing")
        else:
            stats.append(f"{required}=present")

    _report(errors, warnings, stats)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
