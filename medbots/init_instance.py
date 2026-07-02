#!/usr/bin/env python3
"""Scaffold a new private health-data instance directory."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

from medbots.corpus_io import empty_manifest, write_manifest


def init(path: Path, *, force: bool = False) -> None:
    root = path.expanduser().resolve()
    if root.exists() and any(root.iterdir()) and not force:
        print(f"ERROR: {root} is not empty (use --force)", file=sys.stderr)
        raise SystemExit(1)

    dirs = [
        root / "sources" / "emias",
        root / "sources" / "medsi",
        root / "sources" / "gemotest",
        root / "structured_database" / "pdf_text",
        root / "structured_database" / "doc_text",
        root / "structured_database" / "labs",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)

    corpus = root / "structured_database"
    write_manifest(corpus, empty_manifest())

    profile = corpus / "PATIENT_PROFILE.json"
    if not profile.exists() or force:
        profile.write_text(
            json.dumps(
                {"dob": "YYYY-MM-DD", "full_name_ru": "Your Name"},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    labs = corpus / "LABS_NORMALIZED.json"
    if not labs.exists() or force:
        labs.write_text(json.dumps({"rows": []}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    loinc = corpus / "labs" / "LOINC_MAP.tsv"
    if not loinc.exists() or force:
        loinc.write_text("canonical_key\tloinc_code\tname_en\n", encoding="utf-8")

    cfg_dst = root / "bot_config.json"
    candidates = [
        Path(__file__).resolve().parent / "bot_config.example.json",
        Path(__file__).resolve().parent.parent / "bot_config.example.json",
    ]
    template = next((p for p in candidates if p.is_file()), None)
    if template is not None and (not cfg_dst.exists() or force):
        shutil.copy(template, cfg_dst)

    print(f"Instance ready: {root}")
    print("Next:")
    print(f"  1. Copy PDFs into {root}/sources/{{emias,medsi,gemotest}}/")
    print(f"  2. Edit {profile.name} (your DOB)")
    print(f"  3. medbots scan --bot-root {root}")
    print(f"  4. medbots extract-text --bot-root {root}")
    print(f"  5. medbots structure --bot-root {root}")
    print(f"  6. medbots pipeline --bot-root {root}")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Create instance directory layout")
    ap.add_argument("path", type=Path, help="Directory for your private instance")
    ap.add_argument("--force", action="store_true", help="Overwrite scaffold files")
    args = ap.parse_args()
    init(args.path, force=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
