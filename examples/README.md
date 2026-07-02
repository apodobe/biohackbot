# Examples

Try **medbots** without your own PDFs using the synthetic demo corpus.

## Quick start (no PDF files)

From the repository root (with `pip install -e .` done):

```bash
medbots structure --bot-root examples/demo-instance
medbots pipeline --bot-root examples/demo-instance
medbots validate --corpus examples/demo-instance/structured_database
```

Expected: **3** `doc_text/*.md` files (EMIAS, Medsi, Gemotest biochemistry), **~46** rows in `LABS_NORMALIZED.json`.

The demo uses redacted `pdf_text/` fixtures only — see `structured_database/manifest.json` (`meta.demo: true`). No binaries in `sources/`.

## Compare output

After `structure`, compare against [expected/doc_text_emias_excerpt.md](expected/doc_text_emias_excerpt.md).

## Full workflow with your PDFs

```bash
medbots init ~/my-health
# copy PDFs → sources/{emias,medsi,gemotest}/
medbots scan --bot-root ~/my-health
medbots extract-text --bot-root ~/my-health
medbots structure --bot-root ~/my-health
medbots pipeline --bot-root ~/my-health
```

See [docs/PARSERS.md](../docs/PARSERS.md).
