#!/usr/bin/env python3
"""Composer v0: enrich PROTOCOLS.json from doc_text (lifestyle + exam cadence)."""
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

_EXAM_CADENCE = re.compile(
    r"(?:"
    r"эгдс\s+раз\s+в\s+\d+\s+(?:год|года|лет)[^.\n]{0,120}|"
    r"узи\s+[^.\n]{0,40}раз\s+в\s+(?:год|год\w*)[^.\n]{0,80}|"
    r"флюорограф\w*[^.\n]{0,80}(?:раз\s+в|ежегодн\w*)[^.\n]{0,60}|"
    r"контрольн\w*\s+(?:анализ\w*|узи|эгдс)[^.\n]{0,100}|"
    r"сдать\s+контрольн\w*\s+анализ\w*[^.\n]{0,80}|"
    r"инсулин[^.\n]{0,60}(?:раз\s+в|6\s*мес)[^.\n]{0,40}|"
    r"гликированн\w*\s+гемоглобин[^.\n]{0,60}"
    r")",
    re.I,
)

_LIFESTYLE = re.compile(
    r"(?:"
    r"контрастн\w*\s+душ[^.\n]{0,200}|"
    r"10\s*000\s+шагов[^.\n]{0,120}|"
    r"отбой\s+до\s+23[^.\n]{0,120}|"
    r"гимнастик\w*\s+для\s+желчеоттока[^.\n]{0,120}|"
    r"натощак\s+[^.\n]{0,40}вод\w*[^.\n]{0,80}|"
    r"3\s+прием\w*\s+пищ\w*\s+без\s+перекус\w*[^.\n]{0,80}"
    r")",
    re.I,
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _proto_id(category: str, snippet: str) -> str:
    digest = hashlib.sha256(f"{category}|{snippet}".encode()).hexdigest()[:10]
    return f"proto_{category}_{digest}"


def _doc_meta(text: str, path: Path) -> tuple[str | None, str]:
    dm = _DATE_FRONT.search(text)
    doc_date = dm.group(1) if dm else None
    tm = _TITLE_FRONT.search(text)
    title = tm.group(1).strip() if tm else path.stem
    return doc_date, title


def _normalize(s: str, max_len: int = 300) -> str:
    s = re.sub(r"\*+", "", s)
    s = re.sub(r"\s+", " ", s).strip(" .;,-")
    return s[:max_len] if len(s) > max_len else s


def _category_for(snippet: str) -> str:
    low = snippet.lower()
    if any(x in low for x in ("эгдс", "узи", "флюорограф", "анализ", "инсулин", "гликирован")):
        return "monitoring"
    if "душ" in low or "шаг" in low or "сон" in low or "отбой" in low:
        return "lifestyle"
    if "пищ" in low or "перекус" in low:
        return "nutrition"
    if "желче" in low or "вод" in low:
        return "digestion"
    return "general"


def extract_protocols(corpus: Path, *, apply: bool = True) -> dict[str, int]:
    proto_path = corpus / "biohacking" / "PROTOCOLS.json"
    if proto_path.exists():
        data: dict[str, Any] = json.loads(proto_path.read_text(encoding="utf-8"))
    else:
        data = {"version": 1, "protocols": [], "meta": {}}

    existing_ids = {p.get("id") for p in data.get("protocols") or []}
    existing_steps = {
        tuple(p.get("steps_ru") or []) for p in data.get("protocols") or []
    }
    new_count = 0
    doc_dir = corpus / "doc_text"

    for path in sorted(doc_dir.glob("*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        doc_date, title = _doc_meta(text, path)
        rel = f"doc_text/{path.name}"
        for pattern in (_EXAM_CADENCE, _LIFESTYLE):
            for m in pattern.finditer(text):
                snippet = _normalize(m.group(0))
                if len(snippet) < 20:
                    continue
                steps = (snippet,)
                if steps in existing_steps:
                    continue
                cat = _category_for(snippet)
                pid = _proto_id(cat, snippet)
                if pid in existing_ids:
                    continue
                data.setdefault("protocols", []).append(
                    {
                        "id": pid,
                        "name_ru": snippet[:80] + ("…" if len(snippet) > 80 else ""),
                        "category": cat,
                        "status": "recommended",
                        "schedule": "по рекомендации врача",
                        "steps_ru": [snippet],
                        "doc_date": doc_date,
                        "source_path": rel,
                        "why_ru": f"Извлечено из «{title}»",
                        "extracted_by": "composer",
                        "extracted_at": _utc_now(),
                    }
                )
                existing_ids.add(pid)
                existing_steps.add(steps)
                new_count += 1

    meta = data.setdefault("meta", {})
    meta["updated_at"] = _utc_now()[:10]
    meta["extracted_by"] = "composer"
    meta["review_status"] = "pending_gemini"

    stats = {"total": len(data.get("protocols") or []), "new": new_count}
    if apply:
        proto_path.parent.mkdir(parents=True, exist_ok=True)
        proto_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


def main() -> int:
    ap = argparse.ArgumentParser(description="Enrich PROTOCOLS.json from doc_text")
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
    stats = extract_protocols(corpus, apply=not args.dry_run)
    mode = "dry-run" if args.dry_run else "applied"
    print(f"{mode}: protocols total={stats['total']} new={stats['new']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
