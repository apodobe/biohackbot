#!/usr/bin/env bash
set -euo pipefail
VPS="${VPS:-n8n-server}"
REMOTE_SCRIPT="${REMOTE_SCRIPT:-/opt/medbot-ingest/weekly-goals-telegram.sh}"
LOCAL_SCRIPT="$(cd "$(dirname "$0")" && pwd)/06-weekly-goals-telegram.sh"
CRON_LINE="0 6 * * 1 $REMOTE_SCRIPT >> /var/log/biohack-reminder.log 2>&1"
echo "Deploy reminder script to $VPS:$REMOTE_SCRIPT"
rsync -avz "$LOCAL_SCRIPT" "$VPS:$REMOTE_SCRIPT"
ssh "$VPS" "chmod +x '$REMOTE_SCRIPT'"
echo "Install cron on $VPS (Monday 06:00 UTC):"
echo "$CRON_LINE"
ssh "$VPS" "(crontab -l 2>/dev/null | grep -v weekly-goals-telegram; echo '$CRON_LINE') | crontab -"
echo "Done."
