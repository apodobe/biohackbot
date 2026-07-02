"""Grok ingest dedupe and API-key guards (no live API calls)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("fitz")

import fitz  # noqa: E402

from medbots.grok_ingest import ingest_image_bytes, ingest_pdf_bytes, sha256_bytes


def _minimal_pdf_bytes() -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Лейкоциты 6.5 10^9/L (реф. 4-9). Дата: 10.04.2026.")
    data = doc.tobytes()
    doc.close()
    return data


_MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def ingest_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "structured_database"
    root.mkdir()
    (root / "pdf_text").mkdir()
    manifest = {
        "version": 1,
        "pdfs": [],
        "images": [],
        "meta": {"built": "2000-01-01", "pdf_count": 0},
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "LABS_NORMALIZED.json").write_text(json.dumps({"rows": []}), encoding="utf-8")
    return root


def test_ingest_pdf_requires_api_key(ingest_corpus: Path) -> None:
    result = ingest_pdf_bytes(
        ingest_corpus,
        _minimal_pdf_bytes(),
        original_filename="test.pdf",
        api_key="",
    )
    assert result.status == "error"
    assert "XAI_API_KEY" in result.detail


def test_ingest_pdf_duplicate_by_manifest_hash(ingest_corpus: Path) -> None:
    pdf = _minimal_pdf_bytes()
    digest = sha256_bytes(pdf)
    manifest = json.loads((ingest_corpus / "manifest.json").read_text(encoding="utf-8"))
    manifest["pdfs"].append({"source_pdf": "fake.pdf", "sha256": digest})
    (ingest_corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = ingest_pdf_bytes(
        ingest_corpus,
        pdf,
        original_filename="dup.pdf",
        api_key="dummy",
    )
    assert result.status == "duplicate"


def test_ingest_image_duplicate_by_manifest_hash(ingest_corpus: Path) -> None:
    digest = sha256_bytes(_MINIMAL_PNG)
    manifest = json.loads((ingest_corpus / "manifest.json").read_text(encoding="utf-8"))
    manifest["images"].append({"source": "fake.png", "sha256": digest})
    (ingest_corpus / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    result = ingest_image_bytes(
        ingest_corpus,
        _MINIMAL_PNG,
        original_filename="x.png",
        api_key="dummy",
    )
    assert result.status == "duplicate"
