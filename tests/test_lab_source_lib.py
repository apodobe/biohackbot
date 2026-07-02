"""Tests for lab_source_lib helpers."""
from __future__ import annotations

import re

from medbots.lab_source_lib import (
    content_hash,
    extract_dates,
    ingest_priority,
    iso_to_created_at,
    is_owner_patient_text,
    safe_slug,
)


def test_safe_slug_basic() -> None:
    assert safe_slug("Hello World") == "Hello_World"
    assert safe_slug("  foo__bar!!  ") == "foo_bar"
    assert safe_slug("___") == "document"


def test_safe_slug_max_len() -> None:
    long_name = "a" * 100
    assert len(safe_slug(long_name, max_len=10)) == 10
    assert safe_slug("", max_len=72) == "document"


def test_content_hash_deterministic() -> None:
    text = "lab result text"
    h1 = content_hash(text)
    h2 = content_hash(text)
    assert h1 == h2
    assert len(h1) == 64
    assert content_hash("other") != h1


def test_iso_to_created_at() -> None:
    assert iso_to_created_at("2024-03-15") == "2024-03-15T12:00:00Z"
    assert iso_to_created_at(None) == ""
    assert iso_to_created_at("") == ""


def test_ingest_priority() -> None:
    assert ingest_priority("lab") == 0
    assert ingest_priority("consultation") == 1
    assert ingest_priority("imaging") == 3
    assert ingest_priority("unknown_type") == 9


def test_extract_dates() -> None:
    patterns = [
        re.compile(r"(\d{2})\.(\d{2})\.(\d{4})"),
        re.compile(r"(\d{2})/(\d{2})/(\d{4})"),
    ]
    text = "Sample taken 15.03.2024 and backup 01/06/2023"
    assert extract_dates(text, patterns) == ["2024-03-15", "2023-06-01"]


def test_extract_dates_no_match() -> None:
    patterns = [re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")]
    assert extract_dates("no dates here", patterns) == []


def test_is_owner_patient_text_owner() -> None:
    text = "Дата рождения пациента\n20.03.1985"
    ok, reason = is_owner_patient_text(text, owner_dob="1985-03-20")
    assert ok is True
    assert reason == ""


def test_is_owner_patient_text_child() -> None:
    text = "Мальчик, 3 года"
    ok, reason = is_owner_patient_text(text, owner_dob="1985-03-20")
    assert ok is False
    assert reason == "child_marker"


def test_is_owner_patient_text_wrong_dob() -> None:
    text = "Дата рождения: 01.01.1980"
    ok, reason = is_owner_patient_text(text, owner_dob="1985-03-20")
    assert ok is False
    assert reason.startswith("patient_dob=")
