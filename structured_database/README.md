# structured_database (local only)

This directory holds your **private** prepared health corpus (`pdf_text/`, `doc_text/`, JSON, prompts).

**Do not commit patient data to the public [biohackbot](https://github.com/apodobe/biohackbot) repository.**

Create `structured_database/` locally (or in a private fork) and point tools at it:

```bash
export MEDBOTS_CORPUS_PATH=/path/to/your/structured_database
```

Schema and required files: [docs/MED_BOTS_CORPUS_STANDARD.md](../docs/MED_BOTS_CORPUS_STANDARD.md).
