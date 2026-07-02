#!/usr/bin/env python3
"""Scan sources/{emias,medsi,gemotest}/ and register new PDFs in manifest.json."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from medbots.corpus_io import empty_manifest, load_manifest, resolve_corpus, write_manifest

_VENDORS = ("emias", "medsi", "gemotest")


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _infer_title(stem: str) -> str:
    s = re.sub(r"__\w{8}$", "", stem)
    s = s.replace("_", " ").strip()
    return s or stem


def scan(
    bot_root: Path,
    corpus: Path | None = None,
    vendors: set[str] | None = None,
) -> dict[str, Any]:
    root = bot_root.resolve()
    corp = resolve_corpus(corpus) if corpus else resolve_corpus(root / "structured_database")
    corp.mkdir(parents=True, exist_ok=True)

    manifest = load_manifest(corp) if (corp / "manifest.json").exists() else empty_manifest()
    existing_paths = {str(e.get("source_pdf")) for e in manifest.get("pdfs") or []}
    existing_hashes = {str(e.get("sha256")) for e in manifest.get("pdfs") or [] if e.get("sha256")}

    added = 0
    pdfs: list[dict[str, Any]] = list(manifest.get("pdfs") or [])
    vendor_filter = {v.lower() for v in vendors} if vendors else set(_VENDORS)

    for vendor in _VENDORS:
        if vendor not in vendor_filter:
            continue
        src_dir = root / "sources" / vendor
        if not src_dir.is_dir():
            continue
        for pdf in sorted(src_dir.rglob("*.pdf")):
            rel = pdf.relative_to(root).as_posix()
            digest = _sha256(pdf)
            if rel in existing_paths or digest in existing_hashes:
                continue
            title = _infer_title(pdf.stem)
            pdfs.append(
                {
                    "source_pdf": rel,
                    "source_system": vendor,
                    "doc_type": "lab" if vendor != "emias" else "other",
                    "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "sha256": digest,
                    "user_drop_title": title,
                    **({f"{vendor}_title": title} if vendor == "gemotest" else {}),
                    **({"emias_title": title} if vendor == "emias" else {}),
                }
            )
            existing_paths.add(rel)
            existing_hashes.add(digest)
            added += 1
            print(f"ADD {rel}", file=sys.stderr)

    manifest["pdfs"] = pdfs
    meta = dict(manifest.get("meta") or {})
    meta["pdf_count"] = len(pdfs)
    meta["scanned_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest["meta"] = meta
    write_manifest(corp, manifest)

    return {"added": added, "total": len(pdfs)}


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Register PDFs from sources/ into manifest.json")
    ap.add_argument("--bot-root", type=Path, default=Path.cwd())
    ap.add_argument("--corpus", type=Path, default=None)
    ap.add_argument("--source", action="append", default=[], help="Vendor filter: emias, medsi, gemotest")
    args = ap.parse_args()
    vendors = {s.strip().lower() for s in args.source if s.strip()} or None
    stats = scan(args.bot_root, args.corpus, vendors)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
