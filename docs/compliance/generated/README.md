# Generated compliance fragments

These Markdown (and JSON) fragments under this directory are produced by
scripts — **do not edit by hand**.

| Generator | Outputs | When |
|-----------|---------|------|
| `compliance/opa/scripts/gen_doc_tables.py` | `*_articles.md` (GDPR/CRA include **Fix by**); `*_article_texts.md` (EUR-Lex excerpts from `compliance/opa/legal/*.yaml`) | After Rego catalogue edits or legal YAML refresh (`make compliance-doc-tables`) |
| `compliance/opa/scripts/fetch_legal_texts.py` | `compliance/opa/legal/*.yaml` | `make compliance-legal-texts` (Cellar / EUR-Lex) |
| `compliance/opa/scripts/gen_doc_results.py` | `latest_results.md`, `*_results.md`, `*_reviewer_checklist.md`, `legal_review_checklist.md`, `latest_report.json` | After every `make audit-compliance` / end of `make ci` |

Included into MkDocs via `pymdownx.snippets`
(`--8<-- "./docs/compliance/generated/…"`).
