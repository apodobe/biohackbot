#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/validate-deploy-path.sh
source "$SCRIPT_DIR/lib/validate-deploy-path.sh"

VPS="${VPS:?Set VPS=root@your-host}"
LOCAL="${CORPUS:?Set CORPUS=/path/to/structured_database}"
REMOTE_DIR="${REMOTE_DIR:-/opt/medbot-corpus/structured_database}"

validate_deploy_value "VPS" "$VPS"
validate_deploy_value "LOCAL" "$LOCAL"
validate_deploy_value "REMOTE_DIR" "$REMOTE_DIR"

echo "Local:  $LOCAL"
echo "Remote: $VPS:$REMOTE_DIR"
ssh -- "$VPS" mkdir -p -- "$REMOTE_DIR"
rsync -avz --delete \
  --exclude '.pytest_cache' \
  --exclude '__pycache__' \
  --exclude '*.pdf' \
  "$LOCAL/" "$VPS:$REMOTE_DIR/"
ssh -- "$VPS" mkdir -p -- /opt/medbot-corpus
ssh -- "$VPS" chmod -R a+rX -- /opt/medbot-corpus
echo "Done."
