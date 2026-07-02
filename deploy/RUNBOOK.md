# VPS deploy (optional)

Sync **text and JSON only** — no PDF binaries.

## Prerequisites

- SSH access to your VPS
- Local instance with `structured_database/` populated (`medbots pipeline` done)

## Variables

```bash
export VPS=root@YOUR_HOST
export CORPUS=$HOME/my-health/structured_database   # local corpus path
```

## Sync corpus

```bash
cd deploy
./02-rsync-corpus.sh
```

## OpenClaw skill (optional Q&A bot)

```bash
./03-install-skill-on-vps.sh
```

Copy and fill env template on the server:

```bash
cp deploy/openclaw.env.example ~/.config/medbot-openclaw.env
# set TELEGRAM token and allowed user IDs
```

Skill reads corpus from `/opt/medbot-corpus/structured_database` (adjust in `02-rsync-corpus.sh` if needed).

**LLM tier for Q&A:** see [docs/LLM_GUIDE.md](../docs/LLM_GUIDE.md). Default private deploy uses `xai/grok-4.3` for the biohacking agent; preset brief buttons should stay script-only (no model).
