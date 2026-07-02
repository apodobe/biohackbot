"""Golden tests for EMIAS PDF parsing."""
from __future__ import annotations

import re
from typing import Any

import pytest

from medbots.local_structure_pdfs import (
    _parse_entry,
    parse_emias_consult_or_imaging,
    parse_emias_lab,
)

from conftest import load_pdf_text

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

LAB_FIXTURE = (
    "sources__emias__2026-06-17__drop_Биохимический_анализ_крови__929313a8.pdf.txt",
    "sources/emias/2026-06-17__drop_Биохимический_анализ_крови__929313a8.pdf",
    "Биохимический анализ крови",
    "2026-06-17",
)

CONSULT_FIXTURE = (
    "sources__emias__2019-12-30__Осмотр_терапевта__746635cf.pdf.txt",
    "sources/emias/2019-12-30__Осмотр_терапевта__746635cf.pdf",
    "Осмотр терапевта",
    "2019-12-30",
)

IMAGING_FIXTURE = (
    "sources__emias__2019-10-10__Результат_флюорографии__1ce3317f.pdf.txt",
    "sources/emias/2019-10-10__Результат_флюорографии__1ce3317f.pdf",
    "Результат флюорографии",
    "2019-10-10",
)

_BIOCHEM_MARKERS: dict[str, float] = {
    "glyukoza_venoznoy_krovi_natoschak": 4.82,
    "s_reaktivnyy_belok": 1.02,
    "mochevina": 4.8,
    "kreatinin": 84.0,
    "obschiy_belok": 71.8,
}


def _assert_lab_rows(rows: list[dict[str, Any]], expected_doc_date: str) -> None:
    assert rows, "lab_rows must be non-empty"
    for row in rows:
        assert row.get("canonical_key"), f"missing canonical_key in row: {row!r}"
        specimen_date = row.get("specimen_date")
        assert specimen_date, f"missing specimen_date in row: {row!r}"
        assert _ISO_DATE.match(specimen_date), f"specimen_date not ISO: {specimen_date!r}"
        assert specimen_date == expected_doc_date


def test_parse_emias_lab_biochem_golden() -> None:
    fixture_name, source_pdf, title, expected_doc_date = LAB_FIXTURE
    text = load_pdf_text(fixture_name)
    result = parse_emias_lab(text, title, source_pdf=source_pdf)

    assert result["doc_type"] == "lab"
    assert result["title_ru"] == title
    assert result["doc_date"] == expected_doc_date
    assert _ISO_DATE.match(result["doc_date"])

    _assert_lab_rows(result["lab_rows"], expected_doc_date)

    by_key = {row["canonical_key"]: row for row in result["lab_rows"]}
    for key, expected_value in _BIOCHEM_MARKERS.items():
        assert key in by_key, f"missing marker {key!r}"
        assert by_key[key]["value"] == expected_value

    md = result["markdown_block"]
    assert "**Тип:** lab" in md
    assert "| Показатель |" in md
    assert "Глюкоза" in md
    assert result["conclusion_ru"] != "—"


def test_parse_emias_consult_golden() -> None:
    fixture_name, source_pdf, title, expected_doc_date = CONSULT_FIXTURE
    text = load_pdf_text(fixture_name)
    result = parse_emias_consult_or_imaging(
        text,
        title,
        "consultation",
        source_pdf=source_pdf,
    )

    assert result["doc_type"] == "consult"
    assert result["title_ru"] == title
    assert result["doc_date"] == expected_doc_date
    assert result["lab_rows"] == []

    conclusion = result["conclusion_ru"]
    assert "J06.8" in conclusion
    assert "Выздоровление" in conclusion

    md = result["markdown_block"]
    assert "**Тип:** consult" in md
    assert f"**Дата:** {expected_doc_date}" in md
    assert "**Осмотр терапевта**" in md
    assert "Жалобы" in md
    assert f"**Заключение:** {conclusion}" in md


def test_parse_emias_imaging_golden() -> None:
    fixture_name, source_pdf, title, expected_doc_date = IMAGING_FIXTURE
    text = load_pdf_text(fixture_name)
    result = parse_emias_consult_or_imaging(
        text,
        title,
        "imaging",
        source_pdf=source_pdf,
    )

    assert result["doc_type"] == "imaging"
    assert result["title_ru"] == title
    assert result["doc_date"] == expected_doc_date
    assert result["lab_rows"] == []

    conclusion = result["conclusion_ru"]
    assert "легких" in conclusion.lower()
    assert "не выявлено" in conclusion.lower()

    md = result["markdown_block"]
    assert "**Тип:** imaging" in md
    assert f"**Дата:** {expected_doc_date}" in md
    assert "**Результат флюорографии**" in md
    assert "флюорографии" in md
    assert f"**Заключение:** {conclusion}" in md


@pytest.mark.parametrize(
    ("fixture", "doc_type", "expected_doc_type", "expect_lab_rows"),
    [
        (LAB_FIXTURE, "lab", "lab", True),
        (CONSULT_FIXTURE, "consultation", "consult", False),
        (IMAGING_FIXTURE, "imaging", "imaging", False),
    ],
    ids=["lab", "consultation", "imaging"],
)
def test_parse_entry_routes_emias_by_doc_type(
    fixture: tuple[str, str, str, str],
    doc_type: str,
    expected_doc_type: str,
    expect_lab_rows: bool,
) -> None:
    fixture_name, source_pdf, title, expected_doc_date = fixture
    text = load_pdf_text(fixture_name)
    entry: dict[str, Any] = {
        "source_pdf": source_pdf,
        "source_system": "emias",
        "doc_type": doc_type,
        "emias_title": title,
        "created_at": f"{expected_doc_date}T12:00:00Z",
    }

    result = _parse_entry(text, entry)

    assert result["doc_type"] == expected_doc_type
    assert result["title_ru"] == title
    assert result["doc_date"] == expected_doc_date
    if expect_lab_rows:
        _assert_lab_rows(result["lab_rows"], expected_doc_date)
    else:
        assert result["lab_rows"] == []
        assert result["conclusion_ru"]
        assert "**Заключение:**" in result["markdown_block"]
