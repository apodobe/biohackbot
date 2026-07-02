#!/usr/bin/env python3
"""Extract exam/supplement reminders from consultation doc_text/*.md (no API)."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CONSULT_TYPE = re.compile(r"^type:\s*(consult|consultation)\s*$", re.M | re.I)
_CONSULT_TITLE = re.compile(r"осмотр|консультац|прием\s+врач", re.I)
_DATE_FRONT = re.compile(r"^date:\s*(\d{4}-\d{2}-\d{2})\s*$", re.M)
_TITLE_FRONT = re.compile(r"^title:\s*(.+?)\s*$", re.M)

_EXAM_LINE = re.compile(
    r"(?:"
    r"сдать\s+(?:контрольн\w*\s+)?анализ\w*|"
    r"контрольн\w*\s+анализ\w*|"
    r"контроль\s+узи|узи\s+в\s+динамик\w*|"
    r"повторн\w*\s+(?:осмотр|консультац|узи|анализ|флюорограф)\w*|"
    r"через\s+\d+\s+(?:нед|мес|месяц)\w*[^.\n]{0,80}(?:контроль|сдать|узи|анализ)|"
    r"(?:флюорограф\w*|колоноскоп\w*|гастроскоп\w*|маммограф\w*|"
    r"денситометр\w*|холтер)(?:\s+[^.\n]{0,60})?|"
    r"(?<![а-яёa-z])(?:мрт|кт|узи|экг)(?![а-яёa-z])\s+[^.\n]{0,80}|"
    r"после\s+(?:программ\w*|курс\w*)\s+сдать[^.\n]{0,120}"
    r")",
    re.I,
)

_SUPPLEMENT_LINE = re.compile(
    r"(?:"
    r"(?:прием|принимать|подключить|назнач\w*|курс)\s+[^.\n]{0,80}"
    r"(?:витамин|магни|мелатонин|омега|урсосан|нутрицевтик|бад)|"
    r"(?:витамин\s*[a-zа-яё0-9]+|магни\w+|мелатонин|омега[\s-]*3|"
    r"урсосан|нутрицевтик\w*|бад\w*)\s*[^.\n]{0,60}"
    r"(?:\d+\s*(?:мг|ме|мкг|мл|шт)|на\s+завтрак|до\s+сна|1\s*раз)"
    r")",
    re.I,
)

_REC_SECTION = re.compile(r"^рекомендац\w*\s*$", re.I | re.M)

_NOISE = re.compile(
    r"^(?:рекомендации|аптека|образ жизни|питание|исключить|основные принципы)\s*:?\s*$",
    re.I,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _item_id(doc_stem: str, kind: str, text: str) -> str:
    digest = hashlib.sha256(f"{doc_stem}|{kind}|{text}".encode()).hexdigest()[:12]
    return f"goal_{kind}_{digest}"


def _normalize_snippet(text: str, max_len: int = 160) -> str:
    s = re.sub(r"\s+", " ", text).strip(" .;,-")
    if len(s) > max_len:
        return s[: max_len - 1] + "…"
    return s


def _is_consultation(path: Path, text: str) -> bool:
    if _CONSULT_TYPE.search(text):
        return True
    m = _TITLE_FRONT.search(text)
    if m and _CONSULT_TITLE.search(m.group(1)):
        return True
    if _CONSULT_TITLE.search(path.stem):
        return True
    return False


def _doc_meta(text: str, path: Path) -> tuple[str | None, str]:
    date_m = _DATE_FRONT.search(text)
    doc_date = date_m.group(1) if date_m else None
    title_m = _TITLE_FRONT.search(text)
    title = title_m.group(1).strip() if title_m else path.stem
    return doc_date, title


def _recommendation_lines(body: str) -> list[str]:
    """Prefer explicit recommendation blocks; fall back to full body."""
    chunks: list[str] = []
    for block in re.split(r"^#{1,3}\s+", body, flags=re.M):
        if _REC_SECTION.search(block[:80]):
            chunks.append(block)
    if chunks:
        return [ln.strip() for ch in chunks for ln in ch.splitlines() if ln.strip()]
    # Inline «Рекомендации» section inside code blocks / EMIAS text
    inline: list[str] = []
    in_rec = False
    for line in body.splitlines():
        stripped = line.strip()
        if re.match(r"^рекомендац\w*\s*:?\s*$", stripped, re.I):
            in_rec = True
            continue
        if in_rec and re.match(
            r"^(?:дата|полис|медицинск|специализац|фио|осмотр|заключение)\b",
            stripped,
            re.I,
        ):
            in_rec = False
        if in_rec and stripped:
            inline.append(stripped)
    if inline:
        return inline
    return [ln.strip() for ln in body.splitlines() if ln.strip()]


def _extract_from_text(
    text: str, path: Path, rel_path: str
) -> list[dict[str, Any]]:
    doc_date, title = _doc_meta(text, path)
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    body = text
    if "## Детали" in body:
        body = body.split("## Детали", 1)[1]
    elif "## Заключение" in body:
        body = body.split("## Заключение", 1)[1]

    candidates = _recommendation_lines(body)
    if not candidates:
        candidates = [ln.strip() for ln in body.splitlines() if ln.strip()]

    for line in candidates:
        if not line or line.startswith("```") or line.startswith("|"):
            continue
        if _NOISE.match(line):
            continue
        if len(line) < 10:
            continue

        kind: str | None = None
        if _EXAM_LINE.search(line):
            kind = "exam"
        elif _SUPPLEMENT_LINE.search(line):
            kind = "supplement"
        if not kind:
            continue

        snippet = _normalize_snippet(line)
        if len(snippet) < 15:
            continue
        dedupe_key = f"{kind}:{snippet.lower()}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        items.append(
            {
                "id": _item_id(path.stem, kind, snippet),
                "type": kind,
                "active": True,
                "title_ru": snippet,
                "why_ru": f"Извлечено из «{title}» ({doc_date or 'дата неизвестна'})",
                "doc_date": doc_date,
                "source_path": rel_path,
                "auto_complete_patterns": [],
                "extracted_by": "composer",
            }
        )
    return items


def extract_goals(corpus: Path, *, apply: bool = True) -> dict[str, int]:
    doc_dir = corpus / "doc_text"
    goals_path = corpus / "GOALS_REMINDERS.json"
    if not doc_dir.is_dir():
        raise FileNotFoundError(doc_dir)

    if goals_path.exists():
        data: dict[str, Any] = json.loads(goals_path.read_text(encoding="utf-8"))
    else:
        data = {
            "version": 1,
            "items": [],
            "meta": {
                "note": "Unified reminders: exam | supplement | workout | metric | biohack",
                "last_auto_sync": None,
            },
        }

    existing_ids = {str(i.get("id")) for i in data.get("items") or []}
    new_items: list[dict[str, Any]] = []
    consult_docs = 0

    for path in sorted(doc_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if not _is_consultation(path, text):
            continue
        consult_docs += 1
        rel = f"doc_text/{path.name}"
        for item in _extract_from_text(text, path, rel):
            if item["id"] in existing_ids:
                continue
            existing_ids.add(item["id"])
            new_items.append(item)

    data["items"] = list(data.get("items") or [])
    data["items"].extend(new_items)
    meta = data.setdefault("meta", {})
    meta["last_extract"] = _utc_now()
    meta["extract_note"] = "scripts/extract_goals_from_doc_text.py"
    meta["extracted_by"] = "composer"
    meta["review_status"] = "pending_gemini"

    stats = {
        "consult_docs": consult_docs,
        "new_items": len(new_items),
        "exam_items": sum(1 for i in new_items if i["type"] == "exam"),
        "supplement_items": sum(1 for i in new_items if i["type"] == "supplement"),
        "total_items": len(data["items"]),
    }

    if apply:
        goals_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Extract goals from consultation doc_text")
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
        stats = extract_goals(corpus, apply=not args.dry_run)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    mode = "dry-run" if args.dry_run else "applied"
    print(
        f"{mode}: consult_docs={stats['consult_docs']} "
        f"new={stats['new_items']} (exam={stats['exam_items']} "
        f"supplement={stats['supplement_items']}) total={stats['total_items']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
