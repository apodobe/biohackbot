#!/usr/bin/env python3
"""Rule-based DISCREPANCIES.json: out-of-range labs, stale imaging, missing fields."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item_id(category: str, payload: str) -> str:
    digest = hashlib.sha256(f"{category}|{payload}".encode()).hexdigest()[:12]
    return f"disc_{category}_{digest}"


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_out_of_range(row: dict[str, Any]) -> bool:
    val = row.get("value")
    if not isinstance(val, (int, float)):
        return False
    ref_lo = row.get("ref_low")
    ref_hi = row.get("ref_high")
    if isinstance(ref_lo, (int, float)) and val < ref_lo:
        return True
    if isinstance(ref_hi, (int, float)) and val > ref_hi:
        return True
    return False


def _lab_discrepancies(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for row in rows:
        if not _is_out_of_range(row):
            continue
        key = row.get("canonical_key") or "?"
        name = row.get("name_ru") or key
        val = row.get("value")
        unit = row.get("unit") or ""
        spec_date = row.get("specimen_date") or "?"
        ref_lo = row.get("ref_low")
        ref_hi = row.get("ref_high")
        source = row.get("source_path") or ""
        detail = (
            f"{name}: {val} {unit} (реф. {ref_lo}–{ref_hi}), дата {spec_date}"
        )
        items.append(
            {
                "id": _item_id("lab", f"{key}|{spec_date}|{val}"),
                "severity": "medium",
                "category": "lab_out_of_range",
                "title_ru": f"Вне референса: {name}",
                "detail_ru": detail,
                "canonical_key": key,
                "specimen_date": spec_date,
                "sources": [source] if source else [],
            }
        )
    return items


def _stale_imaging(corpus: Path, *, years: float = 2.0) -> list[dict[str, Any]]:
    timeline_path = corpus / "TIMELINE_EVENTS.json"
    if not timeline_path.exists():
        return []
    data = json.loads(timeline_path.read_text(encoding="utf-8"))
    today = datetime.now(timezone.utc).date()
    cutoff_days = int(years * 365.25)
    items: list[dict[str, Any]] = []

    for ev in data.get("events") or []:
        if ev.get("type") != "imaging":
            continue
        ev_date = _parse_date(str(ev.get("date") or ""))
        if not ev_date:
            continue
        age_days = (today - ev_date).days
        if age_days <= cutoff_days:
            continue
        title = ev.get("title_ru") or "Лучевая диагностика"
        sources = ev.get("sources") or []
        years_ago = round(age_days / 365.25, 1)
        items.append(
            {
                "id": _item_id("imaging", f"{ev.get('id')}|{ev_date}"),
                "severity": "low",
                "category": "stale_imaging",
                "title_ru": f"Устаревшее исследование: {title}",
                "detail_ru": (
                    f"Дата {ev_date.isoformat()} ({years_ago} лет назад); "
                    f"рекомендуется актуализация по клиническим показаниям"
                ),
                "event_date": ev_date.isoformat(),
                "sources": sources,
            }
        )
    return items


def _missing_field_discrepancies(
    rows: list[dict[str, Any]], corpus: Path
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    missing_loinc = sum(1 for r in rows if not r.get("loinc"))
    if missing_loinc:
        items.append(
            {
                "id": _item_id("missing", f"loinc|{missing_loinc}"),
                "severity": "low",
                "category": "missing_data",
                "title_ru": "Лаборатория без LOINC",
                "detail_ru": (
                    f"{missing_loinc} из {len(rows)} строк LABS_NORMALIZED "
                    f"без кода LOINC"
                ),
                "sources": ["LABS_NORMALIZED.json"],
            }
        )

    missing_value = [
        r for r in rows if r.get("value") in (None, "") and r.get("canonical_key")
    ]
    for row in missing_value[:50]:
        key = row.get("canonical_key") or "?"
        spec_date = row.get("specimen_date") or "?"
        source = row.get("source_path") or ""
        items.append(
            {
                "id": _item_id("missing", f"value|{key}|{spec_date}"),
                "severity": "medium",
                "category": "missing_data",
                "title_ru": f"Пустое значение: {key}",
                "detail_ru": f"Нет value для {key}, дата {spec_date}",
                "canonical_key": key,
                "specimen_date": spec_date,
                "sources": [source] if source else [],
            }
        )

    goals_path = corpus / "GOALS_REMINDERS.json"
    if goals_path.exists():
        goals = json.loads(goals_path.read_text(encoding="utf-8"))
        active = [i for i in goals.get("items") or [] if i.get("active")]
        if not active:
            items.append(
                {
                    "id": _item_id("missing", "goals_empty"),
                    "severity": "low",
                    "category": "missing_data",
                    "title_ru": "Нет активных напоминаний",
                    "detail_ru": "GOALS_REMINDERS.json: активных items = 0",
                    "sources": ["GOALS_REMINDERS.json"],
                }
            )

    return items


def generate_discrepancies(corpus: Path, *, apply: bool = True) -> dict[str, int]:
    labs_path = corpus / "LABS_NORMALIZED.json"
    out_path = corpus / "DISCREPANCIES.json"
    if not labs_path.exists():
        raise FileNotFoundError(labs_path)

    labs = json.loads(labs_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = labs.get("rows") or []

    items: list[dict[str, Any]] = []
    items.extend(_lab_discrepancies(rows))
    items.extend(_stale_imaging(corpus))
    items.extend(_missing_field_discrepancies(rows, corpus))

    # dedupe by id
    by_id: dict[str, dict[str, Any]] = {}
    for item in items:
        by_id[str(item["id"])] = item
    items = list(by_id.values())
    items.sort(key=lambda i: (i.get("severity", ""), i.get("category", "")))

    payload = {
        "version": 1,
        "generated_at": _utc_now(),
        "items": items,
        "meta": {
            "generator": "scripts/generate_discrepancies.py",
            "rules": ["lab_out_of_range", "stale_imaging>2yr", "missing_data"],
            "extracted_by": "composer",
            "review_status": "pending_gemini_opus",
        },
    }

    stats = {
        "total": len(items),
        "lab_out_of_range": sum(1 for i in items if i["category"] == "lab_out_of_range"),
        "stale_imaging": sum(1 for i in items if i["category"] == "stale_imaging"),
        "missing_data": sum(1 for i in items if i["category"] == "missing_data"),
    }

    if apply:
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate DISCREPANCIES.json")
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
        stats = generate_discrepancies(corpus, apply=not args.dry_run)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"{mode}: total={stats['total']} "
        f"lab_out_of_range={stats['lab_out_of_range']} "
        f"stale_imaging={stats['stale_imaging']} "
        f"missing_data={stats['missing_data']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
