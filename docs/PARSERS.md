# Parser guide

How to ingest medical PDFs and Apple Health data into your private instance.

**Instance root** below is `~/my-health/` (created with `medbots init`). All paths are relative to it unless noted.

---

## End-to-end workflow

```
sources/*.pdf  ──scan──►  manifest.json
                ──extract-text──►  pdf_text/*.txt
                ──structure──►  doc_text/*.md + labs/*.jsonl
                ──pipeline──►  LABS_NORMALIZED.json, CORPUS_INDEX.json, …

export.zip  ──import-apple-health──►  fitness/*.json
```

Recommended order for PDFs:

```bash
medbots scan --bot-root ~/my-health
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health
medbots pipeline --bot-root ~/my-health
medbots validate --corpus ~/my-health/structured_database
```

Apple Health is **optional** and **separate** — run anytime after `init`:

```bash
medbots import-apple-health --zip ~/Downloads/export.zip --bot-root ~/my-health --copy-zip
medbots validate-apple-health --corpus ~/my-health/structured_database
```

---

## Before you parse

1. **Create instance:** `medbots init ~/my-health`
2. **Set date of birth** in `structured_database/PATIENT_PROFILE.json` — used for age-based reference ranges and Apple Health quality checks:

   ```json
   {"dob": "1985-06-15", "full_name_ru": "John Smith", "country": "USA"}
   ```

3. **Copy source files** into the right folder (see vendor sections below).
4. **Do not edit `manifest.json` by hand** unless you know what you are doing — use `medbots scan`.

---

## 1. Scan — register PDFs

**Command:** `medbots scan --bot-root ~/my-health`

**What it does:** Walks `sources/emias/`, `sources/medsi/`, `sources/gemotest/`, computes SHA-256, appends new entries to `manifest.json`. Skips duplicates (same path or hash).

**Options:**

| Flag | Description |
|------|-------------|
| `--source emias` | Only scan one vendor (repeatable) |
| `--corpus PATH` | Override `structured_database/` location |

**Examples:**

```bash
# All vendors
medbots scan --bot-root ~/my-health

# Only new Gemotest files
medbots scan --bot-root ~/my-health --source gemotest
```

**Output:** Updated `structured_database/manifest.json` with fields like `source_pdf`, `source_system`, `doc_type`, `sha256`.

---

## 2. Extract text — PDF → plain text

**Command:** `medbots extract-text --bot-root ~/my-health`

**What it does:** For every PDF in `manifest.json`, extracts the **text layer** with PyMuPDF into `structured_database/pdf_text/*.txt`. Updates manifest with `extracted_txt`, `chars`, `pages_hint`.

**Requirements:**

- PDF must exist at `{bot-root}/{source_pdf}` from manifest.
- Scanned PDFs **without a text layer** get a placeholder: `[NO_TEXT_LAYER: scanned PDF — OCR not included in this tool]`. Those files will fail at `structure` until you add OCR externally or replace with text-based PDFs.

**Re-run:** Safe to re-run; overwrites `pdf_text/` files and refreshes manifest fields.

---

## 3. Structure — vendor PDF parsers

**Command:** `medbots structure --bot-root ~/my-health`

**What it does:** Reads `pdf_text/`, picks a parser by `source_system` and `doc_type`, writes:

- `structured_database/doc_text/YYYY-MM-DD_<type>.md` — document with YAML frontmatter
- Appends normalized lab rows to `structured_database/labs/` (JSONL sections)
- Sets `structured_locally_at`, `doc_text`, `grok_title` on manifest entries

**Options:**

| Flag | Description |
|------|-------------|
| `--force` | Re-parse entries that already have `structured_locally_at` |
| `--dry-run` | Parse only, no writes |
| `--source emias` | Limit to one vendor (repeatable) |

**Examples:**

```bash
# Parse all pending PDFs
medbots structure --bot-root ~/my-health

# Re-parse only Medsi after fixing PDFs
medbots structure --bot-root ~/my-health --source medsi --force

# Test parser output without writing
medbots structure --bot-root ~/my-health --source gemotest --dry-run
```

### 3.1 EMIAS (`sources/emias/`)

**Layout:** Flat folder of PDFs from the Moscow EMIAS portal.

```bash
cp ~/Downloads/emias_*.pdf ~/my-health/sources/emias/
medbots scan --bot-root ~/my-health --source emias
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health --source emias
```

**Supported document types** (auto-detected from text and manifest `doc_type`):

| Type | Parser | Output |
|------|--------|--------|
| Lab | `parse_emias_lab` | Lab table in markdown + `lab_rows` (COVID IgG/IgM, PCR qualitative, some Medsi-format blocks embedded in EMIAS exports) |
| Consultation | `parse_emias_consult_or_imaging` | Diagnosis, conclusion, recommendations |
| Imaging / functional | `parse_emias_consult_or_imaging` | Study description and conclusion |

**Tips:**

- Filename stem becomes the default title if no vendor title is set.
- For lab PDFs, ensure `PATIENT_PROFILE.json` has correct `dob` — some reference logic depends on it.
- After `structure`, run `medbots pipeline` to merge rows into `LABS_NORMALIZED.json`.

### 3.2 Medsi (`sources/medsi/`)

**Layout:** Recursive — subfolders allowed (e.g. by clinic or year).

```bash
cp -r ~/Downloads/medsi_reports/*.pdf ~/my-health/sources/medsi/2024/
medbots scan --bot-root ~/my-health --source medsi
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health --source medsi
```

**Routing:**

