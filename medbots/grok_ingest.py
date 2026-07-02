#!/usr/bin/env python3
"""
Grok/Telegram PDF and image ingest into structured_database (shared medbots-core).
Uses xAI Grok (OpenAI-compatible API) for extraction (no pytesseract).

Flow:
  PDF with text layer  → PyMuPDF text     → Grok chat (text)   → JSON
  Scan PDF (no text)   → PyMuPDF pixmaps  → Grok vision        → JSON
  Photo/image          → raw bytes         → Grok vision        → JSON

Env: XAI_API_KEY (or GROK_API_KEY), optional INGEST_LLM_BASE_URL (default https://api.x.ai/v1),
     INGEST_LLM_MODEL (default grok-4-1-fast-reasoning — Thinking/reasoning, vision; xAI fast tier).

JSON response fields written to:
  markdown_block  → EXTRACTED_FROM_IMAGES.md + doc_text/*.md
  lab_rows        → LABS_NORMALIZED.json (appended)
  metadata        → manifest.json
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None  # type: ignore


from medbots.corpus_io import load_manifest, load_patient_dob, write_manifest
from medbots.corpus_writers import (  # noqa: E402
    _append_lab_rows,
    _append_supplement_mentions,
    _safe_txt_name,
    _write_doc_text_md,
    _write_to_extracted_images_md,
    sha256_bytes,
)


# ─────────────────────────────── helpers ────────────────────────────────────

def _utc_date_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_manifest(corpus: Path) -> dict[str, Any]:
    return load_manifest(corpus)


def _write_manifest(corpus: Path, data: dict[str, Any]) -> None:
    write_manifest(corpus, data)


def _utc_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_ingest_state(corpus: Path) -> dict[str, Any]:
    p = corpus / "ingest_state.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"sha256": []}


def _save_ingest_state(corpus: Path, state: dict[str, Any]) -> None:
    (corpus / "ingest_state.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _known_hashes(manifest: dict[str, Any], state: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for e in (manifest.get("pdfs") or []) + (manifest.get("images") or []):
        h = e.get("sha256") or ""
        if isinstance(h, str) and len(h) == 64:
            out.add(h.lower())
    for h in state.get("sha256") or []:
        if isinstance(h, str):
            out.add(h.lower().removeprefix("img:"))
    return out


# ─────────────────────────── PDF text helpers ────────────────────────────────

def _extract_pdf_text(data: bytes) -> tuple[str, int]:
    """Return (full_text, pages_with_text). Requires fitz."""
    doc = fitz.open(stream=data, filetype="pdf")
    try:
        parts: list[str] = []
        for i, page in enumerate(doc):
            t = (page.get_text("text") or "").strip()
            if t:
                parts.append(f"--- page {i + 1} ---\n{t}")
        full = "\n\n".join(parts).strip()
        return full, len(parts)
    finally:
        doc.close()


def _pdf_page_images(data: bytes, dpi: int = 150) -> list[bytes]:
    """Render each page to PNG bytes (for scan PDFs sent to Vision)."""
    doc = fitz.open(stream=data, filetype="pdf")
    out: list[bytes] = []
    try:
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        for page in doc:
            pix = page.get_pixmap(matrix=mat, alpha=False)
            out.append(pix.tobytes("png"))
    finally:
        doc.close()
    return out


# ─────────────────────────── Grok (xAI) extraction ─────────────────────────

def _load_patient_profile(corpus: Path) -> dict[str, Any]:
    p = corpus / "PATIENT_PROFILE.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"full_name_ru": "Пациент", "dob": load_patient_dob(corpus)}


def _load_system_prompt() -> str:
    p = Path(__file__).parent / "biohack_ingest_extract_prompt.txt"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    return (
        "Extract the medical document and return JSON with fields: "
        "doc_date, doc_type, title_ru, institution, doctor, conclusion_ru, "
        "markdown_block, lab_rows, supplement_mentions. Follow biohack_ingest_extract_prompt.txt."
    )


def _xai_client(api_key: str, base_url: str):
    from openai import OpenAI

    return OpenAI(api_key=api_key, base_url=base_url.rstrip("/"))


def _extract_json_object(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        return raw[start : end + 1]
    return raw


def _parse_json_llm_output(raw: str) -> dict[str, Any]:
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\n?```\s*$", "", raw)
    last_err: json.JSONDecodeError | None = None
    for cand in (raw, _extract_json_object(raw)):
        if not cand.strip():
            continue
        try:
            return json.loads(cand)
        except json.JSONDecodeError as e:
            last_err = e
    if last_err is not None:
        raise last_err
    raise json.JSONDecodeError("empty LLM output", raw, 0)


_LAB_SYSTEM_SUFFIX = (
    "\n\nLAB CBC / large panel: keep markdown_block concise (≤1500 chars). "
    "Put every analyte with numeric value into lab_rows. "
    "Return one complete valid JSON object — do not truncate mid-string."
)


def _call_grok_text(
    text: str,
    api_key: str,
    model: str,
    base_url: str,
    *,
    max_tokens: int = 4096,
    lab_mode: bool = False,
) -> dict[str, Any]:
    """Send extracted PDF text to Grok for structuring."""
    client = _xai_client(api_key, base_url)
    sys_prompt = _load_system_prompt()
    if lab_mode:
        sys_prompt += _LAB_SYSTEM_SUFFIX
    user_msg = (
        "Extracted text from a medical PDF (plain text, may have formatting artefacts):\n\n"
        + text[:80_000]
    )
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.1,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    return _parse_json_llm_output(raw)


def _call_grok_vision(
    images_b64: list[tuple[str, str]],
    api_key: str,
    model: str,
    base_url: str,
    *,
    max_tokens: int = 4096,
    lab_mode: bool = False,
) -> dict[str, Any]:
    """
    images_b64: (media_type, base64_data) per image. Max ~10 pages for cost/latency.
    """
    client = _xai_client(api_key, base_url)
    sys_prompt = _load_system_prompt()
    if lab_mode:
        sys_prompt += _LAB_SYSTEM_SUFFIX
    user_parts: list[dict[str, Any]] = []
    for mime, b64 in images_b64[:10]:
        data_url = f"data:{mime};base64,{b64}"
        user_parts.append(
            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}}
        )
    user_parts.append({"type": "text", "text": "Extract the medical document shown above. Return JSON only."})
    resp = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0.1,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_parts},
        ],
    )
    raw = (resp.choices[0].message.content or "").strip()
    return _parse_json_llm_output(raw)


def _extract_with_grok(
    *,
    pdf_data: bytes | None = None,
    image_bytes: bytes | None = None,
    image_mime: str = "image/jpeg",
    api_key: str,
    model: str,
    base_url: str,
    max_tokens: int = 4096,
    lab_mode: bool = False,
) -> dict[str, Any]:
    """Route to text or vision call depending on input type."""
    if image_bytes is not None:
        b64 = base64.standard_b64encode(image_bytes).decode()
        return _call_grok_vision(
            [(image_mime, b64)], api_key, model, base_url, max_tokens=max_tokens, lab_mode=lab_mode
        )

    if pdf_data is not None:
        if fitz is None:
            raise RuntimeError("PyMuPDF not installed")
        text, text_pages = _extract_pdf_text(pdf_data)
        total_pages = fitz.open(stream=pdf_data, filetype="pdf").page_count
        is_scan = text_pages == 0 or (text_pages / max(total_pages, 1)) < 0.3

        if is_scan:
            imgs = _pdf_page_images(pdf_data)
            pairs = [("image/png", base64.standard_b64encode(img).decode()) for img in imgs]
            return _call_grok_vision(
                pairs, api_key, model, base_url, max_tokens=max_tokens, lab_mode=lab_mode
            )
        return _call_grok_text(text, api_key, model, base_url, max_tokens=max_tokens, lab_mode=lab_mode)

    raise ValueError("Provide either pdf_data or image_bytes")


def _ingest_api_key() -> str:
    return (
        os.environ.get("XAI_API_KEY", "").strip()
        or os.environ.get("GROK_API_KEY", "").strip()
    )


def _ingest_base_url() -> str:
    return os.environ.get("INGEST_LLM_BASE_URL", "https://api.x.ai/v1").strip().rstrip("/")


def _ingest_default_model() -> str:
    return os.environ.get("INGEST_LLM_MODEL", "grok-4-1-fast-reasoning").strip()


def _git_push_after_ingest(corpus: Path, rel_source: str) -> None:
    import subprocess

    repo_root = corpus.parent
    result = subprocess.run(
        ["git", "-C", str(repo_root), "add", "structured_database/"],
        capture_output=True,
    )
    if result.returncode == 0:
        msg = f"ingest: {rel_source}"
        subprocess.run(
            ["git", "-C", str(repo_root), "commit", "-m", msg],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_root), "pull", "--rebase", "--autostash", "origin", "main"],
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_root), "push", "origin", "main"],
            capture_output=True,
        )

# ───────────────────────────── public API ────────────────────────────────────

from dataclasses import dataclass, field


@dataclass
class IngestResult:
    status: str  # added | duplicate | error
    detail: str
    source_path: str | None = None
    sha256: str | None = None
    doc_type: str | None = None
    doc_date: str | None = None
    title_ru: str | None = None
    conclusion_ru: str | None = None
    lab_rows_added: int = 0
    extraction: dict = field(default_factory=dict)


def _ingest_core(
    corpus: Path,
    data: bytes,
    *,
    original_filename: str,
    save_subdir: str,
    is_image: bool,
    image_mime: str = "image/jpeg",
    api_key: str,
    model: str,
    base_url: str,
    git_push: bool = False,
) -> IngestResult:
    h = sha256_bytes(data)
    manifest = _load_manifest(corpus)
    state = _load_ingest_state(corpus)
    known = _known_hashes(manifest, state)
    if h.lower() in known:
        return IngestResult(status="duplicate", detail="Этот файл уже есть в базе.", sha256=h)

    section_id = f"telegram_{_utc_date_slug()}_{h[:10]}"
    rel_source = ""
    raw_path: Path | None = None
    if is_image:
        ingest_dir = corpus / "telegram_ingest"
        ingest_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^\w.\-]+", "_", Path(original_filename).stem)[:60] or "file"
        ext = Path(original_filename).suffix.lower() or ".jpg"
        fname = f"{_utc_date_slug()}_{h[:10]}_{stem}{ext}"
        raw_path = ingest_dir / fname
        raw_path.write_bytes(data)
        rel_source = f"telegram_ingest/{fname}"

    try:
        if is_image:
            extracted = _extract_with_grok(
                image_bytes=data,
                image_mime=image_mime,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )
        else:
            extracted = _extract_with_grok(
                pdf_data=data,
                api_key=api_key,
                model=model,
                base_url=base_url,
            )
    except Exception as e:
        if raw_path is not None:
            raw_path.unlink(missing_ok=True)
        return IngestResult(status="error", detail=f"Ошибка извлечения Grok (xAI): {e}", sha256=h)

    # Write markdown section
    _write_to_extracted_images_md(corpus, section_id, extracted)

    now = _utc_ts()
    doc_rel = _write_doc_text_md(
        corpus,
        extracted,
        original_filename=original_filename,
        sha256=h,
        ingest_ts=now,
    )

    # Write pdf_text/ for PDFs (raw PDF is not stored — only extracted text)
    extracted_txt_rel: str | None = None
    if not is_image and fitz is not None:
        try:
            raw_text, _ = _extract_pdf_text(data)
            txt_name = _safe_txt_name(original_filename)
            txt_dir = corpus / "pdf_text"
            txt_dir.mkdir(exist_ok=True)
            (txt_dir / txt_name).write_text(raw_text, encoding="utf-8")
            extracted_txt_rel = f"pdf_text/{txt_name}"
        except Exception:
            pass

    if is_image:
        source_ref = f"EXTRACTED_FROM_IMAGES.md#{section_id}"
    else:
        rel_source = doc_rel
        source_ref = doc_rel
    labs_added = _append_lab_rows(
        corpus,
        extracted.get("lab_rows") or [],
        source_ref,
    )
    sup_added = _append_supplement_mentions(
        corpus,
        extracted.get("supplement_mentions") or [],
        source_ref,
    )

    # Update manifest
    if is_image:
        images = list(manifest.get("images") or [])
        images.append({
            "source": rel_source,
            "extracted_markdown_section": f"EXTRACTED_FROM_IMAGES.md#{section_id}",
            "topic": extracted.get("title_ru") or "Telegram ingest",
            "sha256": h,
            "ingested_at": now,
        })
        manifest["images"] = images
        meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
        meta["image_count"] = len(images)
    else:
        pdfs = list(manifest.get("pdfs") or [])
        entry: dict[str, Any] = {
            "source_pdf": Path(original_filename).name,
            "doc_text": doc_rel,
            "sha256": h,
            "ingested_at": now,
            "ingest_note": "telegram_ingest bot; pdf not stored",
        }
        if extracted_txt_rel:
            txt_path = corpus / extracted_txt_rel
            entry["extracted_txt"] = extracted_txt_rel
            entry["chars"] = len(txt_path.read_text(encoding="utf-8")) if txt_path.exists() else 0
            entry["pages_hint"] = entry.get("chars", 0) // 2000
        pdfs.append(entry)
        manifest["pdfs"] = pdfs
        meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
        meta["pdf_count"] = len(pdfs)
    meta["built"] = _utc_date_slug()
    manifest["meta"] = meta
    _write_manifest(corpus, manifest)

    state.setdefault("sha256", []).append(h)
    _save_ingest_state(corpus, state)

    try:
        from reconcile_goals import reconcile_after_ingest

        reconcile_after_ingest(
            corpus,
            rel_source=rel_source,
            title_ru=extracted.get("title_ru"),
            conclusion_ru=extracted.get("conclusion_ru"),
            apply=True,
        )
    except Exception:
        pass

    if git_push:
        _git_push_after_ingest(corpus, rel_source)

    return IngestResult(
        status="added",
        detail="Добавлено в корпус.",
        source_path=rel_source,
        sha256=h,
        doc_type=extracted.get("doc_type"),
        doc_date=extracted.get("doc_date"),
        title_ru=extracted.get("title_ru"),
        conclusion_ru=extracted.get("conclusion_ru"),
        lab_rows_added=labs_added,
        extraction=extracted,
    )


def ingest_pdf_bulk_path(
    corpus: Path,
    pdf_path: Path,
    *,
    rel_source: str,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> IngestResult:
    """Grok-структурирование существующего PDF из sources/medsi без дубля manifest."""
    if fitz is None:
        return IngestResult(status="error", detail="PyMuPDF не установлен.")
    key = (api_key or "").strip() or _ingest_api_key()
    mdl = (model or "").strip() or _ingest_default_model()
    burl = (base_url or "").strip() or _ingest_base_url()
    if not key:
        return IngestResult(status="error", detail="XAI_API_KEY (или GROK_API_KEY) не задан.")

    data = pdf_path.read_bytes()
    h = sha256_bytes(data)
    manifest = _load_manifest(corpus)
    state = _load_ingest_state(corpus)

    for entry in manifest.get("pdfs") or []:
        if entry.get("source_pdf") == rel_source and entry.get("grok_ingested_at"):
            return IngestResult(status="duplicate", detail="Уже обработан Grok.", sha256=h)

    section_id = f"bulk_{Path(rel_source).stem[:40]}"
    is_lab = "анализ_крови" in rel_source.lower() or "клинический_анализ" in rel_source.lower()
    token_steps = (16384, 24576) if is_lab else (4096, 8192)
    extracted: dict[str, Any] | None = None
    last_err: Exception | None = None
    for max_tokens in token_steps:
        try:
            extracted = _extract_with_grok(
                pdf_data=data,
                api_key=key,
                model=mdl,
                base_url=burl,
                max_tokens=max_tokens,
                lab_mode=is_lab,
            )
            break
        except Exception as e:
            last_err = e
    if extracted is None:
        return IngestResult(status="error", detail=f"Ошибка Grok: {last_err}", sha256=h)

    _write_to_extracted_images_md(corpus, section_id, extracted)
    now = _utc_ts()
    doc_rel = _write_doc_text_md(
        corpus,
        extracted,
        original_filename=pdf_path.name,
        sha256=h,
        ingest_ts=now,
    )
    source_ref = doc_rel
    labs_added = _append_lab_rows(corpus, extracted.get("lab_rows") or [], source_ref)
    _append_supplement_mentions(corpus, extracted.get("supplement_mentions") or [], source_ref)

    updated = False
    for i, entry in enumerate(manifest.get("pdfs") or []):
        if entry.get("source_pdf") == rel_source:
            entry = dict(entry)
            entry["sha256"] = h
            entry["grok_ingested_at"] = now
            entry["grok_title"] = extracted.get("title_ru")
            entry["doc_text"] = doc_rel
            manifest["pdfs"][i] = entry
            updated = True
            break
    if not updated:
        pdfs = list(manifest.get("pdfs") or [])
        pdfs.append({
            "source_pdf": rel_source,
            "sha256": h,
            "grok_ingested_at": now,
            "ingest_note": "bulk ingest",
        })
        manifest["pdfs"] = pdfs

    meta = manifest.get("meta") if isinstance(manifest.get("meta"), dict) else {}
    meta["built"] = _utc_date_slug()
    manifest["meta"] = meta
    _write_manifest(corpus, manifest)

    if h.lower() not in {x.lower() for x in state.get("sha256") or []}:
        state.setdefault("sha256", []).append(h)
        _save_ingest_state(corpus, state)

    try:
        from reconcile_goals import reconcile_after_ingest

        reconcile_after_ingest(
            corpus,
            rel_source=rel_source,
            title_ru=extracted.get("title_ru"),
            conclusion_ru=extracted.get("conclusion_ru"),
            apply=True,
        )
    except Exception:
        pass

    return IngestResult(
        status="added",
        detail="Bulk ingest OK.",
        source_path=rel_source,
        sha256=h,
        doc_type=extracted.get("doc_type"),
        doc_date=extracted.get("doc_date"),
        title_ru=extracted.get("title_ru"),
        conclusion_ru=extracted.get("conclusion_ru"),
        lab_rows_added=labs_added,
        extraction=extracted,
    )


def ingest_file(
    corpus: Path,
    data: bytes,
    *,
    original_filename: str,
    is_image: bool = False,
    image_mime: str = "image/jpeg",
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    git_push: bool = False,
) -> IngestResult:
    if is_image:
        return ingest_image_bytes(
            corpus,
            data,
            original_filename=original_filename,
            image_mime=image_mime,
            api_key=api_key,
            model=model,
            base_url=base_url,
            git_push=git_push,
        )
    return ingest_pdf_bytes(
        corpus,
        data,
        original_filename=original_filename,
        api_key=api_key,
        model=model,
        base_url=base_url,
        git_push=git_push,
    )


def ingest_pdf_bytes(
    corpus: Path,
    data: bytes,
    *,
    original_filename: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    git_push: bool = False,
) -> IngestResult:
    if fitz is None:
        return IngestResult(status="error", detail="PyMuPDF не установлен.")
    key = (api_key or "").strip() or _ingest_api_key()
    mdl = (model or "").strip() or _ingest_default_model()
    burl = (base_url or "").strip() or _ingest_base_url()
    if not key:
        return IngestResult(
            status="error",
            detail="XAI_API_KEY (или GROK_API_KEY) не задан.",
        )
    return _ingest_core(
        corpus,
        data,
        original_filename=original_filename or "document.pdf",
        save_subdir="telegram_ingest",
        is_image=False,
        api_key=key,
        model=mdl,
        base_url=burl,
        git_push=git_push,
    )


def ingest_image_bytes(
    corpus: Path,
    data: bytes,
    *,
    original_filename: str | None = None,
    image_mime: str = "image/jpeg",
    api_key: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
    git_push: bool = False,
) -> IngestResult:
    key = (api_key or "").strip() or _ingest_api_key()
    mdl = (model or "").strip() or _ingest_default_model()
    burl = (base_url or "").strip() or _ingest_base_url()
    if not key:
        return IngestResult(
            status="error",
            detail="XAI_API_KEY (или GROK_API_KEY) не задан.",
        )
    return _ingest_core(
        corpus,
        data,
        original_filename=original_filename or "photo.jpg",
        save_subdir="telegram_ingest",
        is_image=True,
        image_mime=image_mime,
        api_key=key,
        model=mdl,
        base_url=burl,
        git_push=git_push,
    )


# ─────────────────────────────── self-test ───────────────────────────────────

def _self_test() -> None:
    import tempfile

    if fitz is None:
        print("SKIP: PyMuPDF not installed", file=sys.stderr)
        return

    # Build a minimal synthetic PDF with text
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Лейкоциты 6.5 10^9/L (реф. 4-9). Дата: 10.04.2026.")
    pdf_bytes = doc.tobytes()
    doc.close()

    # Minimal 1×1 PNG
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xdb\x00\x00\x00\x00IEND\xaeB`\x82"
    )

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "pdf_text").mkdir()
        man = {"version": 1, "pdfs": [], "images": [], "meta": {"built": "2000-01-01", "pdf_count": 0}}
        (root / "manifest.json").write_text(json.dumps(man), encoding="utf-8")

        # Dedupe test without API (no api_key → error, but sha256 path)
        r_no_key = ingest_pdf_bytes(root, pdf_bytes, original_filename="test.pdf", api_key="")
        assert r_no_key.status == "error" and "XAI_API_KEY" in r_no_key.detail, r_no_key

        # Direct dedupe via manifest injection
        h = sha256_bytes(pdf_bytes)
        man2 = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        man2["pdfs"].append({"source_pdf": "fake.pdf", "sha256": h})
        (root / "manifest.json").write_text(json.dumps(man2), encoding="utf-8")
        r_dup = ingest_pdf_bytes(root, pdf_bytes, original_filename="dup.pdf", api_key="dummy")
        assert r_dup.status == "duplicate", r_dup

        # Image dedupe
        h2 = sha256_bytes(png)
        man3 = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        man3["images"].append({"source": "fake.png", "sha256": h2})
        (root / "manifest.json").write_text(json.dumps(man3), encoding="utf-8")
        r_idup = ingest_image_bytes(root, png, original_filename="x.png", api_key="dummy")
        assert r_idup.status == "duplicate", r_idup

    print("biohack_ingest_lib self-test OK", file=sys.stderr)


if __name__ == "__main__":
    _self_test()
