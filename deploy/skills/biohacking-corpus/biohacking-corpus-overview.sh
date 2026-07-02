#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$(bash "$DIR/biohacking-corpus-path.sh")"
if [[ ! -d "$BASE" ]]; then
  echo "ERROR: corpus not found at $BASE" >&2
  exit 1
fi
echo "=== BIOHACKING_CORPUS_PATH=$BASE ==="
for f in AI_SYSTEM_BRIEF_EN.md CORPUS_INDEX.json DISCREPANCIES.json LABS_NORMALIZED.json TIMELINE_EVENTS.json GOALS_REMINDERS.json manifest.json PROMPT_AGENT_EN.md LIVING_HEALTH_SUMMARY.md; do
  p="$BASE/$f"
  if [[ -f "$p" ]]; then
    echo "-- $f ($(wc -c < "$p" | tr -d ' ') bytes) --"
    head -n 5 "$p"
    echo "..."
  else
    echo "-- MISSING: $f --"
  fi
done
for sub in supplements/SUPPLEMENTS.json nutrition/NUTRITION.json fitness/WORKOUTS.json fitness/BODY_METRICS.json biohacking/PROTOCOLS.json; do
  p="$BASE/$sub"
  if [[ -f "$p" ]]; then
    echo "-- $sub --"
    jq 'if .rows then (.rows|length) elif .entries then (.entries|length) elif .sessions then (.sessions|length) elif .regimen then (.regimen|length) elif .protocols then (.protocols|length) else . end' "$p" 2>/dev/null || head -n 3 "$p"
  fi
done
echo "=== pdf_text ==="
PDF_TXT_COUNT=0
if [[ -d "$BASE/pdf_text" ]]; then
  PDF_TXT_COUNT=$(find "$BASE/pdf_text" -type f -name '*.txt' 2>/dev/null | wc -l | tr -d ' ')
  echo "files: $PDF_TXT_COUNT"
fi
echo "=== doc_text ==="
DOC_COUNT=0
if [[ -d "$BASE/doc_text" ]]; then
  DOC_COUNT=$(find "$BASE/doc_text" -type f \( -name '*.md' -o -name '*.txt' \) 2>/dev/null | wc -l | tr -d ' ')
  echo "files: $DOC_COUNT"
fi
echo "=== welcome_stats ==="
MAN="$BASE/manifest.json"
if [[ -f "$MAN" ]] && command -v jq >/dev/null 2>&1; then
  jq -r '"manifest_meta_built=" + (.meta.built // ""), "manifest_pdf_count=" + ((.meta.pdf_count // 0)|tostring)' "$MAN"
fi
echo "pdf_text_txt_files=${PDF_TXT_COUNT}"
echo "doc_text_files=${DOC_COUNT}"
echo "=== genomics ==="
G="$BASE/genomics/GENETICS_OPUS_BUNDLE.json"
if [[ -f "$G" ]] && command -v jq >/dev/null 2>&1; then
  jq -r '"genomics_sample=" + (.vcf_meta.sample_id // ""), "genomics_snps_on_chip=" + ((.vcf_meta.variants_on_chip // 0)|tostring), "genomics_panel_non_ref=" + ((.panel_stats.non_reference_in_panel // 0)|tostring), "genomics_andme_matched=" + ((.andme_crosscheck.matched // 0)|tostring)' "$G"
else
  echo "genomics: MISSING"
fi
echo "=== apple_health ==="
AH="$BASE/fitness/APPLE_HEALTH_META.json"
if [[ -f "$AH" ]] && command -v jq >/dev/null 2>&1; then
  jq -r '"apple_health_days=" + ((.daily_metric_days // 0)|tostring), "apple_health_workouts=" + ((.workouts // 0)|tostring), "apple_health_range=" + ((.date_range[0] // "") + ".." + (.date_range[1] // "")), "apple_health_quality=" + (.quality.status // "")' "$AH"
else
  echo "apple_health: MISSING"
fi
echo "=== living_health_summary ==="
LHM="$BASE/LIVING_HEALTH_SUMMARY.md"
if [[ -f "$LHM" ]]; then
  echo "living_health_summary_bytes=$(wc -c < "$LHM" | tr -d ' ')"
  head -n 8 "$LHM"
  echo "..."
else
  echo "living_health_summary: MISSING (phase 2.6)"
fi
echo "=== loinc_map ==="
LOINC="$BASE/labs/LOINC_MAP.tsv"
if [[ -f "$LOINC" ]]; then
  echo "loinc_map_lines=$(wc -l < "$LOINC" | tr -d ' ')"
  head -n 5 "$LOINC"
  echo "..."
else
  echo "loinc_map: MISSING (phase 2.1)"
fi
LABS="$BASE/LABS_NORMALIZED.json"
if [[ -f "$LABS" ]] && command -v jq >/dev/null 2>&1; then
  jq -r '
    (.rows | length) as $n
    | ([.rows[] | select(.loinc != null and .loinc != "")] | length) as $l
    | if $n > 0 then "labs_rows=\($n) loinc_filled_pct=\(($l * 100 / $n)|floor)%" else "labs_rows=0" end
  ' "$LABS"
fi
