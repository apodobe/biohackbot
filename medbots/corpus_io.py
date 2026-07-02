#!/usr/bin/env python3
"""Shared corpus I/O: manifest, labs, patient profile, vendor index."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_SOURCE_TIER = ("medsi", "gemotest", "emias")

# Legacy env names kept for backward compatibility during migration.
_CORPUS_ENV_NAMES = (
    "MEDBOTS_CORPUS_PATH",
    "BIOHACKING_CORPUS_PATH",
    "IRINA_CORPUS_PATH",
    "MEDICAL_CORPUS_PATH",
)


def bot_root() -> Path:
    env = os.environ.get("MEDBOTS_BOT_ROOT", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return Path.cwd().resolve()


def default_corpus_root() -> Path:
    for name in _CORPUS_ENV_NAMES:
        env = os.environ.get(name, "").strip()
        if env:
            return Path(env).expanduser().resolve()
    root = bot_root()
    direct = root / "structured_database"
    if direct.is_dir():
        return direct
    return root / "structured_database"


def resolve_corpus(path: Path | str | None = None) -> Path:
    if path is None:
        return default_corpus_root()
    return Path(path).expanduser().resolve()


def empty_manifest() -> dict[str, Any]:
    return {"version": 1, "pdfs": [], "images": [], "meta": {}}


def load_manifest(corpus: Path) -> dict[str, Any]:
    p = corpus / "manifest.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return empty_manifest()


def write_manifest(corpus: Path, data: dict[str, Any]) -> None:
    (corpus / "manifest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_labs(corpus: Path) -> dict[str, Any]:
    p = corpus / "LABS_NORMALIZED.json"
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"rows": []}


def write_labs(corpus: Path, data: dict[str, Any]) -> None:
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if not text.endswith("\n"):
        text += "\n"
    (corpus / "LABS_NORMALIZED.json").write_text(text, encoding="utf-8")


def load_patient_dob(corpus: Path) -> str:
    """Load owner DOB from PATIENT_PROFILE.json or MEDBOTS_OWNER_DOB env."""
    profile = corpus / "PATIENT_PROFILE.json"
    if profile.exists():
        data = json.loads(profile.read_text(encoding="utf-8"))
        dob = (data.get("dob") or "").strip()
        if dob:
            return dob
    env_dob = os.environ.get("MEDBOTS_OWNER_DOB", "").strip()
    return env_dob


def resolve_owner_dob(repo_or_corpus: Path) -> str:
    """Accept repo root or structured_database path."""
    direct = repo_or_corpus / "PATIENT_PROFILE.json"
    if direct.is_file():
        return load_patient_dob(repo_or_corpus)
    return load_patient_dob(repo_or_corpus / "structured_database")


def manifest_vendor_index(corpus: Path) -> dict[str, str]:
    """Map doc_text / pdf_text basename -> lab source vendor (medsi/gemotest/emias)."""
    index: dict[str, str] = {}
    for entry in load_manifest(corpus).get("pdfs") or []:
        source_pdf = str(entry.get("source_pdf") or "")
        vendor = ""
        for name in _SOURCE_TIER:
            if f"/{name}/" in source_pdf or source_pdf.startswith(f"sources/{name}/"):
                vendor = name
                break
        if not vendor:
            continue
        for field in ("doc_text", "extracted_txt", "source_pdf"):
            rel = str(entry.get(field) or "")
            if not rel:
                continue
            index[Path(rel).name] = vendor
            if field == "source_pdf":
                index[Path(rel).stem] = vendor
    return index
