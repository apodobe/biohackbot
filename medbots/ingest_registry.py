"""Canonical site download and PDF parse registry (verified on corpus)."""
from __future__ import annotations

from dataclasses import dataclass

# Verified: full download (gaps missing_count=0) or complete batch log.
SITE_DOWNLOAD_PARSERS: dict[str, dict[str, str]] = {
    "emias_analyses": {
        "script": "emias_chrome_download_all.py",
        "repo": "Анализы",
        "mode": "--bridge --only-missing",
        "verify": "sources/emias/_gaps.json missing_count=0 (152/152)",
        "status": "canonical",
    },
    "emias_sync": {
        "script": "emias_sync_to_meiramed.py",
        "repo": "Анализы",
        "mode": "post-download dedup + manifest",
        "verify": "irina sources/emias manifest",
        "status": "canonical",
    },
    "medsi_smartmed_api": {
        "script": "Medsi-Documents/download-in-chrome-console.js",
        "repo": "My_biochacking",
        "mode": "Chrome console fetch (logged-in session)",
        "verify": "download-new.log 61/61; 291 PDF on disk",
        "status": "canonical",
    },
    "medsi_import": {
        "script": "import_medsi_manifest.py",
        "repo": "biohackbot / irina-healthbot",
        "mode": "manifest.json → sources/medsi",
        "verify": "205+ medsi PDFs in mymedbot corpus",
        "status": "canonical",
    },
    "gemotest_drop": {
        "script": "import_gemotest.py",
        "repo": "biohackbot",
        "mode": "Гемотест/raw → sources/gemotest",
        "verify": "20 PDF on disk, 9 in corpus",
        "status": "canonical",
    },
    "emias_drop": {
        "script": "import_emias.py",
        "repo": "biohackbot",
        "mode": "EMIAS/ → sources/emias",
        "verify": "62 PDF on disk, 28 in corpus",
        "status": "canonical",
    },
}

# Best PDF text/lab extraction (pytest-covered).
PDF_PARSE_PARSERS: dict[str, dict[str, str]] = {
    "local_structure": {
        "script": "local_structure_pdfs.py",
        "repo": "medbots overlay (per-bot scripts/)",
        "vendors": "medsi, gemotest, emias, emias_inspections, emias_emergency",
        "status": "canonical",
    },
    "merge_labs": {
        "script": "merge_labs_corpus.py",
        "repo": "medbots overlay",
        "status": "canonical",
    },
    "ingest_user_pdfs": {
        "script": "ingest_user_pdfs.py",
        "repo": "biohackbot",
        "note": "uses local_structure._parse_entry, not Grok",
        "status": "canonical",
    },
    "build_corpus_manifest": {
        "script": "build_corpus_manifest.py",
        "repo": "irina-healthbot",
        "status": "canonical",
    },
}

DEPRECATED_PARSERS: dict[str, str] = {
    "emias_api_download_all.py": "emias_chrome_download_all.py --bridge",
    "emias_chrome_download_analyses.py": "emias_chrome_download_all.py --bridge",
    "emias_download_analyses.py": "emias_chrome_download_all.py --bridge",
    "medsi_playwright": "download-all.mjs — token/login failures in download.log",
    "bulk_ingest_medsi.py": "Grok bulk; use local_structure_pdfs + import_medsi_manifest",
    "retry_failed_labs.py": "Grok retry; re-run local_structure_pdfs --force",
}
