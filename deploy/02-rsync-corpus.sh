#!/usr/bin/env bash
set -euo pipefail
VPS="${VPS:-n8n-server}"
LOCAL="${LOCAL:-$(cd "$(dirname "$0")/.." && pwd)/structured_database}"
REMOTE_DIR="${REMOTE_DIR:-/opt/medbot-corpus/structured_database}"
echo "Local:  $LOCAL"
echo "Remote: $VPS:$REMOTE_DIR"
ssh "$VPS" "mkdir -p '$REMOTE_DIR'"
rsync -avz --delete \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  --exclude '*.pdf' \
  --exclude 'telegram_ingest/' \
  "$LOCAL/" "$VPS:$REMOTE_DIR/"
ssh "$VPS" "mkdir -p /opt/medbot-corpus && chown -R root:root /opt/medbot-corpus && chmod -R a+rX /opt/medbot-corpus"
if [[ -f "$(cd "$(dirname "$0")/.." && pwd)/scripts/reconcile_goals.py" ]]; then
  rsync -avz "$(cd "$(dirname "$0")/.." && pwd)/scripts/reconcile_goals.py" "$VPS:/opt/medbot-ingest/reconcile_goals.py"
  ssh "$VPS" "python3 /opt/medbot-ingest/reconcile_goals.py --corpus /opt/medbot-corpus/structured_database --recent-days 14 --apply" || true
fi
echo "Done."
