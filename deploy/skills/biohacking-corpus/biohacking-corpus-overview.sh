#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$(bash "$DIR/biohacking-corpus-path.sh")"
if [[ ! -d "$BASE" ]]; then
  echo "ERROR: corpus not found at $BASE" >&2
  exit 1
fi
echo "=== MEDBOTS_CORPUS_PATH=$BASE ==="
for f in CORPUS_INDEX.json DISCREPANCIES.json LABS_NORMALIZED.json manifest.json LIVING_HEALTH_SUMMARY.md; do
  p="$BASE/$f"
  if [[ -f "$p" ]]; then
    echo "-- $f ($(wc -c < "$p" | tr -d ' ') bytes) --"
    head -n 3 "$p"
    echo "..."
  else
    echo "-- MISSING: $f --"
  fi
done
echo "=== pdf_text ==="
find "$BASE/pdf_text" -type f -name '*.txt' 2>/dev/null | wc -l | xargs echo "files:"
echo "=== doc_text ==="
find "$BASE/doc_text" -type f 2>/dev/null | wc -l | xargs echo "files:"
