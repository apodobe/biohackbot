#!/usr/bin/env bash
set -euo pipefail
VPS="${VPS:-n8n-server}"
REMOTE_ROOT="${REMOTE_ROOT:-/opt/medbot-ingest}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

if [[ -f "$REPO_ROOT/bot_config.json" ]]; then
  if ! python3 -c "import json; c=json.load(open('$REPO_ROOT/bot_config.json')); exit(0 if c.get('features',{}).get('ingest_telegram') else 1)"; then
    echo "ingest_telegram=false in bot_config.json — skip ingest-bot install."
    exit 0
  fi
fi

LOCAL_SCRIPTS="$REPO_ROOT/scripts"
LOCAL_REQ="$(cd "$(dirname "$0")" && pwd)/requirements-biohack-ingest.txt"

ssh "$VPS" "mkdir -p '$REMOTE_ROOT'"
rsync -avz --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  "$LOCAL_SCRIPTS/biohack_ingest_lib.py" \
  "$LOCAL_SCRIPTS/corpus_io.py" \
  "$LOCAL_SCRIPTS/biohack_medsi_guide.py" \
  "$LOCAL_SCRIPTS/biohack_ldl_lifestyle.py" \
  "$LOCAL_SCRIPTS/biohack_gi_health.py" \
  "$LOCAL_SCRIPTS/biohack_workout_assistant.py" \
  "$LOCAL_SCRIPTS/biohack_strength_program.py" \
  "$LOCAL_SCRIPTS/biohack_exercise_media.py" \
  "$LOCAL_SCRIPTS/biohack_push_sport_gifs.py" \
  "$LOCAL_SCRIPTS/biohack_mediterranean_game.py" \
  "$LOCAL_SCRIPTS/biohack_research_briefs.py" \
  "$LOCAL_SCRIPTS/biohack_telegram_briefs.py" \
  "$LOCAL_SCRIPTS/biohack_telegram_push_keyboard.py" \
  "$LOCAL_SCRIPTS/biohack_telegram_ingest_bot.py" \
  "$LOCAL_SCRIPTS/biohack_text_ingest.py" \
  "$LOCAL_SCRIPTS/biohack_ingest_extract_prompt.txt" \
  "$LOCAL_SCRIPTS/reconcile_goals.py" \
  "$VPS:$REMOTE_ROOT/"
rsync -avz "$LOCAL_REQ" "$VPS:$REMOTE_ROOT/requirements.txt"
rsync -avz "$(cd "$(dirname "$0")" && pwd)/biohack-ingest-bot.env.example" "$VPS:$REMOTE_ROOT/"

ssh "$VPS" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'REMOTE'
set -euo pipefail
cd "$REMOTE_ROOT"
python3 -m venv venv
venv/bin/pip install -U pip
venv/bin/pip install -r requirements.txt
REMOTE

ssh "$VPS" "REMOTE_ROOT='$REMOTE_ROOT' bash -s" <<'REMOTE'
set -euo pipefail
REMOTE_ROOT="${REMOTE_ROOT:-/opt/medbot-ingest}"
cat > /tmp/biohacking-ingest-bot.service <<UNIT
[Unit]
Description=Biohacking corpus Telegram ingest bot
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${REMOTE_ROOT}
EnvironmentFile=-/root/.config/biohacking-ingest-bot.env
ExecStart=${REMOTE_ROOT}/venv/bin/python ${REMOTE_ROOT}/biohack_telegram_ingest_bot.py
Restart=on-failure
RestartSec=15

[Install]
WantedBy=multi-user.target
UNIT
sudo mv /tmp/biohacking-ingest-bot.service /etc/systemd/system/biohacking-ingest-bot.service
sudo systemctl daemon-reload
REMOTE

echo ""
echo "На VPS:"
echo "  cp biohack-ingest-bot.env.example -> /root/.config/biohacking-ingest-bot.env"
echo "  sudo systemctl enable --now biohacking-ingest-bot"
echo "  # Клавиатура на @your_medbot (если нужна там же):"
echo "  TELEGRAM_PUSH_BOT_TOKEN=... TELEGRAM_PUSH_CHAT_IDS=... venv/bin/python biohack_telegram_push_keyboard.py"
