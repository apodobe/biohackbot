#!/usr/bin/env python3
"""Write CORPUS_INDEX.json — unified nav map (idamedbot / mymedbot / meiramedbot)."""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medbots.config import find_bot_root, load_config
from medbots.corpus_io import bot_root, default_corpus_root

REPO = bot_root()
CORPUS = default_corpus_root()

PROFILES: dict[str, dict[str, Any]] = {
    "idamedbot": {
        "patient": "Синельник Ида Исааковна",
        "patient_dob": "1959-03-24",
        "corpus_path_vps": "/opt/medical-corpus/structured_database",
        "mac_ingest": "python3 scripts/_extract_pdfs.py && bash scripts/run_corpus_pipeline.sh",
        "read_order_extra_after_discrepancies": ["WEEKLY_PENDING_EXAMS.json"],
        "read_order_tail": ["manifest.json", "doc_text/", "pdf_text/", "genomics/"],
        "source_folders": {
            "flat_pdfs": "repo root + Мама телеграмм/ — legacy flat PDF paths in manifest",
            "genomics": "structured_database/genomics/ — VCF panel",
        },
        "prompt_files": {
            "bot_minimal_en": "AI_SYSTEM_BRIEF_EN.md",
            "bot_full_en": "PROMPT_AGENT_EN.md",
            "genetics": "genomics/PROMPT_GENETICS_OPUS.md",
            "opus_en": "PROMPT_OPUS_EN.md",
            "opus_ru": "PROMPT_OPUS_RU.md",
            "file_map": "README_FOR_OPUS.md",
            "ai_prep": "AI_PREP_README.md",
            "standard": "docs/MED_BOTS_CORPUS_STANDARD.md",
        },
    },
    "mymedbot": {
        "patient": None,
        "patient_dob": None,
        "corpus_path_vps": "/opt/biohacking-corpus/structured_database",
        "mac_ingest": "bash scripts/run_corpus_pipeline.sh",
        "read_order_extra_after_discrepancies": [],
        "read_order_tail": [
            "GOALS_REMINDERS.json",
            "TIMELINE_EVENTS.json",
            "manifest.json",
            "doc_text/",
            "supplements/",
            "nutrition/",
            "fitness/",
            "biohacking/",
            "genomics/",
        ],
        "source_folders": {
            "medsi": "sources/medsi/",
            "emias": "sources/emias/",
            "gemotest": "sources/gemotest/",
        },
        "prompt_files": {
            "bot_minimal_en": "AI_SYSTEM_BRIEF_EN.md",
            "bot_full_en": "PROMPT_AGENT_EN.md",
            "genetics": "genomics/PROMPT_GENETICS_OPUS.md",
            "opus_en": "PROMPT_OPUS_EN.md",
            "opus_ru": "PROMPT_OPUS_RU.md",
            "file_map": "README_FOR_OPUS.md",
            "ai_prep": "AI_PREP_README.md",
            "standard": "docs/MED_BOTS_CORPUS_STANDARD.md",
        },
    },
    "meiramedbot": {
        "patient": "Осипова Ирина Владимировна",
        "patient_dob": "1992-06-19",
        "corpus_path_vps": "/opt/irina-corpus/structured_database",
        "mac_ingest": "bash scripts/run_full_corpus_ingest.sh",
        "read_order_extra_after_discrepancies": [],
        "read_order_tail": [
            "GOALS_REMINDERS.json",
            "TIMELINE_EVENTS.json",
            "manifest.json",
            "doc_text/",
            "recommendations/",
        ],
        "source_folders": {
            "medsi": "sources/medsi/",
            "emias": "sources/emias/",
            "emias_inspections": "sources/emias_inspections/",
            "emias_emergency": "sources/Скорая + госпитализация/",
        },
        "prompt_files": {
            "bot_minimal_en": "AI_SYSTEM_BRIEF_EN.md",
            "bot_full_en": "PROMPT_AGENT_EN.md",
            "batch_review_en": "PROMPT_VPS_PREP_EN.md",
            "opus_en": "PROMPT_OPUS_EN.md",
            "opus_ru": "PROMPT_OPUS_RU.md",
            "file_map": "README_FOR_OPUS.md",
            "ai_prep": "AI_PREP_README.md",
            "standard": "docs/MED_BOTS_CORPUS_STANDARD.md",
        },
    },
}

