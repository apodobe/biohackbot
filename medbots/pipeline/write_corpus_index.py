#!/usr/bin/env python3
"""Write CORPUS_INDEX.json — navigation summary for the corpus."""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medbots.config import find_bot_root, load_config
from medbots.corpus_io import default_corpus_root, load_patient_dob, resolve_corpus

DATE_IN_PDF = re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})")


def _entry_date(entry: dict[str, Any]) -> str | None:
    created = (entry.get("created_at") or "")[:10]
    if created and len(created) == 10 and created != "unknown-date":
        return created
    sp = entry.get("source_pdf") or ""
    m = DATE_IN_PDF.search(sp)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def build_index(corpus: Path, bot_id: str, vps_path: str) -> dict[str, Any]:
    manifest_path = corpus / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {"pdfs": [], "meta": {}}
    pdfs = manifest.get("pdfs") or []
    meta = manifest.get("meta") or {}

    by_source: Counter[str] = Counter()
    by_type: Counter[str] = Counter()
    with_doc_text = 0
    with_pdf_text = 0
    date_min = None
    date_max = None

    for entry in pdfs:
        sys_name = entry.get("source_system")
        if not sys_name:
            sp = entry.get("source_pdf") or ""
            sys_name = sp.split("/")[1] if sp.startswith("sources/") else "other"
        by_source[sys_name] += 1
        by_type[entry.get("doc_type") or "other"] += 1
        if entry.get("doc_text"):
            with_doc_text += 1
        if entry.get("extracted_txt"):
            with_pdf_text += 1
        d = _entry_date(entry)
        if d:
            date_min = d if date_min is None or d < date_min else date_min
            date_max = d if date_max is None or d > date_max else date_max

    profile_path = corpus / "PATIENT_PROFILE.json"
    patient = meta.get("patient")
    if profile_path.exists():
        data = json.loads(profile_path.read_text(encoding="utf-8"))
        patient = patient or data.get("full_name_ru") or data.get("name")
    dob = meta.get("patient_dob") or load_patient_dob(corpus) or None

    read_order = [
        "CORPUS_INDEX.json",
        "DISCREPANCIES.json",
        "LABS_NORMALIZED.json",
        "LIVING_HEALTH_SUMMARY.md",
        "GOALS_REMINDERS.json",
        "TIMELINE_EVENTS.json",
        "manifest.json",
        "doc_text/",
        "pdf_text/",
    ]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bot_id": bot_id,
        "patient": patient,
        "patient_dob": dob,
        "corpus_path_vps": vps_path or None,
        "corpus_path_local": str(corpus),
        "totals": {
            "pdfs": len(pdfs),
            "with_pdf_text": with_pdf_text,
            "with_doc_text": with_doc_text,
            "date_range": {"min": date_min, "max": date_max},
        },
        "by_source_system": dict(by_source),
        "by_doc_type": dict(by_type),
        "read_order": read_order,
        "workflow": {
            "scan": "medbots scan --bot-root <instance>",
            "extract": "medbots extract-text --bot-root <instance>",
            "structure": "medbots structure --bot-root <instance>",
            "pipeline": "medbots pipeline --bot-root <instance>",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate CORPUS_INDEX.json")
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--bot-root", type=Path, default=None)
    args = ap.parse_args()

    root = (args.bot_root or find_bot_root()).resolve()
    cfg = load_config(root)
    corpus = resolve_corpus(args.corpus) if args.corpus else resolve_corpus(root / "structured_database")

    index = build_index(corpus, cfg.bot_id, cfg.vps_corpus_path)
    out = corpus / "CORPUS_INDEX.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} pdfs={index['totals']['pdfs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
