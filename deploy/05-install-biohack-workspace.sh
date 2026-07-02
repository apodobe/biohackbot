#!/usr/bin/env bash
# Dedicated OpenClaw workspace for biohacking agent (no LinkedIn/n8n context).
set -euo pipefail
VPS="${VPS:-n8n-server}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REMOTE_WS="${REMOTE_WS:-/root/.openclaw/workspace-biohacking}"

echo "==> Install biohacking workspace -> $VPS:$REMOTE_WS"
ssh "$VPS" "mkdir -p '$REMOTE_WS'"
rsync -avz "$SCRIPT_DIR/workspace-biohacking/" "$VPS:$REMOTE_WS/"

echo "==> Point biohacking agent to isolated workspace"
ssh "$VPS" "REMOTE_WS='$REMOTE_WS' python3 -" <<'PY'
import json
from pathlib import Path

cfg_path = Path("/root/.openclaw/openclaw.json")
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
remote_ws = Path("/root/.openclaw/workspace-biohacking")

for agent in cfg.get("agents", {}).get("list", []):
    if agent.get("id") == "biohacking":
        agent["workspace"] = str(remote_ws)
        theme = (
            "Изолированный workspace biohacking; корпус /opt/medbot-corpus/structured_database; "
            "skill biohacking-corpus; кнопки TELEGRAM_RESEARCH_BRIEFS — только stdout скрипта; "
            "не LinkedIn/n8n"
        )
        agent.setdefault("identity", {})["theme"] = theme
        break
else:
    raise SystemExit("biohacking agent not found in openclaw.json")

cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("biohacking workspace =", remote_ws)
PY

echo "==> Clear polluted biohacking sessions (optional fresh context)"
ssh "$VPS" "rm -f /root/.openclaw/agents/biohacking/sessions/*.json 2>/dev/null || true"

echo "Done. Restart: systemctl --user restart openclaw-gateway.service"
