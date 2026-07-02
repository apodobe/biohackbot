#!/usr/bin/env python3
"""Re-extract lab rows from EMIAS/Gemotest pdf_text into LABS_NORMALIZED.json."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from medbots.corpus_io import default_corpus_root, load_manifest
from medbots.corpus_writers import _append_lab_rows
from medbots.local_structure_pdfs import _entry_title, _parse_entry, _pdf_text_path


def _is_lab_source(entry: dict[str, Any]) -> bool:
    source_system = (entry.get("source_system") or "").lower()
    source_pdf = entry.get("source_pdf") or ""
    doc_type = entry.get("doc_type") or ""
    if source_system == "legacy_flat":
        return doc_type == "lab"
    if doc_type == "lab" and (
        source_system == "medsi" or "sources/medsi" in source_pdf
    ):
        return True
    if source_system in ("emias", "gemotest"):
        return True
    if not source_pdf.startswith("sources/") and doc_type == "lab":
        return True
    return "sources/emias" in source_pdf or "sources/gemotest" in source_pdf


def _doc_text_rel(entry: dict[str, Any]) -> str:
    doc_text = entry.get("doc_text")
    if isinstance(doc_text, str) and doc_text:
        return doc_text
    title = _entry_title(entry)
    doc_date = entry.get("doc_date") or "unknown"
    safe = title.replace("/", "-").replace("\\", "-")[:80]
    return f"doc_text/{doc_date}_{safe}.md"


def _remove_rows_for_sources(corpus: Path, source_paths: set[str]) -> int:
    labs_path = corpus / "LABS_NORMALIZED.json"
    if not labs_path.exists():
        return 0
    labs = json.loads(labs_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = labs.get("rows") or []
    kept = [r for r in rows if (r.get("source_path") or "") not in source_paths]
    removed = len(rows) - len(kept)
    if removed:
        labs["rows"] = kept
        labs_path.write_text(json.dumps(labs, ensure_ascii=False, indent=2), encoding="utf-8")
    return removed


def run(corpus: Path, *, dry_run: bool = False, replace: bool = True) -> dict[str, Any]:
    manifest = load_manifest(corpus)
    pdfs: list[dict[str, Any]] = list(manifest.get("pdfs") or [])

    targets: list[tuple[dict[str, Any], str, str]] = []
    errors: list[str] = []
    source_paths: set[str] = set()

    for entry in pdfs:
        if not _is_lab_source(entry):
            continue
        source_pdf = entry.get("source_pdf") or ""
        txt_path = _pdf_text_path(corpus, entry)
        if not txt_path.is_file():
            errors.append(f"missing pdf_text: {source_pdf}")
            continue
        text = txt_path.read_text(encoding="utf-8").strip()
        if not text or text.startswith("[NO_TEXT_LAYER"):
            errors.append(f"empty text: {source_pdf}")
            continue
        try:
            extracted = _parse_entry(text, entry)
        except Exception as exc:
            errors.append(f"parse {source_pdf}: {exc}")
            continue
        lab_rows = extracted.get("lab_rows") or []
        if not lab_rows:
            continue
        doc_rel = _doc_text_rel(entry)
        source_paths.add(doc_rel)
        targets.append((entry, doc_rel, source_pdf))

    before_count = 0
    labs_path = corpus / "LABS_NORMALIZED.json"
    if labs_path.exists():
        before_count = len(json.loads(labs_path.read_text(encoding="utf-8")).get("rows") or [])

    removed = 0
    if replace and not dry_run and source_paths:
        removed = _remove_rows_for_sources(corpus, source_paths)

    labs_added_total = 0
    per_doc: list[dict[str, Any]] = []
    if not dry_run:
        for entry, doc_rel, source_pdf in targets:
            text = _pdf_text_path(corpus, entry).read_text(encoding="utf-8").strip()
            extracted = _parse_entry(text, entry)
            added = _append_lab_rows(corpus, extracted.get("lab_rows") or [], doc_rel)
            labs_added_total += added
            per_doc.append(
                {
                    "source_pdf": source_pdf,
                    "doc_text": doc_rel,
                    "lab_rows_parsed": len(extracted.get("lab_rows") or []),
                    "lab_rows_added": added,
                }
            )
    else:
        for entry, doc_rel, source_pdf in targets:
            text = _pdf_text_path(corpus, entry).read_text(encoding="utf-8").strip()
            extracted = _parse_entry(text, entry)
            n = len(extracted.get("lab_rows") or [])
            labs_added_total += n
            per_doc.append(
                {
                    "source_pdf": source_pdf,
                    "doc_text": doc_rel,
                    "lab_rows_parsed": n,
                    "lab_rows_added": n,
                }
            )

    after_count = before_count
    if not dry_run and labs_path.exists():
        after_count = len(json.loads(labs_path.read_text(encoding="utf-8")).get("rows") or [])

    return {
        "before_rows": before_count,
        "after_rows": after_count if not dry_run else before_count + labs_added_total - removed,
        "rows_removed": removed,
        "lab_rows_added": labs_added_total,
        "documents": len(per_doc),
        "per_document": per_doc,
        "errors": errors,
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Merge Gemotest/EMIAS labs into LABS_NORMALIZED")
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument(
        "--no-replace",
        action="store_true",
        help="Do not remove existing rows for the same doc_text source_path before append",
    )
    args = ap.parse_args()
    if args.corpus is None:
        args.corpus = default_corpus_root()
    corpus = args.corpus.expanduser().resolve()
    if not corpus.is_dir():
        print(f"ERROR: corpus not found: {corpus}", file=sys.stderr)
        return 1

    stats = run(corpus, dry_run=args.dry_run, replace=not args.no_replace)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if stats.get("errors"):
        for err in stats["errors"]:
            print(f"WARN: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
