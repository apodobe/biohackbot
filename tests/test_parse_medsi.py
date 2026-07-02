"""Tests for Medsi lab PDF parsing (local_structure_pdfs)."""
from __future__ import annotations

import re
from typing import Any

import pytest

from medbots.local_structure_pdfs import (
    _extract_medsi_facility,
    _parse_entry,
    parse_medsi_lab,
)
from conftest import load_pdf_text

BIOCHEM_FIXTURE = (
    "sources__medsi__2026-06-16__drop_Биохимический_анализ_крови__2e563e81.pdf.txt"
)
CBC_FIXTURE = (
    "sources__medsi__2026-06-16__drop_Клинический_анализ_крови__4d39f738.pdf.txt"
)
MIN_BIOCHEM_ROWS = 5
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


@pytest.fixture(scope="module")
def biochem_text() -> str:
    return load_pdf_text(BIOCHEM_FIXTURE)


@pytest.fixture(scope="module")
def cbc_text() -> str:
    return load_pdf_text(CBC_FIXTURE)


@pytest.fixture(scope="module")
def biochem_parsed(biochem_text: str) -> dict[str, Any]:
    return parse_medsi_lab(biochem_text, "Биохимический анализ крови")


@pytest.fixture(scope="module")
def cbc_parsed(cbc_text: str) -> dict[str, Any]:
    return parse_medsi_lab(cbc_text, "Клинический анализ крови")


def _medsi_lab_entry(*, title: str = "Биохимический анализ крови") -> dict[str, Any]:
    return {
        "source_system": "medsi",
        "doc_type": "lab",
        "source_pdf": f"sources/medsi/2026-06-16/drop/{title}.pdf",
        "user_drop_title": title,
        "created_at": "2026-06-16T12:00:00",
    }


class TestParseMedsiLab:
    def test_biochem_parses_minimum_rows(self, biochem_parsed: dict[str, Any]) -> None:
        assert len(biochem_parsed["lab_rows"]) >= MIN_BIOCHEM_ROWS

    def test_cbc_parses_rows(self, cbc_parsed: dict[str, Any]) -> None:
        assert len(cbc_parsed["lab_rows"]) >= MIN_BIOCHEM_ROWS

    def test_doc_date_iso_format(self, biochem_parsed: dict[str, Any]) -> None:
        doc_date = biochem_parsed["doc_date"]
        assert doc_date is not None
        assert ISO_DATE_RE.match(doc_date)

    def test_lab_rows_have_required_fields(self, biochem_parsed: dict[str, Any]) -> None:
        for row in biochem_parsed["lab_rows"]:
            assert isinstance(row["canonical_key"], str) and row["canonical_key"]
            assert row["value"] is not None
            assert isinstance(row["unit"], str)

    def test_biochem_glucose_row(self, biochem_parsed: dict[str, Any]) -> None:
        glucose = next(
            r for r in biochem_parsed["lab_rows"] if r["canonical_key"] == "glyukoza_venoznoy_krovi_natoschak"
        )
        assert glucose["value"] == pytest.approx(4.82)
        assert glucose["unit"] == "ммоль/л"

    def test_returns_lab_doc_type(self, biochem_parsed: dict[str, Any]) -> None:
        assert biochem_parsed["doc_type"] == "lab"


class TestExtractMedsiFacility:
    def test_extracts_from_biochem_fixture(self, biochem_text: str) -> None:
        facility = _extract_medsi_facility(biochem_text)
        assert isinstance(facility, str)
        assert facility


class TestParseEntryMedsiLab:
    def test_routes_medsi_lab_entry(self, biochem_text: str) -> None:
        entry = _medsi_lab_entry()
        parsed = _parse_entry(biochem_text, entry)

        assert parsed["doc_type"] == "lab"
        assert len(parsed["lab_rows"]) >= MIN_BIOCHEM_ROWS
        assert ISO_DATE_RE.match(parsed["doc_date"])
        assert parsed.get("institution")

    def test_parse_entry_lab_rows_shape(self, biochem_text: str) -> None:
        parsed = _parse_entry(biochem_text, _medsi_lab_entry())
        for row in parsed["lab_rows"]:
            assert row["canonical_key"]
            assert row["value"] is not None
            assert "unit" in row

    def test_routes_cbc_via_title(self, cbc_text: str) -> None:
        entry = _medsi_lab_entry(title="Клинический анализ крови")
        parsed = _parse_entry(cbc_text, entry)
        assert parsed["doc_type"] == "lab"
        assert len(parsed["lab_rows"]) >= MIN_BIOCHEM_ROWS
