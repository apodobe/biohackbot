# Demo instance (synthetic mock patient)

Pre-built manifest + `pdf_text/` for three vendors. **No PDF files required.**

Mock patient: **John Smith**, USA (`PATIENT_PROFILE.json`).

```bash
# from repo root
medbots structure --bot-root examples/demo-instance
medbots pipeline --bot-root examples/demo-instance
```

| Vendor | Fixture | doc_type |
|--------|---------|----------|
| EMIAS | biochemistry panel | lab |
| Medsi | biochemistry panel | lab |
| Gemotest | 19-parameter biochemistry | lab |

Medsi entry includes `user_drop_batch: true` (required by the Medsi parser gate in `local_structure_pdfs`).

Text fixtures are copied from `tests/fixtures/pdf_text/` (synthetic extracts with mock PII).
