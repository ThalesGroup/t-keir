# -*- coding: utf-8 -*-
"""Pull embedding / LLM / reranker models for the configured provider."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from thot.core.LlmWrapper import UnifiedLLMWrapper, WrapperConfig
from thot.tools.search.rag_config import load_rag_config

LOGGER = logging.getLogger(__name__)


async def _run(*, include_reranker: bool) -> int:
    """Pull configured Ollama models and exit with status code."""
    config = WrapperConfig.from_env()
    LOGGER.info(
        "Pulling models provider=%s embedding=%s llm=%s reranker=%s",
        config.provider.value,
        config.embedding_model,
        config.llm_model,
        config.reranker_model if include_reranker else "(skipped)",
    )
    async with UnifiedLLMWrapper(config) as llm:
        await llm.verify_provider(
            pull_missing=True,
            include_reranker=include_reranker,
        )
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m thot.tools.search.pull_models``.

    Example:
        >>> main(["--help"])  # doctest: +SKIP
        0
    """
    parser = argparse.ArgumentParser(
        description=(
            "Ensure search/index models are present "
            "(env → configs/rag.yaml → defaults). "
            "For Ollama: pulls embedding, llm, and reranker via /api/pull."
        )
    )
    parser.add_argument(
        "--skip-reranker",
        action="store_true",
        help="Do not pull the configured reranker model",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    include_reranker = (
        not args.skip_reranker and load_rag_config().search.rerank.enabled
    )
    return asyncio.run(_run(include_reranker=include_reranker))


if __name__ == "__main__":
    sys.exit(main())
