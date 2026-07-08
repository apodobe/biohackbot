# Security

## Public repository policy

**Never commit to this public repo:**

- API keys, bot tokens, real `.env` files
- `bot_config.json` with instance-specific paths
- Patient data: labs, genetics, clinical notes, `PATIENT_PROFILE.json`, `pdf_text/`, `doc_text/`
- Raw PDFs in `sources/` or `incoming/`

Keep health data in a local or private instance directory (see README).

## Automated controls

| Control | Purpose |
|---------|---------|
| `scripts/check_safe_to_push.py --public --push` | Pre-push hook: scans outgoing commits (not just staged files) |
| `scripts/check_safe_to_push.py --public --scan-all` | CI: scans all tracked files |
| `.github/workflows/secret-scan.yml` | Gitleaks + path blocks + dependency audit |
| `.gitleaks.toml` | Allowlist for mock fixtures only |
| `deploy/lib/validate-deploy-path.sh` | Blocks shell metacharacter injection in deploy vars |

Install hooks after clone:

```bash
git config core.hooksPath .githooks
```

## Private VPS / Telegram bot

- Store tokens in `~/.config/medbot-openclaw.env` with `chmod 600`
- Set `TELEGRAM_ALLOWED_USER_IDS` — never run the bot open to all Telegram users
- Corpus on VPS: `/opt/medbot-corpus` — restrict SSH and filesystem permissions
- Do not expose corpus directory via HTTP without authentication

## Reporting

Report vulnerabilities via [GitHub Security Advisories](https://github.com/apodobe/biohackbot/security/advisories/new) — without attaching PHI or tokens.
