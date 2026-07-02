#!/usr/bin/env bash
set -euo pipefail
VPS="${VPS:?Set VPS=root@your-host}"
LOCAL="${CORPUS:?Set CORPUS=/path/to/structured_database}"
REMOTE_DIR="${REMOTE_DIR:-/opt/medbot-corpus/structured_database}"
echo "Local:  $LOCAL"
echo "Remote: $VPS:$REMOTE_DIR"
ssh "$VPS" "mkdir -p '$REMOTE_DIR'"
rsync -avz --delete \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  --exclude '*.pdf' \
  "$LOCAL/" "$VPS:$REMOTE_DIR/"
ssh "$VPS" "mkdir -p /opt/medbot-corpus && chmod -R a+rX /opt/medbot-corpus"
echo "Done."
