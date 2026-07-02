#!/usr/bin/env python3
"""Shared helpers for lab PDF source import scripts (EMIAS, Gemotest, …)."""
from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

import fitz

INGEST_PRIORITY: dict[str, int] = {
    "lab": 0,
    "consultation": 1,
    "nutrition": 1,
    "functional": 2,
    "imaging": 3,
    "procedure": 4,
    "other": 5,
}

_W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_CP_NS = "{http://purl.org/dc/elements/1.1/}"
_DCTERMS_NS = "{http://purl.org/dc/terms/}"


def safe_slug(name: str, max_len: int = 72) -> str:
    s = re.sub(r"[^\w\-]+", "_", name.strip(), flags=re.UNICODE)
    s = re.sub(r"_+", "_", s).strip("_")
    return s[:max_len] or "document"


def pdf_text(path: Path) -> str:
    doc = fitz.open(path)
    parts = [page.get_text("text") or "" for page in doc]
    doc.close()
    return "\n".join(parts).strip()


def docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        xml = zf.read("word/document.xml")
    root = ET.fromstring(xml)
    paras: list[str] = []
    for p in root.iter(f"{_W_NS}p"):
        texts = [t.text for t in p.iter(f"{_W_NS}t") if t.text]
        if texts:
            paras.append("".join(texts))
    return "\n".join(paras).strip()


def docx_core_date(path: Path, field: str = "modified") -> Optional[str]:
    """Return ISO date YYYY-MM-DD from docProps/core.xml (created|modified)."""
    with zipfile.ZipFile(path) as zf:
        if "docProps/core.xml" not in zf.namelist():
            return None
        root = ET.fromstring(zf.read("docProps/core.xml"))
    tag = f"{_DCTERMS_NS}{field}"
    for child in root:
        if child.tag == tag and child.text:
            return child.text[:10]
    return None


def file_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return docx_text(path)
    if suffix == ".pdf":
        return pdf_text(path)
    return path.read_text(encoding="utf-8", errors="replace").strip()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def iso_to_created_at(iso_date: str | None) -> str:
    if not iso_date:
        return ""
    return f"{iso_date}T12:00:00Z"


def ingest_priority(doc_type: str) -> int:
    return INGEST_PRIORITY.get(doc_type, 9)


def extract_dates(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    """Return ISO dates (YYYY-MM-DD) in pattern order, first match per pattern."""
    found: list[str] = []
    for pat in patterns:
        m = pat.search(text)
        if m:
            d, mo, y = m.group(1), m.group(2), m.group(3)
            found.append(f"{y}-{mo}-{d}")
    return found


_CHILD_RE = re.compile(r"Мальчик|Девочка|новорожд", re.IGNORECASE)
_PATIENT_DOB_RE = re.compile(
    r"Дата рождения(?:\s+пациента)?[:\s]*\n?\s*(\d{2})[./](\d{2})[./](\d{4})",
    re.IGNORECASE,
)


def load_owner_dob(repo_or_corpus: Path) -> str:
    from medbots.corpus_io import resolve_owner_dob

    return resolve_owner_dob(repo_or_corpus)


def is_owner_patient_text(
    text: str, owner_dob: str | None = None
) -> tuple[bool, str]:
    """False when PDF clearly belongs to another patient (child / foreign DOB)."""
    if owner_dob is None:
        import os

        owner_dob = os.environ.get("MEDBOTS_OWNER_DOB", "").strip()
    if not owner_dob:
        return True, "owner dob not configured"
    if _CHILD_RE.search(text):
        return False, "child_marker"
    dobs = sorted(
        {f"{m.group(3)}-{m.group(2)}-{m.group(1)}" for m in _PATIENT_DOB_RE.finditer(text)}
    )
    wrong = [d for d in dobs if d != owner_dob]
    if wrong and owner_dob not in dobs:
        return False, f"patient_dob={wrong}"
    return True, ""
