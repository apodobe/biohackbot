#!/usr/bin/env python3
"""CLI entry points for medbots-core."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from medbots.config import find_bot_root, load_config
from medbots.corpus_io import load_patient_dob, resolve_corpus
from medbots.pipeline.run import run_pipeline


def _cmd_pipeline(args: argparse.Namespace) -> int:
    root = Path(args.bot_root).resolve() if args.bot_root else find_bot_root()
    corpus = resolve_corpus(args.corpus) if args.corpus else None
    try:
        run_pipeline(bot_root=root, corpus=corpus)
    except subprocess.CalledProcessError as exc:
        return exc.returncode or 1
    return 0


def _cmd_patient_dob(args: argparse.Namespace) -> int:
    corpus = resolve_corpus(args.corpus)
    print(load_patient_dob(corpus))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="medbots", description="Medical bots corpus tools")
    sub = parser.add_subparsers(dest="command", required=True)

    p_pipe = sub.add_parser("pipeline", help="Run phase-2 corpus enrichment pipeline")
    p_pipe.add_argument("--bot-root", type=Path, help="Bot repo root (bot_config.json)")
    p_pipe.add_argument("--corpus", type=Path, help="structured_database path override")
    p_pipe.set_defaults(func=_cmd_pipeline)

    p_dob = sub.add_parser("patient-dob", help="Print patient DOB from PATIENT_PROFILE.json")
    p_dob.add_argument("--corpus", type=Path, help="structured_database path")
    p_dob.set_defaults(func=_cmd_patient_dob)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
