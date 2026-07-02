#!/usr/bin/env bash
# Configure @your_medbot in OpenClaw: agent biohacking + telegram account + allowlist.
set -euo pipefail
VPS="${VPS:-n8n-server}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${BIOHACK_OPENCLAW_ENV:-/root/.config/biohack-openclaw.env}"

echo "==> Install biohacking agent identity"
ssh "$VPS" "mkdir -p /root/.openclaw/agents/biohacking/agent /root/.openclaw/agents/biohacking/sessions"
scp -q "$SCRIPT_DIR/agents/biohacking-IDENTITY.md" "$VPS:/root/.openclaw/agents/biohacking/agent/IDENTITY.md"

echo "==> Patch openclaw.json (reads $ENV_FILE on VPS)"
ssh "$VPS" "ENV_FILE='$ENV_FILE' python3 -" <<'PY'
import json
import os
import re
from pathlib import Path

env_path = Path(os.environ["ENV_FILE"])
if not env_path.exists():
    raise SystemExit(f"Missing {env_path} — create from biohack-openclaw.env.example")

env: dict[str, str] = {}
for line in env_path.read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    env[k.strip()] = v.strip()

token = env.get("TELEGRAM_BIOHACK_BOT_TOKEN", "").strip()
if not token:
    raise SystemExit("TELEGRAM_BIOHACK_BOT_TOKEN is empty in env file")

raw_ids = env.get("TELEGRAM_BIOHACK_ALLOWED_USER_IDS", "YOUR_TELEGRAM_USER_ID")
allowed = [int(x) for x in re.split(r"[\s,;]+", raw_ids) if x.strip().isdigit()]
if not allowed:
    raise SystemExit("TELEGRAM_BIOHACK_ALLOWED_USER_IDS must list at least one numeric user id")

cfg_path = Path("/root/.openclaw/openclaw.json")
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))

agents = cfg.setdefault("agents", {})
agent_list = agents.setdefault("list", [])
if not any(a.get("id") == "biohacking" for a in agent_list):
    agent_list.append(
        {
            "id": "biohacking",
            "name": "biohacking",
            "workspace": "/root/.openclaw/workspace-biohacking",
            "agentDir": "/root/.openclaw/agents/biohacking/agent",
            "model": "xai/grok-4.3",
            "identity": {
                "name": "BioHackBot",
                "theme": (
                    "Корпус /opt/medbot-corpus/structured_database; skill biohacking-corpus; "
                    "всегда по-русски; не врач; только факты из файлов; session biohack:corpus"
                ),
            },
        }
    )
else:
    for agent in agent_list:
        if agent.get("id") == "biohacking":
            agent["workspace"] = "/root/.openclaw/workspace-biohacking"
            agent.setdefault("identity", {})["theme"] = (
                "Изолированный workspace biohacking; корпус /opt/medbot-corpus/structured_database; "
                "skill biohacking-corpus; кнопки TELEGRAM_RESEARCH_BRIEFS — только stdout скрипта"
            )
            break

bindings = cfg.setdefault("bindings", [])
if not any(
    b.get("agentId") == "biohacking"
    and (b.get("match") or {}).get("accountId") == "biohacking"
    for b in bindings
):
    bindings.append(
        {
            "type": "route",
            "agentId": "biohacking",
            "match": {"channel": "telegram", "accountId": "biohacking"},
        }
    )

tg = cfg.setdefault("channels", {}).setdefault("telegram", {})
accounts = tg.setdefault("accounts", {})
accounts["biohacking"] = {
    "name": "biohacking",
    "dmPolicy": "allowlist",
    "botToken": token,
    "groupPolicy": "allowlist",
    "streaming": {"mode": "partial"},
    "allowFrom": allowed,
    "groupAllowFrom": [str(x) for x in allowed],
}

cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("openclaw.json updated: agent=biohacking account=biohacking allowFrom=", allowed)
PY

echo "==> Restart OpenClaw gateway"
ssh "$VPS" "export XDG_RUNTIME_DIR=/run/user/0; systemctl --user restart openclaw-gateway.service"
sleep 3
ssh "$VPS" "export XDG_RUNTIME_DIR=/run/user/0; openclaw gateway status 2>&1 | head -20"
echo "Done. Test: message @your_medbot /start from Telegram user ${TELEGRAM_BIOHACK_ALLOWED_USER_IDS:-YOUR_TELEGRAM_USER_ID}"
