# Architecture

How **biohackbot** (`medbots-core` package, `medbots` CLI) is organized.

## System overview

```mermaid
flowchart TB
  subgraph local["Local instance ~/my-health"]
    SRC["sources/{emias,medsi,gemotest,apple_health}"]
    MAN["manifest.json"]
    PT["pdf_text/*.txt"]
    DT["doc_text/*.md"]
    LABS["LABS_NORMALIZED.json"]
    FIT["fitness/*.json"]
    IDX["CORPUS_INDEX.json"]
  end

  subgraph cli["medbots CLI — no LLM API"]
    SCAN[scan]
    EXT[extract-text]
    STRUCT[structure]
    AH[import-apple-health]
    PIPE[pipeline]
  end

  subgraph parsers["local_structure_pdfs.py"]
    E[parse_emias_*]
    M[parse_medsi_*]
    G[parse_gemotest]
  end

  subgraph pipeline["pipeline/ — rule-based composer"]
    MERGE[merge_labs_corpus]
    LOINC[apply_loinc_map]
    DEDUP[dedup_labs]
    GOALS[extract_goals_from_doc_text]
    DISC[generate_discrepancies]
    LHM[generate_lhm]
    VAL[validate_corpus]
    INDEX[write_corpus_index]
  end

  SRC --> SCAN --> MAN
  MAN --> EXT --> PT
  PT --> STRUCT --> parsers
  parsers --> DT
  parsers --> LABS
  AH --> FIT
  DT --> PIPE
  PIPE --> MERGE --> LOINC --> DEDUP --> GOALS --> DISC --> LHM --> VAL --> INDEX
  INDEX --> IDX
```

## Module map

| Path | Role |
|------|------|
| `medbots/cli.py` | User-facing commands |
| `medbots/init_instance.py` | Scaffold private instance |
| `medbots/scan_sources.py` | Register PDFs → `manifest.json` |
| `medbots/extract_pdf_text.py` | PyMuPDF text layer → `pdf_text/` |
| `medbots/local_structure_pdfs.py` | Vendor parsers (EMIAS, Medsi, Gemotest) |
| `medbots/import_apple_health.py` | Stream Apple Health `export.zip` → `fitness/` |
| `medbots/merge_labs_corpus.py` | Re-parse lab rows into `LABS_NORMALIZED.json` |
| `medbots/pipeline/run.py` | Orchestrates post-structure enrichment |
| `medbots/corpus_io.py` | Manifest, paths, patient DOB |
| `medbots/config.py` | `bot_config.json` feature flags |
| `deploy/` | Optional VPS rsync + OpenClaw skill template |

## Manifest entry lifecycle

```mermaid
stateDiagram-v2
  [*] --> Registered: medbots scan
  Registered --> HasText: medbots extract-text\nextracted_txt set
  HasText --> Structured: medbots structure\nstructured_locally_at, doc_text
  Structured --> Enriched: medbots pipeline\nLABS_NORMALIZED, indexes
  note right of Structured
    grok_ingested_at (optional private ingest)
    skips local structure if set
  end note
```

| Field | Set by | Meaning |
|-------|--------|---------|
| `source_pdf`, `sha256` | scan | Path under instance + content hash |
| `extracted_txt` | extract-text | Relative path in `pdf_text/` |
| `structured_locally_at` | structure | Local parser succeeded |
| `doc_text` | structure | Relative path in `doc_text/` |
| `grok_ingested_at` | optional private Grok ingest | Skips local structure |

## Composer vs LLM

| Layer | What | API calls |
|-------|------|-----------|
| **Local parsers** | `structure`, Apple Health import | None |
| **Composer (pipeline)** | Goals, supplements, protocols, discrepancies drafts — `extracted_by: composer` in JSON meta | None — regex/rules in Python |
| **LLM ingest** | Scanned PDFs without text layer (private `grok_ingest`) | xAI Grok vision/text |
| **LLM Q&A** | OpenClaw agent on VPS reading corpus files | Grok / etc. per deploy config |
| **LLM review** | Human-driven pass on drafts, LHM v2 | User-chosen model — see [LLM_GUIDE.md](LLM_GUIDE.md) |

**Public repo default:** tiers 0–1 only (local + optional manual review). No Grok/Telegram ingest in this repository.

## Adding a new PDF vendor

1. Add `sources/<vendor>/` in `init_instance.py` and `scan_sources.py` (`_VENDORS`).
2. Implement `parse_<vendor>_*` in `local_structure_pdfs.py`.
3. Route in `_parse_entry()` by `source_system` / path.
4. Add golden fixture under `tests/fixtures/pdf_text/` + tests in `tests/test_parse_<vendor>.py`.
5. Document in [PARSERS.md](PARSERS.md).

## Tests and demo

| Asset | Purpose |
|-------|---------|
| `tests/fixtures/pdf_text/` | Synthetic extracts for unit tests |
| `examples/demo-instance/` | Runnable corpus without PDF binaries |
| `tests/test_demo_instance.py` | E2E structure + pipeline on demo copy |

## Optional VPS path

```mermaid
flowchart LR
  MAC["Mac: medbots pipeline"]
  RSYNC["deploy/02-rsync-corpus.sh"]
  VPS["VPS: /opt/medbot-corpus/structured_database"]
  OC["OpenClaw + biohacking-corpus skill"]
  MAC --> RSYNC --> VPS --> OC
```

Only text and JSON are synced — no PDFs. See [deploy/RUNBOOK.md](../deploy/RUNBOOK.md).
