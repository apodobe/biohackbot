# Medical bots — unified corpus standard

Schema for personal medical / biohacking bots built on **medbots-core** (this repo).

## Repository roles

| Repo | Visibility | Contents |
|------|------------|----------|
| **biohackbot** (this) | Public | `medbots` package, docs, deploy templates, tests |
| **Your instance** | Private / local | `structured_database/`, `bot_config.json`, `sources/`, ingest scripts |

## Data policy

| Layer | Where | Public git | VPS | Content |
|-------|-------|------------|-----|---------|
| **sources/** | Mac only | never | never | Raw PDF, vendor drops |
| **structured_database/** | Mac (+ private git) | **never in public repo** | rsync text only | `pdf_text/`, `doc_text/`, JSON, prompts |
| **deploy/** | public repo | yes | copy on deploy | rsync scripts, OpenClaw skills |

**Rule:** PDF binaries never on VPS. AI reads text layers only.

## Repository layout (private instance)

```
{your-instance}/
├── sources/                    # canonical PDF (gitignored or private repo)
│   ├── medsi/
│   ├── emias/
│   └── …/manifest.json
├── structured_database/        # prepared corpus (see below)
├── bot_config.json             # feature flags (private)
└── deploy/                     # optional copy from public biohackbot
```

## structured_database/ — required files

| File | Purpose |
|------|---------|
| `PROMPT_AGENT_EN.md` | Full bot rules (EN); replies **Russian** |
| `AI_SYSTEM_BRIEF_EN.md` | Ultra-short rules for VPS sessions |
| `AI_PREP_README.md` | Pointer for humans/AI |
| `README_FOR_OPUS.md` | File map (RU table) |
| `PROMPT_OPUS_RU.md` / `PROMPT_OPUS_EN.md` | Opus orchestration |
| `CORPUS_INDEX.json` | Nav: counts, read order, `prompt_files` |
| `manifest.json` | Master PDF index → `pdf_text/`, `doc_text/` |
| `TIMELINE_EVENTS.json` | Chronology + `sources` |
| `LABS_NORMALIZED.json` | Normalized lab rows |
| `DISCREPANCIES.json` | Conflicts, stale imaging, gaps |
| `PATIENT_PROFILE.json` | Owner DOB / display name (private) |
| `pdf_text/*.txt` | PyMuPDF extract |
| `doc_text/*.md` | Structured docs (YAML frontmatter) |
| `labs/LOINC_MAP.tsv` | canonical_key → LOINC |

Optional modules: `GOALS_REMINDERS.json`, `genomics/`, `nutrition/`, `fitness/`, `recommendations/`.

## manifest.json entry schema

```json
{
  "source_pdf": "sources/emias/2020-01-23__Title__abc12345.pdf",
  "source_system": "emias|medsi|gemotest",
  "doc_type": "lab|consultation|imaging|functional|other",
  "created_at": "ISO-8601",
  "extracted_txt": "pdf_text/….txt",
  "doc_text": "doc_text/….md",
  "structured_locally_at": "ISO-8601"
}
```

## Pipeline

Shared engine: **`medbots`** CLI from this repo. Corpus path: **`MEDBOTS_CORPUS_PATH`**. Feature flags: **`bot_config.json`** + env `MEDBOTS_FEATURE_<FLAG>=0|1`.

```bash
medbots pipeline --bot-root /path/to/your-instance
```

Phase 1: vendor import scripts (private instance) → `sources/` + `manifest.json`  
Phase 2: extract PDF text → `local_structure_pdfs` → `run_corpus_pipeline` / `medbots pipeline`

## AI read order

1. `AI_SYSTEM_BRIEF_EN.md` or `PROMPT_AGENT_EN.md`
2. `CORPUS_INDEX.json`
3. `DISCREPANCIES.json`
4. `LABS_NORMALIZED.json` (+ optional summary JSON)
5. `TIMELINE_EVENTS.json`
6. `doc_text/`, `pdf_text/` on demand

**Mandatory:** first reply line `Источники: …` with corpus paths.

Updated: 2026-07-03.
