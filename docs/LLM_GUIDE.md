# LLM usage guide

When you need language models, which tier to use, and how corpus size affects cost.

**Core principle:** `medbots scan` → `extract-text` → `structure` → `pipeline` runs **without any LLM API**. Parsing EMIAS, Medsi, Gemotest, and Apple Health is deterministic Python. LLMs are for **Q&A bots**, **optional scan ingest**, and **review/synthesis** of already-structured files.

See also: [Parser guide](PARSERS.md)

---

## Quick map: step → LLM?

| Step | Command / artifact | LLM? | Typical tier |
|------|-------------------|------|--------------|
| Register PDFs | `medbots scan` | No | — |
| PDF text layer | `medbots extract-text` | No | — |
| Vendor parse | `medbots structure` | No | — |
| Apple Health | `medbots import-apple-health` | No | — |
| Lab merge, LOINC, dedup | `medbots pipeline` | No | — |
| Goals / supplements / protocols draft | pipeline (`extracted_by: composer`) | No* | — |
| Discrepancies draft | `DISCREPANCIES.json` | No* | — |
| LHM v1 | `LIVING_HEALTH_SUMMARY.md` | No | — |
| Corpus navigation | `CORPUS_INDEX.json` | No | — |
| Telegram brief buttons (4 presets) | shell scripts | No | — |
| OpenClaw Q&A over corpus | OpenClaw agent | **Yes** | Mid |
| Scanned PDF / photo ingest | optional Grok ingest (private) | **Yes** | Fast |
| Review composer drafts | manual chat session | **Yes** | Light → heavy |
| Full corpus audit / narrative LHM | manual chat session | **Yes** | Heavy |

\*Pipeline steps labeled `composer` are **rule-based Python**, not an API call. They produce drafts that **should** be reviewed by a human + LLM before clinical reliance.

---

## Model tiers (practical)

| Tier | Examples | Cost | Use for |
|------|----------|------|---------|
| **0 — Local** | medbots only | Free | All ingest and normalization |
| **1 — Fast** | Grok fast-reasoning, Gemini Flash, GPT-4o-mini | Low | JSON cleanup, dedupe, single-file edits, ingest of 1–3 scans |
| **2 — Mid** | Grok 4.x (OpenClaw default), Gemini Pro, GPT-4o | Medium | Daily Telegram Q&A, targeted questions, 1–2 domain reads |
| **3 — Heavy** | Claude Opus, GPT-4.1, long-context Gemini | High | Cross-domain synthesis, genetics, discrepancy narratives, LHM rewrite, quarterly audits |

**Rule of thumb:** start at the lowest tier that can complete the task; escalate only when answers miss cross-file context or medical nuance.

---

## OpenClaw / clawbot (VPS Q&A)

Public deploy template: [deploy/RUNBOOK.md](../deploy/RUNBOOK.md), skill [biohacking-corpus](../deploy/skills/biohacking-corpus/SKILL.md).

### What does **not** use the LLM

- Corpus sync (`rsync` text + JSON only)
- Skill overview script (`biohacking-corpus-overview.sh`)
- Preset Telegram briefs when wired to `biohack_telegram_briefs.py` — **verbatim script output**, no reasoning
- Reading files via `jq`, `rg`, `cat` in the skill

### What **does** use the LLM

- Free-form patient questions in Telegram / OpenClaw session
- Synthesizing answers from multiple corpus files
- Explaining trends, conflicts, “what changed since last year”

### Recommended model for OpenClaw agent

Private biohackbot deploy defaults to **`xai/grok-4.3`** for the `biohacking` agent — good balance for Russian medical Q&A with tool use (read index → pull snippets → answer with citations).

| Corpus size (PDFs) | OpenClaw model | Notes |
|--------------------|----------------|-------|
| &lt; 20 | Grok 4.x / GPT-4o-mini | `LIVING_HEALTH_SUMMARY.md` + sliced `LABS_NORMALIZED` usually fit |
| 20–80 | Grok 4.x / GPT-4o | Prefer skill scripts + `rg` before loading full JSON |
| 80+ | Same mid tier + **strict read order** | Do not attach whole `doc_text/`; use LHM + index + targeted paths |
| Any + genetics | Mid for Q&A; **heavy for interpretation** | Separate genetics session (see below) |

**Upgrade to tier 3** when: user asks for multi-year trend tables, reconciliation of contradictions across &gt;10 visits, or treatment-style recommendations from scattered consults.

**Downgrade to tier 1** when: question is “what was hemoglobin on date X?” — answer from one `jq` query, model only formats Russian text.

### Mandatory bot behavior (put in corpus `PROMPT_AGENT.md`)

1. First line: **sources used** (file paths + dates)
2. Read order: `CORPUS_INDEX.json` → `DISCREPANCIES.json` → `LIVING_HEALTH_SUMMARY.md` → domain JSON → `doc_text/` only if needed
3. Not a physician — no new prescriptions
4. Template: [prompts/PROMPT_AGENT.template.md](prompts/PROMPT_AGENT.template.md)

---

## Files: who builds them vs who should review

### Generated locally (no LLM)

