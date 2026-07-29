"""Deprecated shim — use ``thot.tasks.answer_generation.rag_answer``."""

from thot.tasks.answer_generation.rag_answer import *  # noqa: F403
from thot.tasks.answer_generation.rag_answer import (  # noqa: F401
    PassageHit,
    RagAnswerResult,
    answer_from_passages,
    build_rag_prompts,
    build_unique_qa_prompt,
    structure_passages,
)