DATE_IN_PDF = re.compile(r"(20\d{2})[-_](\d{2})[-_](\d{2})")


def _detect_bot() -> str:
    env = os.environ.get("MED_BOT", "").strip().lower()
    if env in PROFILES:
        return env
    try:
        cfg = load_config(find_bot_root())
        if cfg.bot_id in PROFILES:
            return cfg.bot_id
    except OSError:
        pass
    name = REPO.name.lower()
    if "irina" in name or "healthbot" in name and "bio" not in name:
        return "meiramedbot"
    if "biohack" in name:
        return "mymedbot"
    if "анализ" in name or name == "анализы":
        return "idamedbot"
    return "meiramedbot"


def _entry_date(entry: dict[str, Any]) -> str | None:
    created = (entry.get("created_at") or "")[:10]
    if created and len(created) == 10 and created != "unknown-date":
        return created
    sp = entry.get("source_pdf") or ""
    m = DATE_IN_PDF.search(sp)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def _patient_from_profile(corpus: Path, profile: dict[str, Any]) -> tuple[str, str | None]:
    patient = profile.get("patient")
    dob = profile.get("patient_dob")
    pp = corpus / "PATIENT_PROFILE.json"
    if pp.exists():
        data = json.loads(pp.read_text(encoding="utf-8"))
        patient = patient or data.get("full_name_ru") or data.get("name")
        dob = dob or data.get("dob")
    return patient or "unknown", dob


def build_index(bot: str) -> dict[str, Any]:
    profile = PROFILES[bot]
    manifest = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
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
            if sp.startswith("sources/"):
                sys_name = sp.split("/")[1]
            else:
                sys_name = "legacy_flat"
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

    patient, dob = _patient_from_profile(CORPUS, profile)
    read_order = [
        "AI_SYSTEM_BRIEF_EN.md",
        "PROMPT_AGENT_EN.md",
        "CORPUS_INDEX.json",
        "DISCREPANCIES.json",
        "LIVING_HEALTH_SUMMARY.md",
        "LABS_NORMALIZED.json",
        *profile.get("read_order_extra_after_discrepancies", []),
        *profile.get("read_order_tail", []),
    ]

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bot": bot,
        "patient": meta.get("patient") or patient,
        "patient_dob": meta.get("patient_dob") or dob,
        "corpus_path_vps": profile["corpus_path_vps"],
        "corpus_path_mac": str(CORPUS),
        "totals": {
            "pdfs": len(pdfs),
            "with_pdf_text": with_pdf_text,
            "with_doc_text": with_doc_text,
            "date_range": {"min": date_min, "max": date_max},
        },
        "by_source_system": dict(by_source),
        "by_doc_type": dict(by_type),
        "read_order_for_ai": read_order,
        "prompt_files": profile.get("prompt_files", {}),
        "source_folders": profile.get("source_folders", {}),
        "deploy": {
            "mac_ingest": profile.get("mac_ingest", ""),
            "vps_rsync": "openclaw-vps-deploy/02-rsync-corpus.sh",
            "standard": "docs/MED_BOTS_CORPUS_STANDARD.md",
            "note": "PDF not on VPS; text and JSON only",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--bot",
        choices=sorted(PROFILES),
        default=_detect_bot(),
        help="Bot profile (or MED_BOT env)",
    )
    args = ap.parse_args()
    index = build_index(args.bot)
    out = CORPUS / "CORPUS_INDEX.json"
    out.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {out} bot={args.bot} pdfs={index['totals']['pdfs']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
