#!/usr/bin/env python3
"""Generate structured_database/LIVING_HEALTH_SUMMARY.md for LLM consumption."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_excerpt(path: Path, max_lines: int) -> str:
    if not path.exists():
        return f"(файл не найден: {path.name})"
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[:max_lines]).strip()


def _top_keys(rows: list[dict[str, Any]], limit: int = 30) -> list[str]:
    counts = Counter(str(r.get("canonical_key") or "") for r in rows)
    return [k for k, _ in counts.most_common(limit) if k]


def _latest_values(
    rows: list[dict[str, Any]], keys: list[str], per_key: int = 5
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in keys}
    by_key: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        key = str(row.get("canonical_key") or "")
        if key not in out:
            continue
        by_key.setdefault(key, []).append(row)

    for key in keys:
        group = by_key.get(key, [])
        group.sort(key=lambda r: str(r.get("specimen_date") or ""), reverse=True)
        out[key] = group[:per_key]
    return out


def generate_lhm(corpus: Path) -> Path:
    labs_path = corpus / "LABS_NORMALIZED.json"
    timeline_path = corpus / "TIMELINE_EVENTS.json"
    genetics_path = corpus / "genomics" / "GENETICS_SUMMARY.md"
    fitness_path = corpus / "fitness" / "APPLE_HEALTH_SUMMARY.md"
    out_path = corpus / "LIVING_HEALTH_SUMMARY.md"

    labs_data = json.loads(labs_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = labs_data.get("rows") or []
    patient = labs_data.get("patient") or "пациент"

    top_keys = _top_keys(rows, 30)
    latest = _latest_values(rows, top_keys, 5)

    lines: list[str] = [
        "# Живая сводка здоровья (LHM)",
        "",
        f"**Сгенерировано:** {_utc_now()}",
        f"**Пациент:** {patient}",
        "",
        "## Лаборатория — топ-30 показателей (последние 5 значений)",
        "",
    ]

    for key in top_keys:
        samples = latest.get(key) or []
        if not samples:
            continue
        name = samples[0].get("name_ru") or key
        lines.append(f"### {name} (`{key}`)")
        for row in samples:
            val = row.get("value")
            unit = row.get("unit") or ""
            date = row.get("specimen_date") or "?"
            ref_lo = row.get("ref_low")
            ref_hi = row.get("ref_high")
            ref = ""
            if ref_lo is not None or ref_hi is not None:
                ref = f" (реф. {ref_lo}–{ref_hi})"
            loinc = row.get("loinc")
            loinc_s = f", LOINC {loinc}" if loinc else ""
            lines.append(f"- {date}: **{val}** {unit}{ref}{loinc_s}")
        lines.append("")

    lines.extend(["## Хронология — последние 20 событий", ""])
    if timeline_path.exists():
        timeline = json.loads(timeline_path.read_text(encoding="utf-8"))
        events = sorted(
            timeline.get("events") or [],
            key=lambda e: str(e.get("date") or ""),
            reverse=True,
        )[:20]
        for ev in events:
            date = ev.get("date") or "?"
            etype = ev.get("type") or "?"
            title = ev.get("title_ru") or "?"
            lines.append(f"- {date} [{etype}] {title}")
    else:
        lines.append("- (TIMELINE_EVENTS.json не найден)")
    lines.append("")

    lines.extend(
        [
            "## Генетика — выдержка",
            "",
            _read_excerpt(genetics_path, 35),
            "",
            "## Фитнес (Apple Health) — выдержка",
            "",
            _read_excerpt(fitness_path, 80),
            "",
            "---",
            "Полные данные: `LABS_NORMALIZED.json`, `TIMELINE_EVENTS.json`, `genomics/`, `fitness/`.",
            "",
        ]
    )

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate LIVING_HEALTH_SUMMARY.md")
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
    if not corpus.is_dir():
        print(f"ERROR: corpus not found: {corpus}", file=sys.stderr)
        return 1
    try:
        out = generate_lhm(corpus)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    lines = out.read_text(encoding="utf-8").splitlines()
    print(f"wrote {out} ({len(lines)} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
