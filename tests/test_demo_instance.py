"""E2E: demo instance structure + pipeline without PDF binaries."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

PKG_ROOT = Path(__file__).resolve().parent.parent
DEMO_SRC = PKG_ROOT / "examples" / "demo-instance"


@pytest.fixture
def demo_copy(tmp_path: Path) -> Path:
    dst = tmp_path / "demo"
    shutil.copytree(DEMO_SRC, dst)
    return dst


def test_demo_instance_structure_and_pipeline(demo_copy: Path) -> None:
    root = demo_copy
    corpus = root / "structured_database"

    from medbots.local_structure_pdfs import run as run_structure
    from medbots.pipeline.run import run_pipeline

    stats = run_structure(corpus, force=True)
    assert stats["structured"] == 3
    assert stats["errors"] == []

    doc_text_dir = corpus / "doc_text"
    assert doc_text_dir.is_dir()
    assert len(list(doc_text_dir.glob("*.md"))) == 3

    run_pipeline(bot_root=root, corpus=corpus)

    labs = json.loads((corpus / "LABS_NORMALIZED.json").read_text(encoding="utf-8"))
    assert len(labs.get("rows") or []) >= 40

    assert (corpus / "CORPUS_INDEX.json").is_file()
    assert (corpus / "LIVING_HEALTH_SUMMARY.md").is_file()
