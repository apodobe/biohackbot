#!/usr/bin/env bash
# Return verbatim brief text for a research section (OpenClaw / CLI).
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
BASE="$(bash "$DIR/biohacking-corpus-path.sh")"
BRIEFS="$BASE/TELEGRAM_RESEARCH_BRIEFS.json"
KEY="${1:-}"

if [[ ! -f "$BRIEFS" ]]; then
  echo "ERROR: missing $BRIEFS" >&2
  exit 1
fi

if [[ -z "$KEY" ]]; then
  echo "Usage: biohacking-research-brief.sh <section_id|button_label>" >&2
  echo "Sections:" >&2
  jq -r '.sections[] | "  \(.id) — \(.button)"' "$BRIEFS"
  exit 1
fi

HANDLER=$(jq -r --arg k "$KEY" '
  .sections[] | select(.id == $k or .button == $k) | .handler // ""
' "$BRIEFS" | head -n 1)

TB_SCRIPT="/opt/medbot-ingest/biohack_telegram_briefs.py"
if [[ -z "$HANDLER" && ( "$KEY" == "К кому идти в Медси" || "$KEY" == "👨‍⚕️ Врачи" ) ]]; then
  HANDLER="doctors"
fi

if [[ -n "$HANDLER" ]]; then
  if [[ -f "$TB_SCRIPT" ]]; then
    python3 "$TB_SCRIPT" "$HANDLER" "$BASE"
    exit 0
  fi
  REPO_SCRIPT="$(cd "$(dirname "$0")/../../../scripts" 2>/dev/null && pwd)/biohack_telegram_briefs.py"
  if [[ -f "$REPO_SCRIPT" ]]; then
    python3 "$REPO_SCRIPT" "$HANDLER" "$BASE"
    exit 0
  fi
fi

jq -r --arg k "$KEY" '
  . as $root
  | ($root.sections[] | select(.id == $k or .button == $k))
  | (.title // .id), "", (.text // ""), "", ($root.disclaimer // "")
' "$BRIEFS"
