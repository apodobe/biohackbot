#!/usr/bin/env python3
"""Structure EMIAS, Gemotest, and Medsi PDFs from pdf_text without external LLM API."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from medbots.corpus_io import bot_root, default_corpus_root, load_manifest, load_patient_dob, write_manifest
from medbots.corpus_writers import (
    _append_lab_rows,
    _safe_txt_name,
    _write_doc_text_md,
    _write_to_extracted_images_md,
    sha256_bytes,
)

_DATE_DMY = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_DATE_RESEARCH = re.compile(
    r"Дата исследования:\s*(\d{2})\.(\d{2})\.(\d{4})", re.IGNORECASE
)
_EMIAS_DATE = re.compile(r"Дата:\s*(\d{2})\.(\d{2})\.(\d{4})", re.IGNORECASE)
_PRINT_DATE = re.compile(r"ПЕЧАТЬ:\s*(\d{2})\.(\d{2})\.(\d{4})", re.IGNORECASE)
_ORDER_DATE = re.compile(
    r"Дата регистрации заказа\s*\n\s*(\d{2})\.(\d{2})\.(\d{4})", re.IGNORECASE
)
_SLASH_ORDER_DATE = re.compile(
    r"дата:\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE
)
_GEMOTEST_DATE_MULTILINE = re.compile(
    r"дата:\s*\n\s*(\d{2})/(\d{2})/(\d{4})", re.IGNORECASE
)
_FILENAME_ISO_DATE = re.compile(r"(?:^|/)(20\d{2}-\d{2}-\d{2})__")
_skip_patient_dob: str = ""
_SECTION_HEADERS = frozenset(
    {
        "Биохимия 19 показателей (расширенная)",
        "ОБЩЕКЛИНИЧЕСКИЕ ИССЛЕДОВАНИЯ КАЛА",
        "Копрограмма",
        "БИОХИМИЯ (Капиллярная кровь)",
    }
)
_NUMERIC = re.compile(r"^[\d]+(?:[.,]\d+)?$")
_SKIP_LINES = frozenset(
    {
        "Исследование",
        "Значение",
        "Ед. изм.",
        "Нормальные значения",
        "Нормальные \nзначения",
        "Диагноз",
        "Тест",
        "Результат",
        "Норма",
        "Отклонение",
        "Критичность отклонения",
        "Критичность",
        "отклонения",
        "Ед. изм.",
    }
)

_CYRILLIC = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "kh",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sch",
    "ъ": "",
    "ы": "y",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
}


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dmy_to_iso(d: str, m: str, y: str) -> str:
    return f"{y}-{m}-{d}"


def _date_from_source_path(source_pdf: str) -> Optional[str]:
    m = _FILENAME_ISO_DATE.search(source_pdf.replace("\\", "/"))
    if not m:
        return None
    iso = m.group(1)
    if iso.endswith("-unknown") or "unknown" in iso:
        return None
    return iso


def _first_iso_date(text: str, *, source_pdf: str = "", fallback_iso: Optional[str] = None) -> Optional[str]:
    path_date = _date_from_source_path(source_pdf)
    if path_date:
        return path_date
    m = _GEMOTEST_DATE_MULTILINE.search(text)
    if m:
        return _dmy_to_iso(m.group(1), m.group(2), m.group(3))
    for pat in (_EMIAS_DATE, _DATE_RESEARCH, _PRINT_DATE, _ORDER_DATE, _SLASH_ORDER_DATE):
        m = pat.search(text)
        if m:
            iso = _dmy_to_iso(m.group(1), m.group(2), m.group(3))
            if iso != _skip_patient_dob:
                return iso
    m = _DATE_DMY.search(text)
    if m:
        iso = _dmy_to_iso(m.group(1), m.group(2), m.group(3))
        if iso != _skip_patient_dob:
            return iso
    if fallback_iso and fallback_iso != _skip_patient_dob:
        return fallback_iso
    return None


def _transliterate_ru(text: str) -> str:
    out: list[str] = []
    for ch in text.lower():
        if ch in _CYRILLIC:
            out.append(_CYRILLIC[ch])
        elif ch.isascii() and (ch.isalnum() or ch in "-_"):
            out.append(ch)
        else:
            out.append("_")
    return "".join(out)


def _canonical_key(name_ru: str) -> str:
    slug = _transliterate_ru(name_ru)
    slug = re.sub(r"[^\w]+", "_", slug)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:80] or "analyte"


def _parse_float(value: str) -> Optional[float]:
    v = value.strip().replace(",", ".")
    if not v or not _NUMERIC.match(v):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _parse_ref_range(ref_text: str) -> tuple[Optional[float], Optional[float], Optional[str]]:
    ref = " ".join(ref_text.split())
    if not ref or ref.lower().startswith("смотри"):
        return None, None, ref or None
    m = re.search(r"([\d.,]+)\s*[-–]\s*([\d.,]+)", ref)
    if m:
        lo = _parse_float(m.group(1))
        hi = _parse_float(m.group(2))
        return lo, hi, None
    m = re.match(r"^[<≤]\s*=?([\d.,]+)\s*$", ref)
    if m:
        hi = _parse_float(m.group(1))
        return None, hi, ref if hi is None else None
    m = re.match(r"^[>≥]\s*=?([\d.,]+)\s*$", ref)
    if m:
        lo = _parse_float(m.group(1))
        return lo, None, ref if lo is None else None
    if ref.startswith("<") or ref.startswith(">") or ref.startswith("<="):
        return None, None, ref
    if _NUMERIC.match(ref.replace(",", ".")):
        return None, None, ref
    return None, None, ref


def _lab_row(
    *,
    name_ru: str,
    value: Any,
    unit: str = "",
    ref_low: Optional[float] = None,
    ref_high: Optional[float] = None,
    ref_note: Optional[str] = None,
    specimen_date: str,
    facility: str = "ЕМИАС",
) -> dict[str, Any]:
    return {
        "canonical_key": _canonical_key(name_ru),
        "name_ru": name_ru.strip(),
        "name_en": None,
        "loinc": None,
        "value": value,
        "unit": unit or None,
        "ref_low": ref_low,
        "ref_high": ref_high,
        "ref_note": ref_note,
        "specimen_date": specimen_date,
        "report_date": specimen_date,
        "facility": facility,
        "source_kind": "pdf_text",
    }


def _markdown_header(
    *,
    doc_type: str,
    doc_date: Optional[str],
    title: str,
    institution: str = "—",
) -> str:
    return (
        f"**Тип:** {doc_type}\n"
        f"**Дата:** {doc_date or 'дата неизвестна'}\n"
        f"**Учреждение:** {institution}\n"
        f"**Врач:** —\n\n"
        f"**{title}**\n\n"
    )


def _extract_emias_facility(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("ГБУЗ") or line.startswith("МНПЦ") or "поликлиник" in line.lower():
            return line[:120]
    return "ЕМИАС"


def _extract_medsi_facility(text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if "медси" in line.lower() or "мичуринск" in line.lower():
            return line[:120]
    if "медси" in text.lower():
        return "Медси"
    return "Медси"


def _extract_conclusion(text: str) -> str:
    m = re.search(
        r"Заключение:?\s*\n+(.+?)(?:\n-{3,}|\nРекомендаци|\nПОДПИСИ|\nЗаключение протокола|\nДата:|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return " ".join(m.group(1).split())[:500]
    m = re.search(
        r"Заключение:\s*(.+?)(?:\nЗаключение протокола|\nРекомендаци|\nПОДПИСИ|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if m:
        return " ".join(m.group(1).split())[:500]
    m = re.search(r"Основной\s*\n\s*диагноз\s*\n+(.+?)(?:\nРекомендации|\nДата:|\Z)", text, re.DOTALL | re.IGNORECASE)
    if m:
        return " ".join(m.group(1).split())[:500]
    return "—"


def parse_emias_lab(text: str, title: str, *, source_pdf: str = "", fallback_iso: Optional[str] = None) -> dict[str, Any]:
    doc_date = _first_iso_date(text, source_pdf=source_pdf, fallback_iso=fallback_iso)
    facility = _extract_emias_facility(text)
    lab_rows: list[dict[str, Any]] = []
    title_l = title.lower()
    text_l = text.lower()

    if "антител" in title_l or "igg" in text_l or "igm" in text_l:
        blocks = re.findall(
            r"Определение антител (Ig[MG]) к\s+Coronavirus \(SARS-[\s\n]*CoV-2\)\s*\n([\d.,]+)\s*\n(<[\d.,]+)",
            text,
            re.IGNORECASE,
        )
        for ig_type, val_s, ref_s in blocks:
            name_clean = f"Определение антител {ig_type.upper()} к Coronavirus (SARS-CoV-2)"
            val = _parse_float(val_s)
            ref_note = ref_s.strip() if ref_s else None
            if doc_date:
                lab_rows.append(
                    _lab_row(
                        name_ru=name_clean,
                        value=val,
                        unit="Ед/мл",
                        ref_note=ref_note,
                        specimen_date=doc_date,
                        facility=facility,
                    )
                )
    elif re.search(r"Исследование - \(L", text):
        lab_date = doc_date or _medsi_iso_date(text)
        if lab_date:
            lab_rows = _parse_medsi_lab_rows(text, lab_date, facility)
    else:
        m = re.search(
            r"(РНК\s+Coronavirus[^\n]+|Исследование на коронавирусы[^\n]*)\s*\n\s*(Не обнаружено|обнаружено|Обнаружено)",
            text,
            re.IGNORECASE,
        )
        if m:
            test_name = " ".join(m.group(1).split())
            result = m.group(2).strip()
            if doc_date:
                lab_rows.append(
                    _lab_row(
                        name_ru=test_name,
                        value=None,
                        ref_note=result,
                        specimen_date=doc_date,
                        facility=facility,
                    )
                )

    result_summary = "—"
    if lab_rows:
        parts = []
        for row in lab_rows:
            val = row.get("value")
            note = row.get("ref_note")
            if val is not None:
                parts.append(f"{row['name_ru']}: {val}")
            elif note:
                parts.append(f"{row['name_ru']}: {note}")
        result_summary = "; ".join(parts)

    md_lines = [_markdown_header(doc_type="lab", doc_date=doc_date, title=title, institution=facility)]
    if lab_rows:
        md_lines.append("| Показатель | Результат | Ед. | Референс |")
        md_lines.append("|------------|-----------|-----|----------|")
        for row in lab_rows:
            val_s = str(row["value"]) if row.get("value") is not None else (row.get("ref_note") or "—")
            ref = row.get("ref_note") if row.get("value") is not None else "—"
            md_lines.append(
                f"| {row['name_ru']} | {val_s} | {row.get('unit') or '—'} | {ref} |"
            )
    else:
        md_lines.append(text.strip())

    return {
        "doc_date": doc_date,
        "doc_type": "lab",
        "title_ru": title,
        "institution": facility,
        "conclusion_ru": result_summary,
        "markdown_block": "\n".join(md_lines),
        "lab_rows": lab_rows,
    }


def parse_emias_consult_or_imaging(
    text: str, title: str, doc_type: str, *, source_pdf: str = "", fallback_iso: Optional[str] = None,
    facility_override: str | None = None,
) -> dict[str, Any]:
    doc_date = _first_iso_date(text, source_pdf=source_pdf, fallback_iso=fallback_iso)
    facility = facility_override or _extract_emias_facility(text)
    conclusion = _extract_conclusion(text)
    if doc_type == "imaging":
        mapped_type = "imaging"
    elif doc_type == "functional":
        mapped_type = "functional"
    else:
        mapped_type = "consult"
    body = text.strip()
    md = _markdown_header(
        doc_type=mapped_type,
        doc_date=doc_date,
        title=title,
        institution=facility,
    )
    md += f"```\n{body}\n```\n\n**Заключение:** {conclusion}"
    return {
        "doc_date": doc_date,
        "doc_type": mapped_type,
        "title_ru": title,
        "institution": facility,
        "conclusion_ru": conclusion,
        "markdown_block": md,
        "lab_rows": [],
    }


def _gemotest_subtype(source_pdf: str) -> str:
    name = Path(source_pdf).name.lower()
    if any(k in name for k in ("справка", "сертификат", "lo-50")):
        return "certificate"
    if "_e_a_m_" in name or "кала" in name or "копрограмм" in name:
        return "microbiome"
    if "_e_a_s_" in name:
        return "certificate"
    if "_e_a_l_" in name or "e_a_l" in name:
        return "lab_results"
    return "other"


def _gemotest_facility(text: str) -> str:
    m = re.search(r'(\d+\.\s*"[^"]+")', text)
    if m:
        return m.group(1)
    if "Гемотест" in text:
        return 'ООО "Лаборатория Гемотест"'
    return "Гемотест"


def _is_section_header(line: str) -> bool:
    if line in _SECTION_HEADERS:
        return True
    return line.startswith("Биохимия ") and "показател" in line.lower()


def _collect_analyte_name(lines: list[str], start_idx: int) -> str:
    name_parts: list[str] = []
    k = start_idx
    while k >= 0:
        prev = lines[k]
        if _DATE_RESEARCH.match(prev) or prev.startswith("ПЕЧАТЬ:"):
            break
        if prev in _SKIP_LINES or _is_section_header(prev):
            k -= 1
            continue
        if _NUMERIC.match(prev.replace(",", ".")):
            break
        if prev.startswith("Нормальный уровень"):
            break
        if len(prev) > 120:
            break
        name_parts.insert(0, prev)
        k -= 1
    return " ".join(name_parts).strip()


def _append_gemotest_row(
    rows: list[dict[str, Any]],
    seen: set[tuple[str, str]],
    *,
    name_ru: str,
    specimen_date: str,
    facility: str,
    value: Any = None,
    unit: str = "",
    ref_low: Optional[float] = None,
    ref_high: Optional[float] = None,
    ref_note: Optional[str] = None,
) -> None:
    if not name_ru or len(name_ru) < 2 or not specimen_date:
        return
    key = (_canonical_key(name_ru), specimen_date)
    if key in seen:
        return
    seen.add(key)
    rows.append(
        _lab_row(
            name_ru=name_ru,
            value=value,
            unit=unit,
            ref_low=ref_low,
            ref_high=ref_high,
            ref_note=ref_note,
            specimen_date=specimen_date,
            facility=facility,
        )
    )


def _parse_gemotest_numeric_blocks(text: str, facility: str) -> list[dict[str, Any]]:
    """Parse Gemotest blocks: name / value / unit / ref / Дата исследования."""
    lines = [ln.strip() for ln in text.splitlines()]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()

    for i, line in enumerate(lines):
        m = _DATE_RESEARCH.match(line)
        if not m or i < 3:
            continue
        specimen_date = _dmy_to_iso(m.group(1), m.group(2), m.group(3))
        ref_line = lines[i - 1]
        unit_line = lines[i - 2]
        value_line = lines[i - 3]

        if ref_line.startswith("Нормальный уровень"):
            continue

        val = _parse_float(value_line)
        if val is None:
            name_ru = _collect_analyte_name(lines, i - 4)
            _append_gemotest_row(
                rows,
                seen,
                name_ru=name_ru,
                value=None,
                ref_note=value_line,
                specimen_date=specimen_date,
                facility=facility,
            )
            continue

        unit = ""
        if unit_line not in _SKIP_LINES and not _NUMERIC.match(unit_line.replace(",", ".")):
            unit = unit_line
            name_idx = i - 4
        else:
            name_idx = i - 3

        ref_low, ref_high, ref_note = _parse_ref_range(ref_line)
        name_ru = _collect_analyte_name(lines, name_idx)
        _append_gemotest_row(
            rows,
            seen,
            name_ru=name_ru,
            value=val,
            unit=unit,
            ref_low=ref_low,
            ref_high=ref_high,
            ref_note=ref_note,
            specimen_date=specimen_date,
            facility=facility,
        )
    return rows


def _parse_gemotest_quad_table(
    text: str, facility: str, specimen_date: str
) -> list[dict[str, Any]]:
    """Parse 4-line Gemotest tables without per-analyte dates (capillary biochemistry)."""
    lines = [ln.strip() for ln in text.splitlines()]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    stop_markers = (
        "Результат лабораторных",
        "Получая данный",
        "Электронная подпись",
        "ПЕЧАТЬ:",
        "Качество исследований",
    )

    start = 0
    for idx, ln in enumerate(lines):
        if "Нормальные значения" in ln or ln.startswith("БИОХИМИЯ"):
            start = idx + 1
            break

    i = start
    while i < len(lines) - 3:
        line = lines[i]
        if any(marker in line for marker in stop_markers):
            break
        if line in _SKIP_LINES or _is_section_header(line) or not line:
            i += 1
            continue
        if ":" in line or line.startswith("№"):
            i += 1
            continue

        name = line
        val_s = lines[i + 1]
        unit = lines[i + 2]
        ref = lines[i + 3]

        if _DATE_RESEARCH.match(val_s) or _DATE_RESEARCH.match(unit):
            i += 1
            continue
        if _NUMERIC.match(unit.replace(",", ".")):
            i += 1
            continue
        if not re.search(r"[а-яa-z]", name, re.IGNORECASE):
            i += 1
            continue

        val = _parse_float(val_s)
        ref_low, ref_high, ref_note = _parse_ref_range(ref)
        if val is not None:
            _append_gemotest_row(
                rows,
                seen,
                name_ru=name,
                value=val,
                unit=unit if unit not in _SKIP_LINES else "",
                ref_low=ref_low,
                ref_high=ref_high,
                ref_note=ref_note,
                specimen_date=specimen_date,
                facility=facility,
            )
            i += 4
            continue
        i += 1
    return rows


def _coprogram_norm_continues(norm: str) -> bool:
    n = norm.rstrip().lower()
    return n.endswith("или") or n.endswith("или,") or "или" in n and not n.endswith("немного")


def _read_coprogram_triplet(lines: list[str], i: int) -> tuple[str, str, str, int] | None:
    if i + 2 >= len(lines):
        return None
    name = lines[i]
    if lines[i + 1].rstrip().endswith(","):
        if i + 3 >= len(lines):
            return None
        result = f"{lines[i + 1]} {lines[i + 2]}".strip()
        norm = lines[i + 3]
        next_i = i + 4
    else:
        result = lines[i + 1]
        norm = lines[i + 2]
        next_i = i + 3
    if next_i < len(lines) and _coprogram_norm_continues(norm):
        norm = f"{norm} {lines[next_i]}".strip()
        next_i += 1
    return name, result, norm, next_i


def _parse_gemotest_coprogram_rows(
    text: str, specimen_date: str, facility: str
) -> list[dict[str, Any]]:
    """Parse coprogram section: name / result [/ multiline] / norm."""
    m = re.search(
        r"Копрограмма\s*\n(.+?)(?:\nКачество исследований|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return []

    lines = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    i = 0
    while i < len(lines):
        name = lines[i]
        if not name or name in _SKIP_LINES or _is_section_header(name):
            i += 1
            continue
        triplet = _read_coprogram_triplet(lines, i)
        if not triplet:
            break
        name, result, norm, i = triplet
        if not result or _DATE_RESEARCH.match(result):
            continue

        val = _parse_float(result)
        ref_low, ref_high, ref_note = _parse_ref_range(norm)
        if val is not None:
            _append_gemotest_row(
                rows,
                seen,
                name_ru=name,
                value=val,
                ref_low=ref_low,
                ref_high=ref_high,
                ref_note=ref_note,
                specimen_date=specimen_date,
                facility=facility,
            )
        else:
            _append_gemotest_row(
                rows,
                seen,
                name_ru=name,
                value=None,
                ref_note=f"{result} (норма: {norm})" if norm else result,
                specimen_date=specimen_date,
                facility=facility,
            )
    return rows


def _parse_gemotest_qualitative_table(text: str) -> str:
    m = re.search(
        r"Копрограмма\s*\n(.+?)(?:\nКачество исследований|\Z)",
        text,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return text.strip()

    lines = [ln.strip() for ln in m.group(1).splitlines() if ln.strip()]
    rows: list[tuple[str, str, str]] = []
    i = 0
    while i < len(lines):
        name = lines[i]
        if not name or name in _SKIP_LINES or _is_section_header(name):
            i += 1
            continue
        triplet = _read_coprogram_triplet(lines, i)
        if not triplet:
            break
        name, val, norm, i = triplet
        if val and norm and not _DATE_RESEARCH.match(val):
            rows.append((name, val, norm))

    if not rows:
        return text.strip()
    out = ["| Показатель | Результат | Норма |", "|------------|-----------|-------|"]
    for name, val, norm in rows:
        out.append(f"| {name} | {val} | {norm} |")
    return "\n".join(out)


def parse_gemotest(
    text: str,
    title: str,
    source_pdf: str,
    *,
    fallback_iso: Optional[str] = None,
) -> dict[str, Any]:
    subtype = _gemotest_subtype(source_pdf)
    facility = _gemotest_facility(text)
    doc_date = _first_iso_date(text, source_pdf=source_pdf, fallback_iso=fallback_iso)

    if subtype == "certificate":
        md = _markdown_header(
            doc_type="consult",
            doc_date=doc_date,
            title=title,
            institution=facility,
        )
        md += f"```\n{text.strip()}\n```"
        return {
            "doc_date": doc_date,
            "doc_type": "consult",
            "title_ru": title,
            "institution": facility,
            "conclusion_ru": "Справка/сертификат",
            "markdown_block": md,
            "lab_rows": [],
        }

    if subtype == "microbiome" or "копрограмма" in text.lower():
        table = _parse_gemotest_qualitative_table(text)
        lab_rows: list[dict[str, Any]] = []
        if doc_date:
            lab_rows = _parse_gemotest_coprogram_rows(text, doc_date, facility)
        md = _markdown_header(
            doc_type="lab",
            doc_date=doc_date,
            title=title,
            institution=facility,
        )
        md += table
        return {
            "doc_date": doc_date,
            "doc_type": "lab",
            "title_ru": title,
            "institution": facility,
            "conclusion_ru": "Качественное исследование",
            "markdown_block": md,
            "lab_rows": lab_rows,
        }

    lab_rows = _parse_gemotest_numeric_blocks(text, facility)
    if not lab_rows and doc_date:
        lab_rows = _parse_gemotest_quad_table(text, facility, doc_date)
    md = _markdown_header(
        doc_type="lab",
        doc_date=doc_date,
        title=title,
        institution=facility,
    )
    if lab_rows:
        md += "| Показатель | Значение | Ед. | Референс |\n"
        md += "|------------|----------|-----|----------|\n"
        for row in lab_rows:
            val_s = str(row["value"]) if row.get("value") is not None else (row.get("ref_note") or "—")
            ref = (
                f"{row['ref_low']}–{row['ref_high']}"
                if row.get("ref_low") is not None and row.get("ref_high") is not None
                else (row.get("ref_note") or "—")
            )
            md += f"| {row['name_ru']} | {val_s} | {row.get('unit') or '—'} | {ref} |\n"
    else:
        md += text.strip()

    conclusion = "—"
    if lab_rows:
        conclusion = f"Извлечено показателей: {len(lab_rows)}"

    return {
        "doc_date": doc_date,
        "doc_type": "lab",
        "title_ru": title,
        "institution": facility,
        "conclusion_ru": conclusion,
        "markdown_block": md,
        "lab_rows": lab_rows,
    }


_MEDSI_UNIT = re.compile(
    r"^(?:ммоль/л|мг/л|г/л|ед/л|мкмоль/л|%|фл|пг|мм/час|10\*9/л|10\*12/л|клеток/мкл)$",
    re.IGNORECASE,
)
_MEDSI_SKIP = frozenset(
    {
        "венозная",
        "Наименование исследования",
        "Результат",
        "Ед. изм.",
        "Нормальные значения",
        "Флаг",
        "Врач КДЛ:",
    }
)


def _is_medsi_unit_line(line: str) -> bool:
    s = line.strip()
    return bool(_MEDSI_UNIT.match(s))


def _is_medsi_ref_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if s.startswith("<") or s.startswith(">") or s.startswith("≤") or s.startswith("≥"):
        return True
    return bool(re.match(r"^[\d.,]+\s*[-–]\s*[\d.,]+$", s))


def _is_medsi_value_line(line: str) -> bool:
    return _parse_float(line.strip()) is not None


def _medsi_iso_date(text: str) -> Optional[str]:
    m = _EMIAS_DATE.search(text)
    if m:
        return _dmy_to_iso(m.group(1), m.group(2), m.group(3))
    return _first_iso_date(text)


def _parse_medsi_lab_rows(text: str, doc_date: str, facility: str) -> list[dict[str, Any]]:
    lines = [ln.rstrip() for ln in text.splitlines()]
    rows: list[dict[str, Any]] = []
    i = 0
    in_table = False

    while i < len(lines):
        raw = lines[i].strip()
        i += 1
        if not raw:
            continue
        if raw in _MEDSI_SKIP:
            continue
        if raw.startswith("Исследование - (L"):
            in_table = True
            continue
        if not in_table:
            continue
        if raw.startswith("Согласно ") or raw.startswith("Диагностические"):
            continue
        if raw.startswith("Нормальный уровень") or raw.startswith("уровень глюкозы"):
            continue
        if raw.startswith("Выполнено по методу"):
            continue
        if re.match(r"^\d{2}\.\d{2}\.\d{4}", raw):
            continue
        if "Врач" in raw and ":" not in raw[:20]:
            continue

        name_parts = [raw]
        while i < len(lines):
            nxt = lines[i].strip()
            if not nxt:
                i += 1
                continue
            if (
                _is_medsi_unit_line(nxt)
                or _is_medsi_ref_line(nxt)
                or _is_medsi_value_line(nxt)
                or nxt.startswith("Исследование - (L")
            ):
                break
            if nxt in _MEDSI_SKIP:
                i += 1
                break
            name_parts.append(nxt)
            i += 1

        name = " ".join(name_parts).strip()
        if not name or name in _MEDSI_SKIP:
            continue

        unit = ""
        ref_low: Optional[float] = None
        ref_high: Optional[float] = None
        ref_note: Optional[str] = None
        value: Optional[float] = None

        if i < len(lines) and _is_medsi_unit_line(lines[i].strip()):
            unit = lines[i].strip()
            i += 1

        if i < len(lines) and _is_medsi_ref_line(lines[i].strip()):
            ref_low, ref_high, ref_note = _parse_ref_range(lines[i].strip())
            i += 1

        if i < len(lines) and _is_medsi_value_line(lines[i].strip()):
            value = _parse_float(lines[i].strip())
            i += 1

        if value is None and ref_note is None:
            continue

        rows.append(
            _lab_row(
                name_ru=name,
                value=value,
                unit=unit,
                ref_low=ref_low,
                ref_high=ref_high,
                ref_note=ref_note,
                specimen_date=doc_date,
                facility=facility,
            )
        )

    return rows


def parse_medsi_lab(
    text: str,
    title: str,
    *,
    source_pdf: str = "",
    fallback_iso: Optional[str] = None,
) -> dict[str, Any]:
    doc_date = _medsi_iso_date(text) or fallback_iso
    facility = "Медси"
    if "мичуринск" in text.lower():
        facility = 'Медси "Мичуринский"'
    lab_rows: list[dict[str, Any]] = []
    if doc_date:
        lab_rows = _parse_medsi_lab_rows(text, doc_date, facility)

    md = _markdown_header(
        doc_type="lab",
        doc_date=doc_date,
        title=title,
        institution=facility,
    )
    if lab_rows:
        md += "| Показатель | Значение | Ед. | Референс |\n"
        md += "|------------|----------|-----|----------|\n"
        for row in lab_rows:
            val_s = str(row["value"]) if row.get("value") is not None else "—"
            ref = (
                f"{row['ref_low']}–{row['ref_high']}"
                if row.get("ref_low") is not None and row.get("ref_high") is not None
                else (row.get("ref_note") or "—")
            )
            md += f"| {row['name_ru']} | {val_s} | {row.get('unit') or '—'} | {ref} |\n"
    else:
        md += text.strip()

    conclusion = f"Извлечено показателей: {len(lab_rows)}" if lab_rows else "—"
    return {
        "doc_date": doc_date,
        "doc_type": "lab",
        "title_ru": title,
        "institution": facility,
        "conclusion_ru": conclusion,
        "markdown_block": md,
        "lab_rows": lab_rows,
    }


def _append_extracted_section_if_new(
    corpus: Path, section_id: str, extracted: dict[str, Any]
) -> None:
    md_path = corpus / "EXTRACTED_FROM_IMAGES.md"
    if md_path.exists() and f"## {section_id}" in md_path.read_text(encoding="utf-8"):
        return
    _write_to_extracted_images_md(corpus, section_id, extracted)


def _is_legacy_flat_entry(entry: dict[str, Any]) -> bool:
    source_system = (entry.get("source_system") or "").lower()
    source_pdf = entry.get("source_pdf") or ""
    if source_system == "legacy_flat" and entry.get("extracted_txt"):
        return True
    return bool(source_pdf and not source_pdf.startswith("sources/") and entry.get("extracted_txt"))


def _infer_legacy_doc_type(source_pdf: str) -> str:
    s = source_pdf.lower()
    if any(
        k in s
        for k in (
            "лаборатор",
            "анализ",
            "исследован",
            "кров",
            "моч",
            "биохим",
        )
    ):
        return "lab"
    if any(k in s for k in ("эхокарди", "узи", "рентген", "мрт", "кт", "флюорограф")):
        return "imaging"
    if any(k in s for k in ("осмотр", "консультац", "эпикриз")):
        return "consultation"
    return "other"


def _is_target_entry(entry: dict[str, Any], *, force: bool = False, sources: set[str] | None = None) -> bool:
    if entry.get("grok_ingested_at"):
        return False
    source_pdf = entry.get("source_pdf") or ""
    source_system = (entry.get("source_system") or "").lower()
    if sources and source_system not in sources:
        if not any(s in source_pdf for s in sources):
            if not (_is_legacy_flat_entry(entry) and "legacy_flat" in sources):
                return False
    if entry.get("structured_locally_at") and not force:
        return False
    if _is_legacy_flat_entry(entry):
        return True
    if source_system in ("emias", "gemotest"):
        return True
    if "sources/emias" in source_pdf or "sources/gemotest" in source_pdf:
        return True
    if source_system == "medsi" or "sources/medsi" in source_pdf:
        if entry.get("user_drop_batch") or entry.get("ingest_note") == "ALL-NEW-FILES drop":
            return True
    return False


def _entry_title(entry: dict[str, Any]) -> str:
    return (
        entry.get("emias_title")
        or entry.get("gemotest_title")
        or entry.get("user_drop_title")
        or entry.get("grok_title")
        or Path(entry.get("source_pdf") or "document.pdf").stem
    )


def _entry_sha(entry: dict[str, Any], pdf_path: Path) -> str:
    for key in ("sha256", "emias_content_sha256", "gemotest_content_sha256"):
        h = entry.get(key)
        if isinstance(h, str) and len(h) >= 12:
            return h
    if pdf_path.is_file():
        return sha256_bytes(pdf_path.read_bytes())
    return hashlib.sha256((entry.get("source_pdf") or "").encode()).hexdigest()


def _pdf_text_path(corpus: Path, entry: dict[str, Any]) -> Path:
    rel = entry.get("extracted_txt")
    if isinstance(rel, str) and rel.startswith("pdf_text/"):
        return corpus / rel
    source_pdf = entry.get("source_pdf") or ""
    return corpus / "pdf_text" / _safe_txt_name(source_pdf)


def _parse_entry(text: str, entry: dict[str, Any]) -> dict[str, Any]:
    title = _entry_title(entry)
    source_pdf = entry.get("source_pdf") or ""
    source_system = (entry.get("source_system") or "").lower()
    doc_type = entry.get("doc_type") or "other"
    fallback_iso = (entry.get("created_at") or "")[:10] or None
    title_l = title.lower()
    is_legacy = _is_legacy_flat_entry(entry)
    if is_legacy and not doc_type:
        doc_type = _infer_legacy_doc_type(source_pdf)

    if is_legacy and doc_type == "lab":
        if "Показатель" in text and "Референсные значения" in text:
            return parse_gemotest(text, title, source_pdf, fallback_iso=fallback_iso)
        return parse_emias_lab(text, title, source_pdf=source_pdf, fallback_iso=fallback_iso)

    if source_system == "medsi" or "sources/medsi" in source_pdf:
        facility = _extract_medsi_facility(text)
        if doc_type == "lab" or "анализ крови" in title_l or "биохим" in title_l:
            parsed = parse_medsi_lab(
                text, title, source_pdf=source_pdf, fallback_iso=fallback_iso
            )
            parsed["institution"] = facility
            return parsed
        if doc_type == "functional" or "электрокарди" in title_l or "эхокг" in title_l:
            return parse_emias_consult_or_imaging(
                text, title, "functional", source_pdf=source_pdf, fallback_iso=fallback_iso,
                facility_override=facility,
            )
        if doc_type == "imaging" or "ультразвуков" in title_l or "дуплекс" in title_l:
            return parse_emias_consult_or_imaging(
                text, title, "imaging", source_pdf=source_pdf, fallback_iso=fallback_iso,
                facility_override=facility,
            )
        return parse_emias_consult_or_imaging(
            text, title, "consultation", source_pdf=source_pdf, fallback_iso=fallback_iso,
            facility_override=facility,
        )

    if source_system == "gemotest" or "sources/gemotest" in source_pdf:
        return parse_gemotest(text, title, source_pdf, fallback_iso=fallback_iso)

    if doc_type == "lab" or "коронавирус" in title.lower() or "covid" in title.lower():
        return parse_emias_lab(text, title, source_pdf=source_pdf, fallback_iso=fallback_iso)
    if doc_type in ("consultation", "consult"):
        return parse_emias_consult_or_imaging(
            text, title, "consultation", source_pdf=source_pdf, fallback_iso=fallback_iso
        )
    if doc_type == "imaging":
        return parse_emias_consult_or_imaging(
            text, title, "imaging", source_pdf=source_pdf, fallback_iso=fallback_iso
        )
    return parse_emias_consult_or_imaging(
        text, title, doc_type, source_pdf=source_pdf, fallback_iso=fallback_iso
    )


def _configure_patient_dob(corpus: Path) -> None:
    global _skip_patient_dob
    _skip_patient_dob = load_patient_dob(corpus)


def run(
    corpus: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    sources: set[str] | None = None,
) -> dict[str, Any]:
    _configure_patient_dob(corpus)
    manifest = load_manifest(corpus)
    pdfs: list[dict[str, Any]] = list(manifest.get("pdfs") or [])

    structured = 0
    skipped = 0
    errors: list[str] = []
    labs_added_total = 0
    now = _utc_ts()

    for idx, entry in enumerate(pdfs):
        if not _is_target_entry(entry, force=force, sources=sources):
            continue

        source_pdf = entry.get("source_pdf") or ""
        txt_path = _pdf_text_path(corpus, entry)
        if not txt_path.is_file():
            errors.append(f"missing pdf_text: {source_pdf}")
            skipped += 1
            continue

        text = txt_path.read_text(encoding="utf-8").strip()
        if not text or text.startswith("[NO_TEXT_LAYER"):
            errors.append(f"empty text: {source_pdf}")
            skipped += 1
            continue

        try:
            extracted = _parse_entry(text, entry)
        except Exception as exc:
            errors.append(f"parse {source_pdf}: {exc}")
            skipped += 1
            continue

        pdf_path = bot_root() / source_pdf
        sha = _entry_sha(entry, pdf_path)
        section_id = f"local_{Path(source_pdf).stem[:40]}"

        if dry_run:
            structured += 1
            labs_added_total += len(extracted.get("lab_rows") or [])
            continue

        _append_extracted_section_if_new(corpus, section_id, extracted)
        doc_rel = _write_doc_text_md(
            corpus,
            extracted,
            original_filename=Path(source_pdf).name,
            sha256=sha,
            ingest_ts=now,
        )
        labs_added = _append_lab_rows(
            corpus, extracted.get("lab_rows") or [], doc_rel
        )
        labs_added_total += labs_added

        updated = dict(entry)
        updated["structured_locally_at"] = now
        updated["grok_title"] = extracted.get("title_ru") or _entry_title(entry)
        updated["doc_text"] = doc_rel
        if pdf_path.is_file() and not updated.get("sha256"):
            updated["sha256"] = sha
        pdfs[idx] = updated
        structured += 1

    if not dry_run:
        manifest["pdfs"] = pdfs
        meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
        meta["structured_locally_at"] = now
        manifest["meta"] = meta
        write_manifest(corpus, manifest)

    return {
        "structured": structured,
        "skipped": skipped,
        "lab_rows_added": labs_added_total,
        "errors": errors,
        "dry_run": dry_run,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Local PDF structuring for EMIAS/Gemotest/Medsi")
    ap.add_argument(
        "--corpus",
        type=Path,
        default=None,
        help="Path to structured_database",
    )
    ap.add_argument("--dry-run", action="store_true", help="Parse only, do not write")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-process entries that already have structured_locally_at",
    )
    ap.add_argument(
        "--source",
        action="append",
        default=[],
        help="Limit to source_system (emias, gemotest, medsi). Repeatable.",
    )
    args = ap.parse_args()
    if args.corpus is None:
        args.corpus = default_corpus_root()
    corpus = args.corpus.expanduser().resolve()
    if not corpus.is_dir():
        print(f"ERROR: corpus not found: {corpus}", file=sys.stderr)
        return 1

    source_filter = {s.strip().lower() for s in args.source if s.strip()} or None
    stats = run(corpus, dry_run=args.dry_run, force=args.force, sources=source_filter)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    if stats.get("errors"):
        for err in stats["errors"]:
            print(f"WARN: {err}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
