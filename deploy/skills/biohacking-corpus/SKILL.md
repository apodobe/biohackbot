---
name: med-corpus
description: Read structured medical corpus on VPS; answer from JSON and doc_text with source citations.
metadata: { "openclaw": { "requires": { "bins": ["bash", "jq", "cat"] } } }
---

# med-corpus

**Corpus root:** `/opt/medbot-corpus/structured_database` (override with `MEDBOTS_CORPUS_PATH`).

## Behavior

1. Read `CORPUS_INDEX.json` for navigation and counts.
2. Check `DISCREPANCIES.json` before interpreting labs.
3. Answer from corpus files only; cite file paths and dates.
4. Not a doctor — no prescriptions.

## Useful commands

```bash
ROOT="$(bash /root/.openclaw/workspace/skills/biohacking-corpus/biohacking-corpus-path.sh)"
bash /root/.openclaw/workspace/skills/biohacking-corpus/biohacking-corpus-overview.sh
jq '.totals' "$ROOT/../CORPUS_INDEX.json" 2>/dev/null || jq '.totals' "$ROOT/CORPUS_INDEX.json"
jq '.rows[:40]' "$ROOT/LABS_NORMALIZED.json"
test -f "$ROOT/LIVING_HEALTH_SUMMARY.md" && cat "$ROOT/LIVING_HEALTH_SUMMARY.md"
rg -l "keyword" "$ROOT/doc_text" "$ROOT/pdf_text" 2>/dev/null | head
```

Session key: configure per your OpenClaw setup (e.g. `med:corpus`).
