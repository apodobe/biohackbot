#!/usr/bin/env python3
"""
Mark GOALS_REMINDERS items inactive when corpus text matches auto_complete_patterns.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_FILENAME_DATE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")


def _file_doc_date(path: Path) -> float | None:
    m = _FILENAME_DATE.match(path.name)
    if not m:
        return None
    try:
        dt = datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
        return dt.timestamp()
    except ValueError:
        return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_goals(corpus: Path) -> dict[str, Any]:
    p = corpus / "GOALS_REMINDERS.json"
    if not p.exists():
        raise FileNotFoundError(p)
    return json.loads(p.read_text(encoding="utf-8"))


def _corpus_haystack(
    corpus: Path,
    extra: str = "",
    *,
    recent_days: int | None = None,
) -> str:
    parts: list[str] = [extra]
    if recent_days is None:
        timeline = corpus / "TIMELINE_EVENTS.json"
        if timeline.exists():
            parts.append(timeline.read_text(encoding="utf-8", errors="replace"))
    cutoff = 0.0
    if recent_days is not None:
        cutoff = datetime.now(timezone.utc).timestamp() - recent_days * 86400
    for sub in ("pdf_text", "doc_text"):
        d = corpus / sub
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.txt")) + sorted(d.glob("*.md")):
            if recent_days is not None:
                doc_ts = _file_doc_date(f)
                if doc_ts is None or doc_ts < cutoff:
                    continue
            parts.append(f.name)
            try:
                parts.append(f.read_text(encoding="utf-8", errors="replace")[:4000])
            except OSError:
                pass
    return "\n".join(parts)


def _matches(patterns: list[str], haystack: str) -> bool:
    for pat in patterns:
        if re.search(pat, haystack, flags=re.IGNORECASE):
            return True
    return False


def reconcile(
    corpus: Path,
    *,
    apply: bool,
    extra_haystack: str = "",
    recent_days: int | None = None,
    ingest_only: bool = False,
) -> list[str]:
    data = _load_goals(corpus)
    if ingest_only:
        haystack = extra_haystack
    else:
        haystack = _corpus_haystack(corpus, extra_haystack, recent_days=recent_days)
    changed: list[str] = []
    for item in data.get("items") or []:
        if not item.get("active"):
            continue
        patterns = item.get("auto_complete_patterns")
        if not patterns:
            continue
        if _matches(patterns, haystack):
            item["active"] = False
            stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            note = f" (авто-снято {stamp}: найдено в корпусе)"
            item["why_ru"] = (item.get("why_ru") or "").rstrip() + note
            changed.append(str(item.get("id", "?")))

    meta = data.setdefault("meta", {})
    meta["last_auto_sync"] = _utc_now()
    if apply and changed:
        out = corpus / "GOALS_REMINDERS.json"
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changed


def reconcile_after_ingest(
    corpus: Path,
    *,
    rel_source: str,
    title_ru: str | None = None,
    conclusion_ru: str | None = None,
    apply: bool = True,
) -> list[str]:
    extra = f"{rel_source}\n{title_ru or ''}\n{conclusion_ru or ''}"
    return reconcile(corpus, apply=apply, extra_haystack=extra, ingest_only=True)


def main() -> int:
    ap = argparse.ArgumentParser(description="Reconcile GOALS_REMINDERS.json with corpus")
    ap.add_argument(
        "--corpus",
        type=Path,
        default=None,
    )
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--recent-days", type=int, default=0)
    args = ap.parse_args()
    from medbots.corpus_io import default_corpus_root
    if getattr(args, "corpus", None) is None:
        args.corpus = default_corpus_root()
    corpus = args.corpus.expanduser().resolve()
    if not corpus.is_dir():
        print(f"ERROR: corpus not found: {corpus}", file=sys.stderr)
        return 1
    recent = args.recent_days if args.recent_days > 0 else None
    changed = reconcile(corpus, apply=args.apply, recent_days=recent)
    mode = "applied" if args.apply else "dry-run"
    if changed:
        print(f"{mode}: deactivated {', '.join(changed)}")
    else:
        print(f"{mode}: no active items matched auto_complete_patterns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
