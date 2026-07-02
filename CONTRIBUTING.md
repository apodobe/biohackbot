# Contributing

Thanks for helping improve the medical corpus pipeline.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
git config core.hooksPath .githooks
chmod +x .githooks/pre-push
pytest
```

## Rules

1. **No patient data** in pull requests — use synthetic fixtures under `tests/fixtures/`.
2. **No secrets** — tokens, keys, real `.env`, personal `bot_config.json`.
3. Run `python3 scripts/check_safe_to_push.py --public` before pushing.

## Tests

Golden parser tests use redacted vendor text snippets in `tests/fixtures/pdf_text/`, not a real corpus.
