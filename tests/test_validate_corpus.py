"""Tests for validate_corpus main checks."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from medbots.pipeline.validate_corpus import main as validate_main


@pytest.fixture
def corpus_env(monkeypatch: pytest.MonkeyPatch, tmp_corpus: Path) -> Path:
    monkeypatch.setenv("MEDBOTS_CORPUS_PATH", str(tmp_corpus))
    monkeypatch.delenv("BIOHACKING_CORPUS_PATH", raising=False)
    monkeypatch.delenv("IRINA_CORPUS_PATH", raising=False)
    monkeypatch.delenv("MEDICAL_CORPUS_PATH", raising=False)
    return tmp_corpus


def test_empty_corpus_fails_key_checks(corpus_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = validate_main()
    captured = capsys.readouterr().out

    assert exit_code == 1
    assert "FAIL: corpus validation failed" in captured
    assert "LABS_NORMALIZED.json has no rows" in captured
    assert "GOALS_REMINDERS.json missing" in captured
    assert "DISCREPANCIES.json missing" in captured
    assert "manifest.meta.pdf_count missing" in captured


def test_minimal_valid_corpus_passes(corpus_env: Path, capsys: pytest.CaptureFixture[str]) -> None:
    corpus = corpus_env
    pdf_text_dir = corpus / "pdf_text"
    pdf_text_dir.mkdir(exist_ok=True)
    txt_rel = "pdf_text/minimal_lab.txt"
    (corpus / txt_rel).write_text("Гемотest lab sample\nГлюкоза 4.5 ммоль/л", encoding="utf-8")

    manifest = {
        "version": 1,
        "pdfs": [
            {
                "source_pdf": "sources/gemotest/2021-02-14/minimal.pdf",
                "extracted_txt": txt_rel,
                "structured_locally_at": "2024-01-01T00:00:00Z",
                "source_system": "gemotest",
                "doc_type": "lab",
            }
        ],
        "images": [],
        "meta": {"pdf_count": 1},
    }
    (corpus / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )
    (corpus / "LABS_NORMALIZED.json").write_text(
        json.dumps(
            {
                "rows": [
                    {
                        "analyte": "Glucose",
                        "value": "4.5",
                        "loinc": "2345-7",
                        "source_path": "doc_text/2021-02-14_minimal.md",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (corpus / "GOALS_REMINDERS.json").write_text("{}", encoding="utf-8")
    (corpus / "DISCREPANCIES.json").write_text("{}", encoding="utf-8")

    exit_code = validate_main()
    captured = capsys.readouterr().out

    assert exit_code == 0
    assert "OK" in captured
    assert "manifest_meta_pdf_count=1 (matches)" in captured
    assert "ingest_status=all_pdfs_grok_or_structured_locally" in captured
    assert "labs_rows=1" in captured
    assert "GOALS_REMINDERS.json=present" in captured
    assert "DISCREPANCIES.json=present" in captured


def test_missing_corpus_directory(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    missing = tmp_path / "no_such_corpus"
    monkeypatch.setenv("MEDBOTS_CORPUS_PATH", str(missing))
    monkeypatch.delenv("BIOHACKING_CORPUS_PATH", raising=False)
    assert validate_main() == 1
