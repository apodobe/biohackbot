# Security Policy

## Never publish

- API keys, bot tokens, private keys, `.env` files (except `*.env.example` with placeholders)
- `bot_config.json` with real VPS paths or instance secrets
- Patient health data: lab values, genetics, clinical notes, `PATIENT_PROFILE.json`, `LABS_NORMALIZED.json`, `pdf_text/`, `doc_text/`
- Raw PDFs in `sources/`

This **public** repository is for framework code only. Keep your corpus in a private clone or local directory.

## Before every push

```bash
python3 scripts/check_safe_to_push.py --public
```

Enable hooks: `git config core.hooksPath .githooks`

## Reporting vulnerabilities

Open a [GitHub Security Advisory](https://github.com/apodobe/biohackbot/security/advisories/new) or contact the maintainer via GitHub — **do not** include PHI or live tokens in the report.
