#!/usr/bin/env python3
"""Index Composer v0 artifacts pending Gemini/Fable/Opus review."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_index(corpus: Path) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    goals_path = corpus / "GOALS_REMINDERS.json"
    if goals_path.exists():
        g = json.loads(goals_path.read_text(encoding="utf-8"))
        items.append(
            {
                "artifact": "GOALS_REMINDERS.json",
                "path": str(goals_path.relative_to(corpus)),
                "count": len(g.get("items") or []),
                "review_model": "gemini",
                "prompt_en": "Review GOALS_REMINDERS.json vs doc_text; dedupe, prioritize, mark inactive stale items.",
                "prompt_ru": "Проверь GOALS vs doc_text; дедуп, приоритеты, inactive для устаревших.",
            }
        )

    disc_path = corpus / "DISCREPANCIES.json"
    if disc_path.exists():
        d = json.loads(disc_path.read_text(encoding="utf-8"))
        items.append(
            {
                "artifact": "DISCREPANCIES.json",
                "path": str(disc_path.relative_to(corpus)),
                "count": len(d.get("items") or []),
                "review_model": "gemini_then_opus",
                "prompt_en": "Review DISCREPANCIES.json; merge duplicates, fix false positives; Opus adds narrative_ru for top high.",
                "prompt_ru": "Проверь DISCREPANCIES; убери ложные; Opus — narrative_ru для top high.",
            }
        )

    for rel, model, pe, pr in (
        (
            "supplements/SUPPLEMENTS.json",
            "gemini",
            "Normalize doses/schedules in SUPPLEMENTS regimen; merge duplicates; set active flags.",
            "Нормализуй дозы/схемы в SUPPLEMENTS; дедуп; active/inactive.",
        ),
        (
            "biohacking/PROTOCOLS.json",
            "gemini",
            "Merge PROTOCOLS duplicates; split vague entries; add schedule where explicit in source.",
            "Объедини дубли PROTOCOLS; уточни schedule из source_path.",
        ),
        (
            "LIVING_HEALTH_SUMMARY.md",
            "fable",
            "Rewrite LHM v2: trends, genetics, goals; max 400 lines; corpus-only.",
            "LHM v2: тренды, генетика, цели; ≤400 строк; только корпус.",
        ),
        (
            "nutrition/NUTRITION.json",
            "fable",
            "Add clinical_context_ru per recipe cluster from nutritionist consult.",
            "Добавь clinical_context_ru к рецептам из консультации.",
        ),
    ):
        p = corpus / rel
        if p.exists():
            count = None
            if p.suffix == ".json":
                data = json.loads(p.read_text(encoding="utf-8"))
                if rel == "nutrition/NUTRITION.json":
                    count = len(
                        data.get("meal_templates")
                        or data.get("recipes")
                        or data.get("items")
                        or []
                    )
                else:
                    count = len(
                        data.get("protocols")
                        or data.get("regimen")
                        or data.get("items")
                        or []
                    )
            items.append(
                {
                    "artifact": rel,
                    "path": rel,
                    "count": count,
                    "review_model": model,
                    "prompt_en": pe,
                    "prompt_ru": pr,
                }
            )

    return {
        "version": 1,
        "generated_at": _utc_now(),
        "composer_pass": "phase2_v0",
        "pending_reviews": items,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--corpus",
        type=Path,
        default=None,
    )
    args = ap.parse_args()
    from medbots.corpus_io import default_corpus_root
    if getattr(args, "corpus", None) is None:
        args.corpus = default_corpus_root()
    corpus = args.corpus.expanduser().resolve()
    bio_dir = corpus / "biohacking"
    out = (
        bio_dir / "COMPOSER_REVIEW_INDEX.json"
        if bio_dir.is_dir()
        else corpus / "COMPOSER_REVIEW_INDEX.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = build_index(corpus)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out} reviews={len(payload['pending_reviews'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
