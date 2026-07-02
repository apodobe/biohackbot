#!/usr/bin/env python3
"""Extract text from manifest PDFs into structured_database/pdf_text/."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz

from medbots.corpus_io import load_manifest, resolve_corpus, write_manifest


def _safe_txt_name(bot_root: Path, pdf_path: Path) -> str:
    try:
        rel = pdf_path.relative_to(bot_root).as_posix()
    except ValueError:
        rel = pdf_path.name
    s = re.sub(r"[^\w\-./]+", "_", rel)
    s = s.replace("/", "__")
    base = (s[:200] + ".txt") if len(s) > 200 else s + ".txt"
    return base


def _extract_one(pdf_path: Path) -> tuple[str, int]:
    text_parts: list[str] = []
    pages = 0
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        t = page.get_text("text") or ""
        if t.strip():
            text_parts.append(f"--- page {i + 1} ---\n{t}")
            pages += 1
    doc.close()
    full = "\n\n".join(text_parts).strip()
    if not full:
        full = "[NO_TEXT_LAYER: scanned PDF — OCR not included in this tool]"
    return full, pages


def run(bot_root: Path, corpus: Path | None = None) -> dict[str, Any]:
    root = bot_root.resolve()
    corp = resolve_corpus(corpus) if corpus else resolve_corpus(root / "structured_database")
    out_dir = corp / "pdf_text"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(corp)
    pdfs: list[dict[str, Any]] = list(manifest.get("pdfs") or [])
    updated: list[dict[str, Any]] = []
    ok = 0
    skipped = 0
    errors: list[str] = []

    for entry in pdfs:
        rel = str(entry.get("source_pdf") or "")
        pdf = root / rel if rel else Path()
        if not rel or not pdf.is_file():
            errors.append(f"missing PDF: {rel}")
            updated.append(entry)
            skipped += 1
            continue

        out_name = _safe_txt_name(root, pdf)
        out_path = out_dir / out_name
        try:
            full, pages = _extract_one(pdf)
            out_path.write_text(full, encoding="utf-8")
            new_entry = dict(entry)
            new_entry["extracted_txt"] = f"pdf_text/{out_name}"
            new_entry["chars"] = len(full)
            new_entry["pages_hint"] = pages
            updated.append(new_entry)
            ok += 1
            print(f"OK {rel} -> pdf_text/{out_name} ({new_entry['chars']} chars)", file=sys.stderr)
        except Exception as exc:
            errors.append(f"{rel}: {exc}")
            updated.append(entry)
            skipped += 1

    manifest["pdfs"] = updated
    meta = dict(manifest.get("meta") or {})
    meta["pdf_count"] = len(updated)
    meta["pdf_text_extracted"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["meta"] = meta
    write_manifest(corp, manifest)

    return {"extracted": ok, "skipped": skipped, "errors": errors}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Extract PDF text layers into pdf_text/")
    ap.add_argument("--bot-root", type=Path, default=Path.cwd(), help="Instance root (sources/ + structured_database/)")
    ap.add_argument("--corpus", type=Path, default=None, help="structured_database path override")
    args = ap.parse_args()
    stats = run(args.bot_root, args.corpus)
    if stats["errors"]:
        for err in stats["errors"]:
            print(f"WARN: {err}", file=sys.stderr)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 1 if stats["errors"] and stats["extracted"] == 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
