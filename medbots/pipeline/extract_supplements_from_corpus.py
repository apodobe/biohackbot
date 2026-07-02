#!/usr/bin/env python3
"""Composer v0: extract supplement/medication mentions from doc_text + GOALS_REMINDERS."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_DATE_FRONT = re.compile(r"^date:\s*(\d{4}-\d{2}-\d{2})\s*$", re.M)
_TITLE_FRONT = re.compile(r"^title:\s*(.+?)\s*$", re.M)

_REC_SECTIONS = re.compile(
    r"^(?:рекомендац\w*|медикаментозн\w*\s+терап\w*|аптека|нутрицевтик\w*|схема\s+приема|"
    r"назначен\w*|лечение)\s*:?\s*$",
    re.I | re.M,
)

_MED_LINE = re.compile(
    r"(?:"
    r"(?:прием|принимать|назнач\w*|курс|подключить|медикаментозн\w*\s+терап\w*)[^.\n]{0,120}|"
    r"(?:[А-ЯA-Z][а-яa-zё\-]+(?:[\s\-][А-ЯA-Z0-9][а-яa-zё0-9\-]*){0,4})\s*"
    r"(?:\d+\s*(?:мг|ме|мкг|мл|г|шт|таб|капс?\.?|р/д|раз)[^.\n]{0,80})"
    r")",
    re.I,
)

_KNOWN = re.compile(
    r"\b("
    r"урсосан|креон|рабепразол|эзомепразол|омепразол|магни\w*|мелатонин|"
    r"витамин\s*[а-яa-z0-9]+|таурин|фермент\w*|ингавирин|парацетамол|"
    r"энтеросгель|регидрон|энтерофурил|сумамед|флемоксин|хемомицин|"
    r"чёрн\w*\s+тмин|тмин|протеин|омега[\s-]*3|донат\s+магни\w*|mivela|magnesium"
    r")\b",
    re.I,
)

_DOSE_FRAGMENT = re.compile(
    r"(\d+(?:[.,]\d+)?\s*(?:мг|ме|мкг|мл|г|шт)(?:\s*/\s*сут)?"
    r"(?:\s*(?:\d+\s*раз|по\s+\d+|1\s*р/д|3\s*р/д|на\s+завтрак|до\s+сна|после\s+\w+)){0,3})",
    re.I,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item_id(name: str, source: str, snippet: str) -> str:
    digest = hashlib.sha256(f"{name}|{source}|{snippet}".encode()).hexdigest()[:12]
    return f"sup_{digest}"


def _doc_meta(text: str, path: Path) -> tuple[str | None, str]:
    dm = _DATE_FRONT.search(text)
    doc_date = dm.group(1) if dm else None
    tm = _TITLE_FRONT.search(text)
    title = tm.group(1).strip() if tm else path.stem
    return doc_date, title


def _normalize_name(raw: str) -> str:
    s = re.sub(r"\s+", " ", raw).strip(" .;,-")
    return s[:120] if s else ""


def _extract_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("|") or s.startswith("---"):
            continue
        if _KNOWN.search(s) or _MED_LINE.search(s):
            lines.append(s)
    # recommendation sections — grab following bullets
    for m in _REC_SECTIONS.finditer(text):
        chunk = text[m.end() : m.end() + 2500]
        for line in chunk.splitlines():
            s = line.strip().lstrip("-*•").strip()
            if len(s) < 8:
                continue
            if _KNOWN.search(s) or _MED_LINE.search(s) or "мг" in s.lower():
                lines.append(s)
    return lines


def _parse_mention(line: str, *, doc_date: str | None, title: str, rel_path: str) -> dict[str, Any] | None:
    known = _KNOWN.search(line)
    if not known and not re.search(r"\d+\s*мг", line, re.I):
        return None
    name_match = known.group(1) if known else None
    if not name_match:
        # first capitalized token sequence as weak name
        nm = re.search(r"([А-ЯA-Z][а-яa-zё\-]+(?:[\s\-][А-ЯA-Z0-9][а-яa-zё0-9\-]*){0,3})", line)
        name_match = nm.group(1) if nm else line[:60]
    name_ru = _normalize_name(name_match)
    if len(name_ru) < 3:
        return None
    dose_m = _DOSE_FRAGMENT.search(line)
    dose_raw = dose_m.group(1).strip() if dose_m else None
    snippet = _normalize_name(line)
    if len(snippet) < 10:
        return None
    return {
        "id": _item_id(name_ru, rel_path, snippet),
        "name_ru": name_ru,
        "dose_raw": dose_raw,
        "schedule_raw": snippet if dose_raw is None else snippet,
        "source_path": rel_path,
        "doc_date": doc_date,
        "source_title_ru": title,
        "context_ru": snippet,
        "active": True,
        "status": "mentioned_in_document",
        "extracted_by": "composer",
        "extracted_at": _utc_now(),
    }


def _from_goals(goals_path: Path) -> list[dict[str, Any]]:
    if not goals_path.exists():
        return []
    data = json.loads(goals_path.read_text(encoding="utf-8"))
    out: list[dict[str, Any]] = []
    for g in data.get("items") or []:
        if g.get("type") != "supplement":
            continue
        title = str(g.get("title_ru") or "")
        if not _KNOWN.search(title) and "витамин" not in title.lower():
            continue
        rel = g.get("source_path") or ""
        snippet = re.sub(r"\*+", "", title).strip()
        name_m = _KNOWN.search(snippet)
        name_ru = _normalize_name(name_m.group(1) if name_m else snippet[:80])
        out.append(
            {
                "id": _item_id(name_ru, rel, snippet),
                "name_ru": name_ru,
                "dose_raw": None,
                "schedule_raw": snippet,
                "source_path": rel,
                "doc_date": g.get("doc_date"),
                "source_title_ru": None,
                "context_ru": snippet,
                "active": bool(g.get("active", True)),
                "status": "from_goals_reminders",
                "extracted_by": "composer",
                "extracted_at": _utc_now(),
            }
        )
    return out


def extract_supplements(corpus: Path, *, apply: bool = True) -> dict[str, int]:
    doc_dir = corpus / "doc_text"
    if not doc_dir.is_dir():
        raise FileNotFoundError(doc_dir)

    items_by_id: dict[str, dict[str, Any]] = {}
    doc_mentions = 0

    for path in sorted(doc_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        doc_date, title = _doc_meta(text, path)
        rel = f"doc_text/{path.name}"
        seen_snippets: set[str] = set()
        for line in _extract_lines(text):
            key = line.lower()[:200]
            if key in seen_snippets:
                continue
            seen_snippets.add(key)
            item = _parse_mention(line, doc_date=doc_date, title=title, rel_path=rel)
            if item and item["id"] not in items_by_id:
                items_by_id[item["id"]] = item
                doc_mentions += 1

    for item in _from_goals(corpus / "GOALS_REMINDERS.json"):
        if item["id"] not in items_by_id:
            items_by_id[item["id"]] = item

    regimen = sorted(items_by_id.values(), key=lambda x: (x.get("doc_date") or "", x["name_ru"]))

    primary = corpus / "supplements" / "SUPPLEMENTS.json"
    mirror = corpus / "biohacking" / "SUPPLEMENTS.json"
    payload: dict[str, Any] = {
        "version": 1,
        "regimen": regimen,
        "intake_log": [],
        "meta": {
            "note": "Composer v0 draft — review with Gemini/Opus before clinical use",
            "extracted_by": "composer",
            "extracted_at": _utc_now(),
            "extract_script": "scripts/extract_supplements_from_corpus.py",
            "review_status": "pending_gemini",
        },
    }

    stats = {
        "regimen_count": len(regimen),
        "from_doc_text": doc_mentions,
        "unique_names": len({r["name_ru"].lower() for r in regimen}),
    }

    if apply:
        primary.parent.mkdir(parents=True, exist_ok=True)
        primary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        mirror.parent.mkdir(parents=True, exist_ok=True)
        mirror.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract supplements/meds from corpus (Composer v0)")
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
    try:
        stats = extract_supplements(corpus, apply=not args.dry_run)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"{mode}: regimen={stats['regimen_count']} "
        f"doc_mentions={stats['from_doc_text']} unique_names={stats['unique_names']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
