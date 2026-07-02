#!/usr/bin/env bash
# Unified VPS deploy for medical bots (corpus rsync + optional ingest-bot restart).
# Usage: ./deploy-bot.sh mymedbot|idamedbot|meiramedbot [--skip-ingest]
set -euo pipefail

BOT="${1:-}"
SKIP_INGEST="${2:-}"

if [[ -z "$BOT" ]]; then
  echo "Usage: $0 mymedbot|idamedbot|meiramedbot [--skip-ingest]" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CURSOR_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

case "$BOT" in
  mymedbot)
    REPO="$CURSOR_ROOT/biohackbot"
    INGEST_INSTALL="$REPO/openclaw-vps-deploy/09-install-biohack-ingest-bot.sh"
    INGEST_UNIT="biohacking-ingest-bot"
    ;;
  idamedbot)
    REPO="$CURSOR_ROOT/Анализы"
    INGEST_INSTALL="$REPO/openclaw-vps-deploy/09-install-medical-ingest-bot.sh"
    INGEST_UNIT="medical-ingest-bot"
    ;;
  meiramedbot)
    REPO="$CURSOR_ROOT/irina-healthbot"
    INGEST_INSTALL=""
    INGEST_UNIT=""
    ;;
  *)
    echo "Unknown bot: $BOT" >&2
    exit 1
    ;;
esac

if [[ ! -d "$REPO/openclaw-vps-deploy" ]]; then
  echo "Repo not found: $REPO" >&2
  exit 1
fi

ingest_enabled() {
  python3 - <<PY
import json
from pathlib import Path
cfg = json.loads(Path("$REPO/bot_config.json").read_text(encoding="utf-8"))
print("true" if cfg.get("features", {}).get("ingest_telegram") else "false")
PY
}

echo "==> Deploy $BOT from $REPO"
cd "$REPO/openclaw-vps-deploy"
./02-rsync-corpus.sh

if [[ "$SKIP_INGEST" == "--skip-ingest" ]]; then
  echo "Skipping ingest-bot (flag --skip-ingest)."
  exit 0
fi

if [[ "$(ingest_enabled)" != "true" ]]; then
  echo "ingest_telegram=false in bot_config.json — corpus only, no ingest restart."
  exit 0
fi

if [[ -z "$INGEST_INSTALL" || ! -f "$INGEST_INSTALL" ]]; then
  echo "No ingest install script for $BOT."
  exit 0
fi

echo "==> Install/restart ingest bot ($INGEST_UNIT)"
bash "$INGEST_INSTALL"
VPS="${VPS:-n8n-server}"
if [[ "$BOT" == "idamedbot" ]]; then
  VPS="${VPS:-root@YOUR_VPS_HOST}"
fi
ssh "$VPS" "sudo systemctl restart $INGEST_UNIT && sudo systemctl is-active $INGEST_UNIT"
echo "Deploy OK: $BOT"
