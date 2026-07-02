# Heavy corpus review — Opus / Claude / GPT-4.1 (template)

Copy to `structured_database/PROMPT_OPUS.md`. Use for quarterly audits, LHM v2, genetics-adjacent synthesis.

**Output language:** Russian for the patient. **This file:** English to save tokens in the chat system prompt.

## Attach minimum

Token saver:

- `CORPUS_INDEX.json`
- `DISCREPANCIES.json`
- `LABS_NORMALIZED.json` (or jq export of top-30 keys × last 5 values)
- `TIMELINE_EVENTS.json` (if present)
- `LIVING_HEALTH_SUMMARY.md` (current v1)
- Target file under review (e.g. `GOALS_REMINDERS.json`)

Full audit: whole `structured_database/` folder — **no PDF binaries**.

## Do not

- Load all `doc_text/` into one context on large corpora (&gt;40 PDFs with doc_text).
- Invent lab values or visit dates.
- Issue treatment orders.

## Strategy by corpus size

| PDFs | Approach |
|------|----------|
| &lt; 20 | Single session, sequential read per read_order |
| 20–60 | One domain per message (labs → visits → supplements → fitness) |
| 60+ | Parallel domain summaries (separate chats or sub-agents), parent synthesizes from summaries + CORPUS_INDEX only |

## Domain split (suggested)

| Domain | Key paths |
|--------|-----------|
| Labs | `LABS_NORMALIZED.json`, `doc_text/*анализ*`, `doc_text/*кров*` |
| Visits / imaging | `doc_text/*консультац*`, `doc_text/*УЗИ*`, `doc_text/*эпикриз*` |
| Supplements / protocols | `supplements/SUPPLEMENTS.json`, `biohacking/PROTOCOLS.json`, `GOALS_REMINDERS.json` |
| Fitness | `fitness/BODY_METRICS.json`, `fitness/WORKOUTS.json`, `fitness/APPLE_HEALTH_SUMMARY.md` |
| Data quality | `DISCREPANCIES.json`, manifest vs doc_text dates, `[NO_TEXT_LAYER]` in pdf_text |
| Genetics (optional) | `genomics/GENETICS_SUMMARY.md`, curated bundle only — **separate run** |

## User message (copy-paste)

```
You are a medical data analyst, not a physician. Patient and corpus: see attached CORPUS_INDEX.json.

Rules: PROMPT_AGENT.md. Every claim: document date + corpus path. Missing → «в корпусе не найдено». No prescriptions. Reply in Russian.

If corpus is large: work domain-by-domain per PROMPT_OPUS.md table. Return summaries ≤40 lines each with source paths before final synthesis.

Final deliverable:
- Источники: … (first line)
- Executive summary (5–8 sentences)
- Tables by domain (labs, visits, gaps)
- Top 5 actions for 4–8 weeks
- List DISCREPANCIES to fix before VPS rsync

Do not dump raw doc_text. Cite paths only.
```

## File-specific tasks

| File | Model tier | Task |
|------|------------|------|
| `GOALS_REMINDERS.json` | 1 | Dedupe, prioritize, mark stale inactive |
| `supplements/SUPPLEMENTS.json` | 1 | Normalize doses, merge duplicates |
| `biohacking/PROTOCOLS.json` | 1 | Merge duplicates, add schedules from source_path |
| `DISCREPANCIES.json` | 1 → 3 | Remove false positives; then narrative_ru for top high severity |
| `LIVING_HEALTH_SUMMARY.md` | 3 | Rewrite v2: trends, goals, genetics pointers; max 400 lines; corpus-only |
| `nutrition/NUTRITION.json` | 3 | clinical_context_ru per recipe cluster |

After edits: run `medbots pipeline` and `medbots validate` locally, then rsync to VPS.
