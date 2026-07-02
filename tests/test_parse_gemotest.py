"""Golden tests for Gemotest PDF parsing."""
from __future__ import annotations

import re
from typing import Any

import pytest

from medbots.local_structure_pdfs import _gemotest_subtype, parse_gemotest

from conftest import load_pdf_text

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

GEMOTEST_FIXTURES: list[tuple[str, str, str, str]] = [
    (
        "sources__gemotest__2020-03-03__gemotest_54397876__ОБЩЕКЛИНИЧЕСКИЕ_ИССЛЕДОВАНИЯ_КАЛА__d2d73f74.pdf.txt",
        "sources__gemotest__2020-03-03__gemotest_54397876__ОБЩЕКЛИНИЧЕСКИЕ_ИССЛЕДОВАНИЯ_КАЛА__d2d73f74.pdf",
        "ОБЩЕКЛИНИЧЕСКИЕ ИССЛЕДОВАНИЯ КАЛА",
        "2020-03-03",
    ),
    (
        "sources__gemotest__2021-02-14__gemotest_69371781__Биохимия_19_показателей__d6c4ee6e.pdf.txt",
        "sources__gemotest__2021-02-14__gemotest_69371781__Биохимия_19_показателей__d6c4ee6e.pdf",
        "Биохимия 19 показателей",
        "2021-02-14",
    ),
    (
        "sources__gemotest__2020-03-06__gemotest_54397876__Микробиологическое_исследование__204c6698.pdf.txt",
        "sources__gemotest__2020-03-06__gemotest_54397876__Микробиологическое_исследование__204c6698.pdf",
        "Микробиологическое исследование",
        "2020-03-06",
    ),
]


def _assert_lab_rows(rows: list[dict[str, Any]]) -> None:
    assert rows, "lab_rows must be non-empty"
    for row in rows:
        assert row.get("canonical_key"), f"missing canonical_key in row: {row!r}"
        specimen_date = row.get("specimen_date")
        assert specimen_date, f"missing specimen_date in row: {row!r}"
        assert _ISO_DATE.match(specimen_date), f"specimen_date not ISO: {specimen_date!r}"


@pytest.mark.parametrize(
    ("fixture_name", "source_pdf", "title", "expected_doc_date"),
    GEMOTEST_FIXTURES,
    ids=[f[2] for f in GEMOTEST_FIXTURES],
)
def test_parse_gemotest_golden(
    fixture_name: str,
    source_pdf: str,
    title: str,
    expected_doc_date: str,
) -> None:
    text = load_pdf_text(fixture_name)
    result = parse_gemotest(text, title, source_pdf)

    assert result["title_ru"] == title
    assert result["doc_date"] == expected_doc_date
    assert _ISO_DATE.match(result["doc_date"])
    _assert_lab_rows(result["lab_rows"])


@pytest.mark.parametrize(
    ("source_pdf", "expected_subtype"),
    [
        (
            "sources__gemotest__2020-03-03__gemotest_54397876__ОБЩЕКЛИНИЧЕСКИЕ_ИССЛЕДОВАНИЯ_КАЛА__d2d73f74.pdf",
            "microbiome",
        ),
        (
            "sources__gemotest__2021-02-14__gemotest_69371781__Биохимия_19_показателей__d6c4ee6e.pdf",
            "other",
        ),
        (
            "sources__gemotest__2021-03-07__gemotest_70371350__СПРАВКА__93d14ba2.pdf",
            "certificate",
        ),
        (
            "sources__gemotest__2021-08-27__gemotest_80518638__СЕРТИФИКАТ__46d00f49.pdf",
            "certificate",
        ),
        (
            "sources__gemotest__2021-08-27__gemotest_80518638__LO-50-01-012467__3d0129d8.pdf",
            "certificate",
        ),
        (
            "sources__gemotest__2020-03-06__gemotest_54397876__Микробиологическое_исследование__204c6698.pdf",
            "other",
        ),
        (
            "sources__gemotest__2021-02-14__gemotest_69371781__e_a_l__lab.pdf",
            "lab_results",
        ),
        (
            "sources__gemotest__2021-02-14__gemotest_69371781__e_a_s__cert.pdf",
            "certificate",
        ),
        (
            "sources__gemotest__2021-02-14__gemotest_69371781__e_a_m__stool.pdf",
            "microbiome",
        ),
        (
            "sources__gemotest__2021-02-14__gemotest_69371781__копрограмма__report.pdf",
            "microbiome",
        ),
    ],
)
def test_gemotest_subtype(source_pdf: str, expected_subtype: str) -> None:
    assert _gemotest_subtype(source_pdf) == expected_subtype
