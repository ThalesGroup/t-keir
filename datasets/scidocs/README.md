# SciDocs (BEIR)

Citation-prediction IR corpus (Cohan et al. / SPECTER). Large files are
**not** committed — download them locally:

```bash
bash datasets/scidocs/download.sh
# or
make scidocs-download
```

| Path | Tracked? | Role |
|------|----------|------|
| `business_ontology.yaml` | yes | Dual-hybrid ontology |
| `download.sh` | yes | Fetches BEIR zip + extracts here |
| `corpus.jsonl` | no (~245 MiB) | Documents |
| `queries.jsonl` | no | Test queries |
| `qrels/` | no | Relevance judgments |

`make beir-eval` / `ensure_dataset("scidocs")` also download on demand if
`corpus.jsonl` is missing.
