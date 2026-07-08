"""Tests for push/CI secret and PHI guards."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from check_safe_to_push import (  # noqa: E402
    check,
    check_tracked_tree,
)


def test_check_blocks_real_telegram_token() -> None:
    errors = check(
        public=True,
        paths=["deploy/openclaw.env.example"],
        diff_text="+TELEGRAM_BOT_TOKEN=123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
    )
    assert any("TELEGRAM_BOT_TOKEN" in e for e in errors)


def test_check_allows_empty_telegram_placeholder() -> None:
    errors = check(
        public=True,
        paths=["deploy/openclaw.env.example"],
        diff_text="+TELEGRAM_BOT_TOKEN=\n",
    )
    assert errors == []


def test_check_blocks_leaked_oms_policy() -> None:
    errors = check(
        public=True,
        paths=["tests/fixtures/pdf_text/foo.txt"],
        diff_text="+Полис ОМС: 7752900844000725",
    )
    assert errors


def test_check_blocks_patient_corpus_path() -> None:
    errors = check(
        public=True,
        paths=["structured_database/LABS_NORMALIZED.json"],
        diff_text="{}",
    )
    assert any("blocked path" in e for e in errors)


def test_check_blocks_env_file() -> None:
    errors = check(
        public=True,
        paths=["deploy/.env"],
        diff_text="SECRET=1",
    )
    assert any("blocked env file" in e for e in errors)


def test_scan_all_passes_on_clean_tree() -> None:
    errors = check_tracked_tree(public=True)
    assert errors == []


def test_pre_push_script_exits_zero_on_current_branch() -> None:
    """Outgoing range vs main should be clean after PHI redaction."""
    out = subprocess.check_output(
        ["git", "merge-base", "HEAD", "main"],
        cwd=ROOT,
        text=True,
    ).strip()
    proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_safe_to_push.py"), "--public", "--range", f"{out}..HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
