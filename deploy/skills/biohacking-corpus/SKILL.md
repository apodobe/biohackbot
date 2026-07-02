---
name: biohacking-corpus
description: Biohacking patient corpus Q&A; Russian replies; health, nutrition, supplements, fitness, metrics.
metadata: { "openclaw": { "requires": { "bins": ["bash", "jq", "cat"] } } }
---

# biohacking-corpus

**Root:** `/opt/medbot-corpus/structured_database` (env `BIOHACKING_CORPUS_PATH` overrides).

**Behavior:** Read `AI_SYSTEM_BRIEF_EN.md` (minimal) or `PROMPT_AGENT_EN.md` (full). Nav: `CORPUS_INDEX.json`. Standard: `docs/MED_BOTS_CORPUS_STANDARD.md`. Replies in **Russian**. Corpus-first; cite sources.

**Parallel sub-agents (Cursor Task):** When spawning parallel sub-agents for corpus reads, search, audit, or VPS prep — **mandatory** model **`composer-2.5`** (`model: "composer-2.5"` on every Task call). **Never** `composer-2.5-fast`. One domain per agent; parent synthesizes from summaries. Details: `PROMPT_OPUS_EN.md`.

**Telegram `/start`:** Run overview script, greet in Russian, state archive is on server (no need to paste PDFs), show counts (labs, doc_text, domains).

**Медси / анализы перед БАДами:** если пользователь спрашивает к какому врачу идти, что сказать, какие анализы сдать, или пишет `/medsi` — прочитать и выдать содержимое файла (можно разбить на 2–3 сообщения):

```bash
cat "$ROOT/recommendations/MEDSI_DOCTOR_GUIDE.md"
```

Ingest-бот: кнопка «👨‍⚕️ Врачи» (handler `doctors`).

**Кнопки справок (только 4):** если сообщение **точно совпадает** с `button` в `$ROOT/TELEGRAM_RESEARCH_BRIEFS.json`:

```bash
python3 /opt/medbot-ingest/biohack_telegram_briefs.py "<handler>" "$ROOT"
```

Handlers: `nutrition`, `medications`, `sport_load`, `doctors`. Ответ — **дословно**, без перефразирования.

```bash
bash /root/.openclaw/workspace/skills/biohacking-corpus/biohacking-corpus-overview.sh
```

```bash
ROOT="$(bash /root/.openclaw/workspace/skills/biohacking-corpus/biohacking-corpus-path.sh)"
jq '.rows[:40]' "$ROOT/LABS_NORMALIZED.json"
jq '.events[-25:]' "$ROOT/TIMELINE_EVENTS.json"
jq '.regimen' "$ROOT/supplements/SUPPLEMENTS.json"
jq '.sessions[-10:]' "$ROOT/fitness/WORKOUTS.json"
jq '.' "$ROOT/fitness/DAILY_MOVEMENT_SCHEDULE.json"
cat "$ROOT/recommendations/WALKING_FAT_LOSS_PODOBEDOV.md"
jq '.entries[-10:]' "$ROOT/fitness/BODY_METRICS.json"
```

**Genomics** (curated bundle only — never attach full VCF):

```bash
cat "$ROOT/genomics/GENETICS_SUMMARY.md"
jq '.panel_stats, .andme_crosscheck, .clinical_panel_non_reference_only' "$ROOT/genomics/GENETICS_OPUS_BUNDLE.json"
```

**Apple Health** (aggregated JSON — never attach export.xml):

```bash
cat "$ROOT/fitness/APPLE_HEALTH_SUMMARY.md"
jq '.entries[-7:]' "$ROOT/fitness/BODY_METRICS.json"
jq '.sessions[-10:]' "$ROOT/fitness/WORKOUTS.json"
jq '.quality, .date_range, .daily_metric_days' "$ROOT/fitness/APPLE_HEALTH_META.json"
```

**Living health summary** (if present — rolling synthesis, phase 2.6):

```bash
test -f "$ROOT/LIVING_HEALTH_SUMMARY.md" && cat "$ROOT/LIVING_HEALTH_SUMMARY.md"
```

**LOINC mapping** (if present — canonical lab codes, phase 2.1):

```bash
test -f "$ROOT/labs/LOINC_MAP.tsv" && head -n 20 "$ROOT/labs/LOINC_MAP.tsv"
```

Read `genomics/PROMPT_GENETICS_OPUS.md` when user asks about DNA, pharmacogenomics, vitamin D genetics, fitness SNPs.

```bash
rg -l "pattern" "$ROOT/doc_text" "$ROOT/pdf_text" 2>/dev/null | head
```

Session key: **`biohack:corpus`**.
