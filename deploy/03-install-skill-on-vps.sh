#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib/validate-deploy-path.sh
source "$SCRIPT_DIR/lib/validate-deploy-path.sh"

VPS="${VPS:-n8n-server}"
SKILL_SRC="$(cd "$(dirname "$0")" && pwd)/skills/biohacking-corpus"
REMOTE_SKILLS="${REMOTE_SKILLS:-/root/.openclaw/workspace/skills}"

validate_deploy_value "VPS" "$VPS"
validate_deploy_value "REMOTE_SKILLS" "$REMOTE_SKILLS"

echo "Install skill: $SKILL_SRC -> $VPS:$REMOTE_SKILLS/biohacking-corpus/"
ssh -- "$VPS" mkdir -p -- "$REMOTE_SKILLS/biohacking-corpus"
rsync -avz "$SKILL_SRC/" "$VPS:$REMOTE_SKILLS/biohacking-corpus/"
ssh -- "$VPS" chmod +x -- "$REMOTE_SKILLS/biohacking-corpus/"*.sh 2>/dev/null || true
echo "Done. Restart OpenClaw gateway if needed."
