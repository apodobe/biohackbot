#!/usr/bin/env bash
# Bind OpenClaw gateway to loopback only and drop public UFW access to port 18789.
set -euo pipefail
VPS="${VPS:-n8n-server}"

echo "==> gateway.bind=loopback on $VPS"
ssh "$VPS" "openclaw config set gateway.bind loopback"

echo "==> Remove UFW allow rules for 18789"
ssh "$VPS" 'while ufw status numbered | grep -q "18789/tcp"; do
  num=$(ufw status numbered | grep "18789/tcp" | head -1 | sed -n "s/^\[\s*\([0-9]*\)\].*/\1/p")
  ufw --force delete "$num"
done'

echo "==> Restart gateway"
ssh "$VPS" "export XDG_RUNTIME_DIR=/run/user/0; systemctl --user restart openclaw-gateway.service"
sleep 3
ssh "$VPS" "export XDG_RUNTIME_DIR=/run/user/0; openclaw gateway status 2>&1 | grep -E 'bind=|Listening|Probe target'"

echo "Done. Dashboard only via SSH tunnel: ssh -L 18789:127.0.0.1:18789 $VPS"
