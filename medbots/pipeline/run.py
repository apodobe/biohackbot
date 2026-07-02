#!/usr/bin/env python3
"""Run post-ingest corpus pipeline with bot_config feature flags."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from medbots.config import BotConfig, corpus_from_config, feature_enabled, load_config
from medbots.corpus_io import resolve_corpus


def _run_module(module: str, corpus: Path, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, "-m", module, "--corpus", str(corpus)]
    if extra:
        cmd.extend(extra)
    print(f"==> {module}")
    subprocess.run(cmd, check=True)


def _run_script(script: Path, corpus: Path, extra: list[str] | None = None) -> None:
    cmd = [sys.executable, str(script), "--corpus", str(corpus)]
    if extra:
        cmd.extend(extra)
    print(f"==> {script.name}")
    subprocess.run(cmd, check=True)


def _corpus_has(corpus: Path, rel: str) -> bool:
    return (corpus / rel).exists()


def run_pipeline(
    bot_root: Path | None = None,
    corpus: Path | str | None = None,
    config: BotConfig | None = None,
) -> None:
    cfg = config or load_config(bot_root)
    root = cfg.bot_root if bot_root is None else bot_root.resolve()
    corp = resolve_corpus(corpus) if corpus is not None else corpus_from_config(cfg)

    os.environ["MEDBOTS_BOT_ROOT"] = str(root)
    os.environ["MEDBOTS_CORPUS_PATH"] = str(corp)
    os.environ[cfg.corpus_path_env] = str(corp)

    scripts = root / "scripts"
    nutrition = feature_enabled("nutrition_import", cfg)

    if feature_enabled("legacy_flat_pdf_paths", cfg):
        bridge = scripts / "bridge_legacy_flat_pdfs.py"
        if bridge.is_file():
            _run_script(bridge, corp, ["--apply"])

    _run_module("medbots.merge_labs_corpus", corp)
    _run_module("medbots.pipeline.apply_loinc_map", corp)
    _run_module("medbots.dedup_labs", corp)

    if feature_enabled("goals_reminders", cfg):
        _run_module("medbots.pipeline.extract_goals_from_doc_text", corp)

    if nutrition or _corpus_has(corp, "nutrition/NUTRITION.json"):
        _run_module("medbots.pipeline.extract_supplements_from_corpus", corp)
        _run_module("medbots.pipeline.extract_protocols_from_corpus", corp)

    _run_module("medbots.pipeline.generate_discrepancies", corp)
    _run_module("medbots.pipeline.generate_lhm", corp)

    if feature_enabled("weekly_pending", cfg):
        weekly = scripts / "reconcile_weekly_pending.py"
        if weekly.is_file():
            _run_script(weekly, corp, ["--apply"])
        else:
            print("==> reconcile_weekly_pending (skipped: script not found)")

    if feature_enabled("goals_reminders", cfg):
        _run_module("medbots.pipeline.reconcile_goals", corp, ["--apply"])

    _run_module("medbots.pipeline.write_composer_review_index", corp)
    _run_module("medbots.pipeline.validate_corpus", corp)

    index_args: list[str] = []
    if cfg.bot_id:
        index_args = ["--bot", cfg.bot_id]
    cmd = [sys.executable, "-m", "medbots.pipeline.write_corpus_index", *index_args]
    print("==> write_corpus_index")
    subprocess.run(cmd, check=True, cwd=str(root), env={**os.environ, "MEDBOTS_CORPUS_PATH": str(corp)})

    print("Pipeline OK.")
