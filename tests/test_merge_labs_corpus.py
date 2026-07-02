"""Tests for merge_labs_corpus.run."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from medbots.merge_labs_corpus import run


def _write_lab_manifest(
    corpus: Path,
    *,
    source_system: str,
    source_pdf: str,
    txt_filename: str,
    text: str,
) -> None:
    pdf_text_dir = corpus / "pdf_text"
    pdf_text_dir.mkdir(exist_ok=True)
    txt_rel = f"pdf_text/{txt_filename}"
    (corpus / txt_rel).write_text(text, encoding="utf-8")

    manifest = {
        "version": 1,
        "pdfs": [
            {
                "source_pdf": source_pdf,
                "extracted_txt": txt_rel,
                "source_system": source_system,
                "doc_type": "lab",
                "gemotest_title": "Биохимия",
                "emias_title": "Биохимический анализ крови",
                "created_at": "2021-02-14T12:00:00Z",
            }
        ],
        "images": [],
        "meta": {"pdf_count": 1},
    }
    (corpus / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_merge_gemotest_adds_lab_rows(
    tmp_corpus: Path,
    load_pdf_text_fixture,
) -> None:
    txt_name = (
        "sources__gemotest__2021-02-14__gemotest_69371781__"
        "Биохимия_19_показателей__d6c4ee6e.pdf.txt"
    )
    text = load_pdf_text_fixture(txt_name)
    source_pdf = (
        "sources/gemotest/2021-02-14/gemotest_69371781__"
        "Биохимия_19_показателей__d6c4ee6e.pdf"
    )
    _write_lab_manifest(
        tmp_corpus,
        source_system="gemotest",
        source_pdf=source_pdf,
        txt_filename=txt_name,
        text=text,
    )

    stats = run(tmp_corpus, dry_run=False)

    assert stats["errors"] == []
    assert stats["lab_rows_added"] > 0
    assert stats["documents"] == 1

    labs = json.loads((tmp_corpus / "LABS_NORMALIZED.json").read_text(encoding="utf-8"))
    assert len(labs["rows"]) > 0
    assert stats["after_rows"] == len(labs["rows"])


def test_merge_emias_adds_lab_rows(
    tmp_corpus: Path,
    load_pdf_text_fixture,
) -> None:
    txt_name = (
        "sources__emias__2021-01-18__Определение_антител_IgM_и_IgG_к_Coronavirus_"
        "SARS-CoV-2__079f862f.pdf.txt"
    )
    text = load_pdf_text_fixture(txt_name)
    source_pdf = (
        "sources/emias/2021-01-18/Определение_антител_IgM_и_IgG_к_Coronavirus_"
        "SARS-CoV-2__079f862f.pdf"
    )
    _write_lab_manifest(
        tmp_corpus,
        source_system="emias",
        source_pdf=source_pdf,
        txt_filename=txt_name,
        text=text,
    )

    stats = run(tmp_corpus, dry_run=False)

    assert stats["errors"] == []
    assert stats["lab_rows_added"] > 0

    labs = json.loads((tmp_corpus / "LABS_NORMALIZED.json").read_text(encoding="utf-8"))
    assert len(labs["rows"]) > 0


def test_merge_dry_run_does_not_write_rows(
    tmp_corpus: Path,
    load_pdf_text_fixture,
) -> None:
    txt_name = (
        "sources__gemotest__2021-02-14__gemotest_69371781__"
        "Биохимия_19_показателей__d6c4ee6e.pdf.txt"
    )
    text = load_pdf_text_fixture(txt_name)
    source_pdf = (
        "sources/gemotest/2021-02-14/gemotest_69371781__"
        "Биохимия_19_показателей__d6c4ee6e.pdf"
    )
    _write_lab_manifest(
        tmp_corpus,
        source_system="gemotest",
        source_pdf=source_pdf,
        txt_filename=txt_name,
        text=text,
    )

    stats = run(tmp_corpus, dry_run=True)

    assert stats["lab_rows_added"] > 0
    labs = json.loads((tmp_corpus / "LABS_NORMALIZED.json").read_text(encoding="utf-8"))
    assert labs["rows"] == []


def test_merge_legacy_flat_lab_rows(
    tmp_corpus: Path,
    load_pdf_text_fixture,
) -> None:
    """idamedbot flat manifest entries (source_system=legacy_flat)."""
    txt_name = (
        "sources__emias__2021-01-18__Определение_антител_IgM_и_IgG_к_Coronavirus_"
        "SARS-CoV-2__079f862f.pdf.txt"
    )
    text = load_pdf_text_fixture(txt_name)
    txt_rel = f"pdf_text/{txt_name}"
    (tmp_corpus / "pdf_text").mkdir(exist_ok=True)
    (tmp_corpus / txt_rel).write_text(text, encoding="utf-8")
    manifest = {
        "version": 1,
        "pdfs": [
            {
                "source_pdf": "2021-01-18_covid_antibodies.pdf",
                "extracted_txt": txt_rel,
                "source_system": "legacy_flat",
                "doc_type": "lab",
                "structured_locally_at": "2024-01-01T00:00:00Z",
            }
        ],
        "images": [],
        "meta": {"pdf_count": 1},
    }
    (tmp_corpus / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )

    stats = run(tmp_corpus, dry_run=False)

    assert stats["errors"] == []
    assert stats["documents"] == 1
    assert stats["lab_rows_added"] > 0
