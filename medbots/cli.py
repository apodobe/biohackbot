#!/usr/bin/env python3
"""CLI entry points for medbots-core."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from medbots.config import find_bot_root
from medbots.corpus_io import load_patient_dob, resolve_corpus
from medbots.extract_pdf_text import run as run_extract
from medbots.init_instance import init as run_init
from medbots.pipeline.run import run_pipeline
from medbots.scan_sources import scan as run_scan


def _cmd_init(args: argparse.Namespace) -> int:
    run_init(args.path, force=args.force)
    return 0


def _cmd_scan(args: argparse.Namespace) -> int:
    root = Path(args.bot_root).resolve() if args.bot_root else find_bot_root()
    vendors = {s.strip().lower() for s in args.source if s.strip()} or None
    stats = run_scan(root, args.corpus, vendors)
    print(f"Registered {stats['added']} new PDF(s), {stats['total']} total in manifest.")
    return 0


def _cmd_extract_text(args: argparse.Namespace) -> int:
    root = Path(args.bot_root).resolve() if args.bot_root else find_bot_root()
    stats = run_extract(root, args.corpus)
    print(f"Extracted {stats['extracted']} PDF(s).")
    return 1 if stats["errors"] and stats["extracted"] == 0 else 0


def _cmd_structure(args: argparse.Namespace) -> int:
    root = Path(args.bot_root).resolve() if args.bot_root else find_bot_root()
    corpus = resolve_corpus(args.corpus) if args.corpus else resolve_corpus(root / "structured_database")
    cmd = [
        sys.executable,
        "-m",
        "medbots.local_structure_pdfs",
        "--corpus",
        str(corpus),
    ]
    if args.force:
        cmd.append("--force")
    for src in args.source:
        cmd.extend(["--source", src])
    if args.dry_run:
        cmd.append("--dry-run")
    return subprocess.call(cmd)


def _cmd_pipeline(args: argparse.Namespace) -> int:
    root = Path(args.bot_root).resolve() if args.bot_root else find_bot_root()
    corpus = resolve_corpus(args.corpus) if args.corpus else None
    try:
        run_pipeline(bot_root=root, corpus=corpus)
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    corpus = resolve_corpus(args.corpus)
    return subprocess.call([sys.executable, "-m", "medbots.pipeline.validate_corpus", "--corpus", str(corpus)])


def _cmd_patient_dob(args: argparse.Namespace) -> int:
    corpus = resolve_corpus(args.corpus)
    print(load_patient_dob(corpus))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="medbots",
        description="Medical corpus tools: scan PDFs, extract text, parse labs, run pipeline",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="Create a new private instance directory")
    p_init.add_argument("path", type=Path, help="Instance directory path")
    p_init.add_argument("--force", action="store_true")
    p_init.set_defaults(func=_cmd_init)

    p_scan = sub.add_parser("scan", help="Register PDFs from sources/ into manifest.json")
    p_scan.add_argument("--bot-root", type=Path, help="Instance root")
    p_scan.add_argument("--corpus", type=Path)
    p_scan.add_argument("--source", action="append", default=[], help="emias, medsi, or gemotest")
    p_scan.set_defaults(func=_cmd_scan)

    p_ext = sub.add_parser("extract-text", help="Extract PDF text into pdf_text/")
    p_ext.add_argument("--bot-root", type=Path)
    p_ext.add_argument("--corpus", type=Path)
    p_ext.set_defaults(func=_cmd_extract_text)

    p_struct = sub.add_parser("structure", help="Parse pdf_text into doc_text and lab rows")
    p_struct.add_argument("--bot-root", type=Path)
    p_struct.add_argument("--corpus", type=Path)
    p_struct.add_argument("--force", action="store_true")
    p_struct.add_argument("--dry-run", action="store_true")
    p_struct.add_argument("--source", action="append", default=[])
    p_struct.set_defaults(func=_cmd_structure)

    p_pipe = sub.add_parser("pipeline", help="Run enrichment: merge labs, LOINC, dedup, index")
    p_pipe.add_argument("--bot-root", type=Path)
    p_pipe.add_argument("--corpus", type=Path)
    p_pipe.set_defaults(func=_cmd_pipeline)

    p_val = sub.add_parser("validate", help="Check corpus integrity")
    p_val.add_argument("--corpus", type=Path)
    p_val.set_defaults(func=_cmd_validate)

    p_dob = sub.add_parser("patient-dob", help="Print DOB from PATIENT_PROFILE.json")
    p_dob.add_argument("--corpus", type=Path)
    p_dob.set_defaults(func=_cmd_patient_dob)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
