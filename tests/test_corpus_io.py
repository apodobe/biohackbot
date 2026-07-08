from __future__ import annotations

import json
from pathlib import Path

import pytest

from medbots.corpus_io import (
    empty_manifest,
    load_labs,
    load_manifest,
    load_patient_dob,
    manifest_vendor_index,
    resolve_owner_dob,
    write_labs,
    write_manifest,
)


def test_empty_manifest_shape() -> None:
    m = empty_manifest()
    assert m["version"] == 1
    assert m["pdfs"] == []


def test_load_write_manifest_roundtrip(tmp_corpus: Path) -> None:
    data = empty_manifest()
    data["pdfs"] = [{"source_pdf": "sources/medsi/x.pdf", "doc_type": "lab"}]
    write_manifest(tmp_corpus, data)
    loaded = load_manifest(tmp_corpus)
    assert len(loaded["pdfs"]) == 1


def test_load_manifest_missing_returns_empty(tmp_path: Path) -> None:
    corpus = tmp_path / "empty"
    corpus.mkdir()
    assert load_manifest(corpus)["pdfs"] == []


def test_load_patient_dob_from_profile(tmp_corpus: Path) -> None:
    (tmp_corpus / "PATIENT_PROFILE.json").write_text(
        json.dumps({"dob": "1985-06-15"}), encoding="utf-8"
    )
    assert load_patient_dob(tmp_corpus) == "1985-06-15"


def test_load_patient_dob_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    corpus = tmp_path / "c"
    corpus.mkdir()
    monkeypatch.delenv("MEDBOTS_OWNER_DOB", raising=False)
    assert load_patient_dob(corpus) == ""


def test_resolve_owner_dob_accepts_repo_root(tmp_path: Path) -> None:
    corpus = tmp_path / "structured_database"
    corpus.mkdir()
    (corpus / "PATIENT_PROFILE.json").write_text(
        json.dumps({"dob": "1985-06-15"}), encoding="utf-8"
    )
    repo = tmp_path
    assert resolve_owner_dob(repo) == "1985-06-15"


def test_manifest_vendor_index_uses_pdfs_key(tmp_corpus: Path) -> None:
    write_manifest(
        tmp_corpus,
        {
            "version": 1,
            "pdfs": [
                {
                    "source_pdf": "sources/medsi/123__lab.pdf",
                    "doc_text": "doc_text/2026-01-01_lab.md",
                    "extracted_txt": "pdf_text/sources__medsi__lab.pdf.txt",
                }
            ],
            "images": [],
            "meta": {},
        },
    )
    index = manifest_vendor_index(tmp_corpus)
    assert index["2026-01-01_lab.md"] == "medsi"
    assert index["sources__medsi__lab.pdf.txt"] == "medsi"


def test_labs_roundtrip(tmp_corpus: Path) -> None:
    rows = [{"canonical_key": "glucose", "value": "5.0"}]
    write_labs(tmp_corpus, {"rows": rows})
    assert load_labs(tmp_corpus)["rows"] == rows
