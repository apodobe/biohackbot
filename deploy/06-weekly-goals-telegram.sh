#!/usr/bin/env bash
set -euo pipefail
ENV_FILE="${BIOHACK_REMINDER_ENV:-/root/.config/biohack-reminder.env}"
if [[ -f "$ENV_FILE" ]]; then
  set -a && source "$ENV_FILE" && set +a
fi

CORPUS="${BIOHACKING_CORPUS_PATH:-/opt/medbot-corpus/structured_database}"
JSON="$CORPUS/GOALS_REMINDERS.json"
N="${GOALS_REMINDERS_TOP:-5}"

if [[ -z "${TELEGRAM_BOT_TOKEN:-}" || -z "${TELEGRAM_CHAT_ID:-}" ]]; then
  echo "ERROR: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID" >&2
  exit 1
fi
if [[ ! -f "$JSON" ]]; then
  echo "ERROR: missing $JSON" >&2
  exit 1
fi

TEXT=$(jq -r --argjson n "$N" '
  def hdr: "Напоминание BioHack: цели на неделю (обследования, БАДы, тренировки).\nСроки уточняйте у врача.\n\nТоп \($n|tostring):";
  hdr + "\n\n" + (
    ([.items[] | select(.active == true)] | sort_by(.rank))[:$n]
    | to_entries
    | map("\(.key + 1). \(.value.title_ru)\n   \(.value.why_ru)")
    | join("\n\n")
  ) + "\n\nИсточник: GOALS_REMINDERS.json"
' "$JSON")

if ((${#TEXT} > 4000)); then
  TEXT="${TEXT:0:3990}…"
fi

PAYLOAD=$(jq -n --arg t "$TEXT" --argjson cid "$TELEGRAM_CHAT_ID" \
  '{chat_id: $cid, text: $t, disable_web_page_preview: true}')

RESP=$(curl -sS -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H 'Content-Type: application/json' \
  -d "$PAYLOAD")

echo "$RESP" | jq -e '.ok == true' >/dev/null 2>&1 || {
  echo "ERROR: Telegram API" >&2
  echo "$RESP" >&2
  exit 1
}
echo "OK: biohack reminder sent"
