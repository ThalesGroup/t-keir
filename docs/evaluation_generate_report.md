# Generation Evaluation Report

_Generated 2026-07-28 12:37 UTC_

T-KEIR-only **generation** eval on `datasets/rag_benchmarks/`: oracle evidence → NLP → merged query/passage ontology → unique type-aware prompt → LLM answer. No retrieval. Compared to `leaderboard.yaml`.

## Summary vs leaderboard

| Dataset | Metric | T-KEIR | Published | Gap |
|---------|--------|-------:|----------:|----:|
| MultiHop-RAG | Acc (contains) | 0.729 | 0.890 (GPT-4 (ground-truth evidence)) | -0.161 |

\* RAGBench published Hal AUROC is a *judge* metric — reference only.

## Per-dataset generation metrics

### MultiHop-RAG (`multihop`)

Evidence passages **6,084** · queries **2,255** · errors **0**

| EM | Token F1 | Contains-gold |
|---:|---------:|--------------:|
| 0.532 | 0.558 | 0.729 |

**Sample answers**

- Q: Who is the individual associated with the cryptocurrency industry facing a criminal trial on fraud and conspiracy charges, as reported by both The Verge and Tec
  - gold: `Sam Bankman-Fried`
  - pred: `Sam Bankman-Fried` (F1=1.000)
- Q: Which individual is implicated in both inflating the value of a Manhattan apartment to a figure not yet achieved in New York City's real estate history, accordi
  - gold: `Donald Trump`
  - pred: `The information is not available.` (F1=0.000)
- Q: Who is the figure associated with generative AI technology whose departure from OpenAI was considered shocking according to Fortune, and is also the subject of 
  - gold: `Sam Altman`
  - pred: `Arun Chandrasekaran` (F1=0.024)

## Method

1. Use dataset oracle evidence only (`evidence_list` facts / RAGBench `documents`).
2. Full NLP analysis of the request + passage SVO.
3. Merge query+passage SVO into one ontology; optional reasoner.
4. Detect question type (yes/no, wh-, inference, …).
5. Build one unique type-aware QA prompt with relevant ontology facts.
6. Generate SHORT_ANSWER / DETAILED_REPORT via a single LLM call.
7. Score EM / token-F1 / contains-gold vs dataset answers.