| File | Producer |
|------|----------|
| `manifest.json`, `pdf_text/`, `doc_text/` | scan + extract + structure |
| `labs/*.jsonl`, `LABS_NORMALIZED.json` | structure + pipeline |
| `fitness/*.json`, `APPLE_HEALTH_SUMMARY.md` | Apple Health import |
| `CORPUS_INDEX.json` | pipeline |
| `DISCREPANCIES.json` (draft) | pipeline rules |
| `GOALS_REMINDERS.json` (draft) | pipeline |
| `supplements/SUPPLEMENTS.json` (draft) | pipeline |
| `biohacking/PROTOCOLS.json` (draft) | pipeline |
| `LIVING_HEALTH_SUMMARY.md` (v1) | pipeline |

### Recommended LLM review pass

| File | Tier | When required | Task |
|------|------|---------------|------|
| `GOALS_REMINDERS.json` | 1 | After new consult PDFs | Dedupe, priorities, mark stale `inactive` |
| `supplements/SUPPLEMENTS.json` | 1 | After supplement mentions in doc_text | Normalize doses/schedules, merge duplicates |
| `biohacking/PROTOCOLS.json` | 1 | After lifestyle / exam docs | Merge duplicates, add schedules from sources |
| `DISCREPANCIES.json` | 1 then **3** | Always before trusting alerts | Tier 1: remove false positives; tier 3: `narrative_ru` for high-severity items |
| `LIVING_HEALTH_SUMMARY.md` | **3** | Quarterly or after &gt;15 new PDFs | Rewrite v2: trends, goals, genetics pointers; ≤400 lines; corpus-only |
| `nutrition/NUTRITION.json` | **3** | If nutritionist consults present | Add `clinical_context_ru` per recipe cluster |
| `genomics/*` | **3** | Separate session | Never mix full VCF into general Q&A; use curated bundle only |
| `recommendations/*.md` | **3** | Optional planning docs | Training / walking plans — human-reviewed narrative |

Attach **minimum context** for review sessions:

```
CORPUS_INDEX.json
DISCREPANCIES.json
<file under review>
related doc_text paths cited in that file's meta
```

Full review template: [prompts/PROMPT_OPUS.template.md](prompts/PROMPT_OPUS.template.md)

---

## Scaling by corpus volume

Use `jq '.totals' CORPUS_INDEX.json` after each pipeline run.

### Small (&lt; 15 PDFs, &lt; 300 lab rows)

- Local pipeline only is often enough
- OpenClaw tier 2 with LHM + index
- LLM review: optional pass on `GOALS_REMINDERS.json` only

### Medium (15–60 PDFs, 300–1500 lab rows)

- Run tier-1 review on all composer drafts after each bulk import
- OpenClaw: never paste full `LABS_NORMALIZED.json`; use `jq '.rows | map(select(.canonical_key == "hemoglobin")) | .[-5:]'`
- Tier-3 LHM rewrite every 6–12 months

### Large (60+ PDFs, 1500+ lab rows, 5+ years labs)

- **Split work by domain** (labs / imaging / supplements / fitness) — parallel sessions or sub-agents
- OpenClaw: skill + `rg` keyword search in `doc_text/` before any bulk read
- Tier 3: mandatory `DISCREPANCIES.json` narrative pass after pipeline
- Consider maintaining `AI_SYSTEM_BRIEF.md` (1-page human summary) to cut tokens

### Apple Health (any size)

- Bot reads `APPLE_HEALTH_SUMMARY.md` + sliced `BODY_METRICS.json`, not raw export
- Heavy model only for long-range training/load analysis spanning years

---

## Optional: LLM ingest (scanned PDFs)

**Not in the public repo** — available in private setups (Telegram ingest bot + `grok_ingest`).

Use only when `extract-text` produced `[NO_TEXT_LAYER`.

| Input | Suggested model | Env |
|-------|-----------------|-----|
| Text PDF fallback | `grok-4-1-fast-reasoning` | `INGEST_LLM_MODEL` |
| Scan / photo | same + vision | `XAI_API_KEY` |

Prefer re-downloading text-based PDFs from the lab portal over LLM OCR — cheaper and more accurate.

After Grok ingest, still run `medbots pipeline` and treat output like composer drafts (review tier 1+).

---

## Cost control checklist

1. **Always** complete local pipeline before any LLM step
2. **Index first** — `CORPUS_INDEX.json` + `DISCREPANCIES.json` before opening `doc_text/`
3. **Slice JSON** — last N values per `canonical_key`, not full `LABS_NORMALIZED.json`
4. **One domain per heavy session** — labs OR genetics OR nutrition, not all three
5. **Scripted briefs** for recurring questions (sport, meds, doctors) — zero tokens
6. **Re-run pipeline** instead of asking LLM to “parse this PDF again”

---

## Suggested workflow after new data

```bash
# 1. Local (free)
medbots scan && medbots extract-text && medbots structure && medbots pipeline && medbots validate

# 2. Light review (tier 1) — GOALS, SUPPLEMENTS, PROTOCOLS if changed

# 3. OpenClaw smoke test — one factual question with source line

# 4. Heavy pass (tier 3) — only if DISCREPANCIES high count or quarterly audit
```

---

## Prompt templates

Copy into your private `structured_database/` and edit paths:

- [PROMPT_AGENT.template.md](prompts/PROMPT_AGENT.template.md) — OpenClaw / daily Q&A
- [PROMPT_OPUS.template.md](prompts/PROMPT_OPUS.template.md) — heavy audit / LHM v2
