"""Title: Answer generation package.

NLP/ontology-grounded QA prompt assembly used by generate-eval and RAG
retrieval enrichment.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tasks.answer_generation.ontology_clues import (
    OntologyClueBundle,
    build_ontology_clues,
    format_clues_for_prompt,
    generate_sparql_from_query_ontology,
)
from thot.tasks.answer_generation.query_enrichment import enrich_first_stage_runs
from thot.tasks.answer_generation.rag_answer import (
    PassageHit,
    RagAnswerResult,
    answer_from_passages,
    build_rag_prompts,
    structure_passages,
)

__all__ = [
    "OntologyClueBundle",
    "PassageHit",
    "RagAnswerResult",
    "answer_from_passages",
    "build_ontology_clues",
    "build_rag_prompts",
    "enrich_first_stage_runs",
    "format_clues_for_prompt",
    "generate_sparql_from_query_ontology",
    "structure_passages",
]
