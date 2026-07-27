# Official EU legal texts (EUR-Lex / Cellar)

YAML sidecars keyed by the same article IDs as the OPA Rego catalogues
(`Art.5(1)`, `AnnexI.PartI.1(a)`, …). Used by `gen_doc_tables.py` to publish
exact legal excerpts next to each engineering control.

| File | Regulation | CELEX |
|------|------------|-------|
| `ai_act.yaml` | AI Act | 32024R1689 |
| `cra.yaml` | CRA | 32024R2847 |
| `gdpr.yaml` | GDPR | 32016R0679 |
| `nis2.yaml` | NIS2 | 32022L2555 |
| `dora.yaml` | DORA | 32022R2554 |
| `pld.yaml` | PLD | 32024L2853 |

Refresh from Publications Office Cellar:

```bash
python3 compliance/opa/scripts/fetch_legal_texts.py
make compliance-doc-tables
```

**Not legal advice.** Texts are © European Union (EUR-Lex). Engineering
`message` fields in Rego remain paraphrases for OPA checks.
