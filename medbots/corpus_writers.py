"""Shared corpus writers (doc_text, labs, supplements) — no Grok/LLM."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_date_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_patient_profile(corpus: Path) -> dict[str, Any]:
    profile = corpus / "PATIENT_PROFILE.json"
    if profile.exists():
        return json.loads(profile.read_text(encoding="utf-8"))
    return {}


def _safe_txt_name(relative_posix: str) -> str:
    s = re.sub(r"[^\w\-./]+", "_", relative_posix)
    s = s.replace("/", "__")
    base = s[:200] if len(s) > 200 else s
    return base + ".txt"


def sha256_bytes(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _write_to_extracted_images_md(corpus: Path, section_id: str, extracted: dict[str, Any]) -> None:
    md_path = corpus / "EXTRACTED_FROM_IMAGES.md"
    profile = _load_patient_profile(corpus)
    patient = profile.get("full_name_ru") or "Пациент"
    dob = profile.get("dob") or "не указана"
    block = extracted.get("markdown_block", "").strip()
    date_str = extracted.get("doc_date") or "дата неизвестна"
    if not block:
        block = (
            f"**Тип:** {extracted.get('doc_type', 'other')}\n"
            f"**Дата:** {date_str}\n\n[Текст не извлечён]"
        )
    entry = f"\n---\n\n## {section_id}\n\n{block}\n"
    if md_path.exists():
        md_path.write_text(md_path.read_text(encoding="utf-8").rstrip() + entry, encoding="utf-8")
    else:
        md_path.write_text(
            "# Извлечение из Telegram ingest\n\n"
            f"Пациент: **{patient}**, д.р. **{dob}**.\n"
            + entry.lstrip("\n"),
            encoding="utf-8",
        )


def _doc_text_slug(title_ru: str | None, original_filename: str) -> str:
    base = (title_ru or Path(original_filename).stem).strip()
    slug = re.sub(r"[^\w\-]+", "_", base, flags=re.UNICODE)
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug[:60] or "document"


def _yaml_scalar(value: str) -> str:
    if not value:
        return '""'
    if re.search(r'[:#\[\]{}|>&*!%@`"\']', value) or value.strip() != value:
        return json.dumps(value, ensure_ascii=False)
    return value


def _format_lab_rows_table(lab_rows: list[dict]) -> str:
    if not lab_rows:
        return ""
    lines = [
        "| Показатель | Значение | Ед. | Референс |",
        "|------------|----------|-----|----------|",
    ]
    for row in lab_rows:
        name = row.get("name_ru") or row.get("canonical_key") or "—"
        val = row.get("value")
        val_s = str(val) if val is not None else (row.get("ref_note") or "—")
        unit = row.get("unit") or "—"
        ref_low = row.get("ref_low")
        ref_high = row.get("ref_high")
        if ref_low is not None and ref_high is not None:
            ref = f"{ref_low}–{ref_high}"
        else:
            ref = row.get("ref_note") or "—"
        lines.append(f"| {name} | {val_s} | {unit} | {ref} |")
    return "\n".join(lines)


def _write_doc_text_md(
    corpus: Path,
    extracted: dict[str, Any],
    *,
    original_filename: str,
    sha256: str,
    ingest_ts: str,
) -> str:
    doc_date = extracted.get("doc_date") or _utc_date_slug()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(doc_date)):
        doc_date = _utc_date_slug()
    title = extracted.get("title_ru") or Path(original_filename).stem
    doc_type = extracted.get("doc_type") or "other"
    conclusion = (extracted.get("conclusion_ru") or "").strip() or "—"
    details = (extracted.get("markdown_block") or "").strip() or "—"
    lab_rows = extracted.get("lab_rows") or []
    lab_table = _format_lab_rows_table(lab_rows)

    slug = _doc_text_slug(extracted.get("title_ru"), original_filename)
    rel_path = f"doc_text/{doc_date}_{slug}.md"
    md_path = corpus / rel_path
    md_path.parent.mkdir(parents=True, exist_ok=True)

    frontmatter = (
        f"---\n"
        f"date: {doc_date}\n"
        f"title: {_yaml_scalar(str(title))}\n"
        f"type: {doc_type}\n"
        f"source_file: {_yaml_scalar(original_filename)}\n"
        f"sha256: {sha256[:12]}\n"
        f"ingest_ts: {ingest_ts}\n"
        f"---\n"
    )
    body_parts = [
        frontmatter,
        "",
        "## Заключение",
        "",
        conclusion,
        "",
        "## Детали",
        "",
        details,
    ]
    if lab_table:
        body_parts.extend(["", "## Лабораторные показатели", "", lab_table])
    md_path.write_text("\n".join(body_parts).rstrip() + "\n", encoding="utf-8")
    return rel_path


def _append_lab_rows(corpus: Path, lab_rows: list[dict], source_path_rel: str) -> int:
    if not lab_rows:
        return 0
    labs_path = corpus / "LABS_NORMALIZED.json"
    if labs_path.exists():
        labs = json.loads(labs_path.read_text(encoding="utf-8"))
    else:
        labs = {"rows": []}
    existing_rows: list[dict] = list(labs.get("rows") or [])
    existing_keys = {
        (r.get("canonical_key", ""), r.get("specimen_date", ""))
        for r in existing_rows
    }
    added = 0
    for row in lab_rows:
        row = dict(row)
        row["source_path"] = source_path_rel
        key = (row.get("canonical_key", ""), row.get("specimen_date", ""))
        if key in existing_keys:
            continue
        existing_rows.append(row)
        existing_keys.add(key)
        added += 1
    labs["rows"] = existing_rows
    labs_path.write_text(json.dumps(labs, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def _append_supplement_mentions(corpus: Path, mentions: list[dict], source_path_rel: str) -> int:
    if not mentions:
        return 0
    sup_path = corpus / "supplements" / "SUPPLEMENTS.json"
    if sup_path.exists():
        data = json.loads(sup_path.read_text(encoding="utf-8"))
    else:
        data = {"version": 1, "regimen": [], "intake_log": []}
    regimen: list[dict] = list(data.get("regimen") or [])
    existing = {(r.get("name_ru", ""), r.get("dose", "")) for r in regimen}
    added = 0
    for m in mentions:
        name = (m.get("name_ru") or "").strip()
        if not name:
            continue
        dose = m.get("dose")
        key = (name, dose or "")
        if key in existing:
            continue
        regimen.append(
            {
                "name_ru": name,
                "dose": dose,
                "schedule": m.get("schedule"),
                "source_path": source_path_rel,
                "context": m.get("context"),
                "status": "mentioned_in_document",
            }
        )
        existing.add(key)
        added += 1
    data["regimen"] = regimen
    sup_path.parent.mkdir(parents=True, exist_ok=True)
    sup_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return added
