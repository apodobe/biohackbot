"""Tests for dedup_labs()."""
from __future__ import annotations

import json
from pathlib import Path

from medbots.dedup_labs import dedup_labs


def _write_labs(corpus: Path, rows: list[dict]) -> None:
    path = corpus / "LABS_NORMALIZED.json"
    path.write_text(json.dumps({"rows": rows}, ensure_ascii=False), encoding="utf-8")


def _read_labs(corpus: Path) -> list[dict]:
    data = json.loads((corpus / "LABS_NORMALIZED.json").read_text(encoding="utf-8"))
    return data["rows"]


def _write_manifest(corpus: Path, pdfs: list[dict]) -> None:
    manifest = {
        "version": 1,
        "pdfs": pdfs,
        "images": [],
        "meta": {},
    }
    (corpus / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_dedup_prefers_medsi_tier(tmp_corpus: Path) -> None:
    rows = [
        {
            "canonical_key": "glucose",
            "specimen_date": "2024-01-10",
            "source_path": "sources/gemotest/report.pdf",
            "value": "5.0",
            "unit": "mmol/L",
        },
        {
            "canonical_key": "glucose",
            "specimen_date": "2024-01-10",
            "source_path": "sources/medsi/report.pdf",
            "value": "5.1",
            "unit": "mmol/L",
            "ref_low": 3.9,
            "ref_high": 6.1,
        },
    ]
    _write_labs(tmp_corpus, rows)

    stats = dedup_labs(tmp_corpus, apply=True)

    assert stats["rows_before"] == 2
    assert stats["rows_after"] == 1
    assert stats["removed"] == 1
    assert stats["dup_groups"] == 1

    kept = _read_labs(tmp_corpus)
    assert len(kept) == 1
    assert "medsi" in kept[0]["source_path"]


def test_manifest_index_uses_pdfs_key(tmp_corpus: Path) -> None:
    from medbots.corpus_io import manifest_vendor_index

    _write_manifest(
        tmp_corpus,
        [
            {
                "source_pdf": "sources/medsi/2024-01-10__blood__abc123.pdf",
                "doc_text": "doc_text/2024-01-10__blood.md",
                "extracted_txt": "pdf_text/2024-01-10__blood__abc123.txt",
            }
        ],
    )
    index = manifest_vendor_index(tmp_corpus)
    assert index["2024-01-10__blood__abc123.txt"] == "medsi"

    rows = [
        {
            "canonical_key": "hemoglobin",
            "specimen_date": "2024-01-10",
            "source_path": "pdf_text/2024-01-10__blood__abc123.txt",
            "value": "140",
        },
        {
            "canonical_key": "hemoglobin",
            "specimen_date": "2024-01-10",
            "source_path": "sources/gemotest/other.pdf",
            "value": "138",
        },
    ]
    _write_labs(tmp_corpus, rows)

    stats = dedup_labs(tmp_corpus, apply=True)

    assert stats["removed"] == 1
    kept = _read_labs(tmp_corpus)
    assert len(kept) == 1
    assert kept[0]["source_path"] == "pdf_text/2024-01-10__blood__abc123.txt"


def test_dedup_dry_run_does_not_write(tmp_corpus: Path) -> None:
    original_rows = [
        {
            "canonical_key": "alt",
            "specimen_date": "2024-02-01",
            "source_path": "sources/medsi/a.pdf",
            "value": "20",
        },
        {
            "canonical_key": "alt",
            "specimen_date": "2024-02-01",
            "source_path": "sources/gemotest/b.pdf",
            "value": "22",
        },
    ]
    _write_labs(tmp_corpus, original_rows)
    original_text = (tmp_corpus / "LABS_NORMALIZED.json").read_text(encoding="utf-8")

    stats = dedup_labs(tmp_corpus, apply=False)

    assert stats["rows_before"] == 2
    assert stats["rows_after"] == 1
    assert stats["removed"] == 1
    assert (tmp_corpus / "LABS_NORMALIZED.json").read_text(encoding="utf-8") == original_text
    assert len(_read_labs(tmp_corpus)) == 2
