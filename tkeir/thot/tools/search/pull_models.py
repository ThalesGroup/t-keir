"""Title: Pull models

Pull embedding / LLM models for the configured provider.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from thot.core.LlmWrapper import UnifiedLLMWrapper, WrapperConfig

LOGGER = logging.getLogger(__name__)


async def _run() -> int:
    """Pull configured Ollama embedding / LLM models and exit with status.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(_run)
        True
    """
    config = WrapperConfig.from_env()
    LOGGER.info(
        "Pulling models provider=%s embedding=%s llm=%s "
        "(reranker=%s strategy=%s is local/HF, not Ollama-pulled)",
        config.provider.value,
        config.embedding_model,
        config.llm_model,
        config.reranker_model,
        config.rerank_strategy,
    )
    async with UnifiedLLMWrapper(config) as llm:
        await llm.verify_provider(pull_missing=True, include_reranker=False)
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI: ``python -m thot.tools.search.pull_models``.

    Example:
        >>> main(["--help"])  # doctest: +SKIP
        0
    """
    parser = argparse.ArgumentParser(
        description=(
            "Ensure search/index embedding+LLM models are present "
            "(env → configs/rag.yaml → defaults). "
            "For Ollama: pulls via /api/pull. Cross-encoder rerankers are "
            "downloaded by sentence-transformers on first use."
        )
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
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
