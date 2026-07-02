"""Shared pytest fixtures for medbots-core."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent
FIXTURES = PKG_ROOT / "tests" / "fixtures" / "pdf_text"

for p in (str(PKG_ROOT),):
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return PKG_ROOT


def load_pdf_text(name: str) -> str:
    """Load vendor PDF text fixture (synthetic, redacted)."""
    path = FIXTURES / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return path.read_text(encoding="utf-8")


@pytest.fixture
def load_pdf_text_fixture():
    return load_pdf_text


@pytest.fixture
def tmp_corpus(tmp_path: Path) -> Path:
    """Empty mini-corpus with manifest.json skeleton."""
    corpus = tmp_path / "structured_database"
    corpus.mkdir()
    (corpus / "manifest.json").write_text(
        json.dumps({"version": 1, "pdfs": [], "images": [], "meta": {}}, ensure_ascii=False),
        encoding="utf-8",
    )
    (corpus / "LABS_NORMALIZED.json").write_text(
        json.dumps({"rows": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return corpus