| Content | Parser |
|---------|--------|
| Blood/biochemistry labs (`doc_type: lab`, or title contains «анализ крови», «биохим») | `parse_medsi_lab` — row layout `Исследование - (L…)` |
| ECG, echo | `parse_emias_consult_or_imaging` (functional) |
| Ultrasound, duplex | `parse_emias_consult_or_imaging` (imaging) |
| Other visits | `parse_emias_consult_or_imaging` (consultation) |

**Note:** Only entries from `sources/medsi/` **or** with `user_drop_batch` / `ingest_note: ALL-NEW-FILES drop` are structured by default. Normal Medsi manifest entries from `scan` are processed.

### 3.3 Gemotest (`sources/gemotest/`)

**Layout:** Flat or nested PDFs from Gemotest lab.

```bash
cp ~/Downloads/gemotest_*.pdf ~/my-health/sources/gemotest/
medbots scan --bot-root ~/my-health --source gemotest
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health --source gemotest
```

**Supported lab layouts** (chosen automatically from PDF text):

| Layout | When used |
|--------|-----------|
| Numeric blocks | Standard result + reference lines |
| Quad table | Four-column table with «Показатель / Результат / Ед. / Референсные значения» |
| Coprogram | Stool analysis rows |
| Qualitative table | Positive/negative results without numeric values |

**Detection:** If text contains «Показатель» and «Референсные значения», Gemotest quad-table parser is preferred even for legacy flat paths.

---

## 4. Apple Health import

**Command:**

```bash
medbots import-apple-health \
  --zip ~/Downloads/export.zip \
  --bot-root ~/my-health \
  --copy-zip
```

**Getting the export (iPhone):**

1. Open **Health** → tap profile photo → **Export All Health Data**
2. Save `export.zip` (AirDrop to Mac, Files, etc.)
3. Run import command above

**What it does:**

- Streams `export.xml` **inside the zip** — does **not** extract or store the full XML in corpus
- Aggregates daily metrics, workouts, ECG metadata
- Merges with existing non–Apple Health entries in fitness files (does not delete manual entries)

**Output files** (`structured_database/fitness/`):

| File | Contents |
|------|----------|
| `BODY_METRICS.json` | Daily: steps, sleep, weight, body fat %, resting HR, HRV, VO2max |
| `WORKOUTS.json` | Sessions: type, duration, distance, energy |
| `ECG_RECORDS.json` | Apple Watch ECG records (metadata) |
| `APPLE_HEALTH_META.json` | Import stats, date range, quality report |
| `APPLE_HEALTH_SUMMARY.md` | Human-readable summary for LLM / review |

**Options:**

| Flag | Description |
|------|-------------|
| `--copy-zip` | Copy archive to `sources/apple_health/` for local backup |
| `--corpus PATH` | Override structured_database path |

**Validation:**

```bash
medbots validate-apple-health --corpus ~/my-health/structured_database
```

**Re-import:** Running import again **replaces** previous `source: apple_health` rows in `BODY_METRICS.json` and `WORKOUTS.json`; other sources are kept.

**Quality checks:** Compares export DOB with `PATIENT_PROFILE.json`, flags empty date ranges, duplicate IDs. If profile has no DOB, import may fill it from Apple export.

**Not in pipeline:** `apple_health: false` in `bot_config.json` — import is always manual via CLI.

---

## 5. Pipeline — after parsing

**Command:** `medbots pipeline --bot-root ~/my-health`

Not a source parser, but **required** after PDF structure step:

| Step | Module | Purpose |
|------|--------|---------|
| Merge labs | `merge_labs_corpus` | Re-parse lab rows → `LABS_NORMALIZED.json` |
| LOINC | `apply_loinc_map` | Map codes via `labs/LOINC_MAP.tsv` |
| Dedup | `dedup_labs` | Remove duplicate lab rows |
| Goals | `extract_goals_from_doc_text` | From consultations (if `goals_reminders: true`) |
| Index | `write_corpus_index` | `CORPUS_INDEX.json` |

Toggle features in `bot_config.json` → `features`.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `missing PDF` on extract | File not under `sources/` or wrong path | Copy PDF, run `scan` again |
| `[NO_TEXT_LAYER` in pdf_text | Scanned PDF | OCR outside medbots, or get text-export from vendor |
| `empty text` on structure | Extract failed or blank PDF | Re-run extract, check PDF opens with selectable text |
| `missing pdf_text` | extract-text not run | `medbots extract-text --bot-root …` |
| Entry skipped on structure | Already has `structured_locally_at` | Add `--force` |
| Medsi lab not parsed | Wrong doc_type or not in medsi path | Ensure file is under `sources/medsi/` |
| Apple Health `quality=fail` | Corrupt zip or empty export | Re-export from iPhone; check zip size |
| No lab rows in LABS_NORMALIZED | pipeline not run | `medbots pipeline --bot-root …` |

**Validate full corpus:**

```bash
medbots validate --corpus ~/my-health/structured_database
```

---

## CLI quick reference

| Command | Input | Output |
|---------|-------|--------|
| `medbots scan` | `sources/{emias,medsi,gemotest}/` | `manifest.json` |
| `medbots extract-text` | manifest PDFs | `pdf_text/*.txt` |
| `medbots structure` | `pdf_text/` | `doc_text/*.md`, lab JSONL |
| `medbots import-apple-health` | `export.zip` | `fitness/*.json`, summary MD |
| `medbots validate-apple-health` | `fitness/` | stdout OK / errors |
| `medbots pipeline` | structured corpus | `LABS_NORMALIZED.json`, index |
| `medbots validate` | full corpus | integrity report |

See also: [Corpus file schema](CORPUS.md) · [LLM usage guide](LLM_GUIDE.md)
