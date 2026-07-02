# biohackbot

Personal medical corpus pipeline: **install → add PDFs → parse → enrich**.

[English](README.md) · [Русский](README.ru.md) · [中文](README.zh-CN.md)

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

> **Not medical advice.** Organizes your documents locally. Does not diagnose or prescribe.

---

## 1. Install

```bash
git clone https://github.com/apodobe/biohackbot.git
cd biohackbot
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .
medbots --help
```

## 2. Configure (first run)

Create a **private** folder for your data (outside this public repo):

```bash
medbots init ~/my-health
```

This creates:

```
~/my-health/
├── bot_config.json
├── sources/emias/      ← drop PDFs here
├── sources/medsi/
├── sources/gemotest/
└── structured_database/
    ├── manifest.json
    ├── PATIENT_PROFILE.json   ← set your DOB
    ├── pdf_text/
    └── doc_text/
```

Edit `PATIENT_PROFILE.json`:

```json
{"dob": "1985-03-20", "full_name_ru": "Your Name"}
```

## 3. Add documents

Copy lab PDFs from EMIAS, Medsi, or Gemotest into the matching `sources/` subfolder.

Register them in the manifest:

```bash
medbots scan --bot-root ~/my-health
# optional: --source emias --source medsi
```

## 4. Parse PDFs

Two steps: extract raw text, then parse into structured `doc_text/` and lab rows.

```bash
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health
# re-parse everything: add --force
# one vendor only: --source emias
```

Supported vendors: **EMIAS**, **Medsi**, **Gemotest** (Russian lab layouts).

### Apple Health (optional)

Export from iPhone: Health app → profile → Export All Health Data → `export.zip`

```bash
medbots import-apple-health --zip ~/Downloads/export.zip --bot-root ~/my-health --copy-zip
medbots validate-apple-health --corpus ~/my-health/structured_database
```

Writes `structured_database/fitness/BODY_METRICS.json`, `WORKOUTS.json`, `APPLE_HEALTH_SUMMARY.md`. Raw `export.xml` is **not** stored — only aggregated JSON.

## 5. Enrich corpus

Normalize labs, apply LOINC map, deduplicate, build indexes:

```bash
medbots pipeline --bot-root ~/my-health
medbots validate --corpus ~/my-health/structured_database
```

Output includes `LABS_NORMALIZED.json`, `DISCREPANCIES.json`, `CORPUS_INDEX.json`, and markdown summaries in `structured_database/`.

## 6. Optional: VPS (text only)

Sync **text + JSON** to a server for a private Q&A bot (no PDF binaries):

```bash
export VPS=root@YOUR_HOST
export CORPUS=~/my-health/structured_database
cd deploy && ./02-rsync-corpus.sh
```

Details: [deploy/RUNBOOK.md](deploy/RUNBOOK.md)

---

## CLI reference

| Command | Purpose |
|---------|---------|
| `medbots init PATH` | Scaffold instance directory |
| `medbots scan --bot-root PATH` | Add new PDFs from `sources/` to manifest |
| `medbots extract-text --bot-root PATH` | PDF → `pdf_text/*.txt` |
| `medbots import-apple-health --zip FILE --bot-root PATH` | Apple Health → `fitness/` |
| `medbots structure --bot-root PATH` | Parse text → `doc_text/`, lab rows |
| `medbots pipeline --bot-root PATH` | Merge labs, LOINC, dedup, index |
| `medbots validate --corpus PATH` | Integrity check |

## Data privacy

- Keep `~/my-health/` **local** or in a **private** git repo.
- Never commit patient data to this public repository.
- See [SECURITY.md](SECURITY.md).

## Docs

- [Corpus file schema](docs/CORPUS.md)
- [License](LICENSE) — MIT, Copyright (c) 2026 Alexey Podobedov

**Author:** [Alexey Podobedov](https://github.com/apodobe)
