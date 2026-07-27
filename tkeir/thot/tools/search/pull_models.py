"""Title: Pull models

Download FlagEmbedding BGE-M3 into ``resources/modeling/net/bge-m3``
(project tree — not the Hugging Face hub cache), and optionally pull
Ollama LLM / embedding models.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

from thot.core.LlmWrapper import UnifiedLLMWrapper, WrapperConfig
from thot.core.TkeirPaths import bge_m3_model_dir, net_models_dir
from thot.tools.search.bge_m3 import local_bge_m3_ready

LOGGER = logging.getLogger(__name__)

_DEFAULT_BGE_HF_ID = "BAAI/bge-m3"
_BGE_HF_ALIASES = {
    "bge-m3": _DEFAULT_BGE_HF_ID,
    "bge_m3": _DEFAULT_BGE_HF_ID,
    "BAAI/bge-m3": _DEFAULT_BGE_HF_ID,
}


def resolve_bge_hf_model_id(model_id: str | None = None) -> str:
    """Resolve the Hugging Face *source* repo id used only for first download."""
    raw = (model_id or os.getenv("EMBEDDING_MODEL") or "").strip()
    if not raw:
        try:
            from thot.tools.search.rag_config import load_rag_config

            raw = (load_rag_config().models.embedding_model or "").strip()
        except Exception:  # noqa: BLE001
            raw = ""
    if not raw or os.path.isdir(raw):
        return _DEFAULT_BGE_HF_ID
    return _BGE_HF_ALIASES.get(raw, raw if "/" in raw else _DEFAULT_BGE_HF_ID)


def pull_bge_embedding_model(
    model_id: str | None = None,
    *,
    force: bool = False,
) -> str:
    """Download BGE-M3 into ``resources/modeling/net/bge-m3``.

    Does **not** use or rely on the default Hugging Face hub cache for runtime.
    A temporary download cache under ``net/.download_cache`` is used during
    fetch, then removed.

    Args:
        model_id: Optional HF source repo id (default ``BAAI/bge-m3``).
        force: Re-download even when ``net/bge-m3`` already exists.

    Returns:
        Absolute path to the local model directory.
    """
    dest = Path(bge_m3_model_dir())
    if not force and local_bge_m3_ready(str(dest)):
        LOGGER.warning(
            "BGE-M3 already present at %s — skipping download. "
            "Pass --force-bge (or FORCE_BGE=1) to refresh.",
            dest,
        )
        return str(dest)

    repo_id = resolve_bge_hf_model_id(model_id)
    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "huggingface_hub is required to download BGE-M3. "
            "Install project deps with: make install"
        ) from exc

    Path(net_models_dir()).mkdir(parents=True, exist_ok=True)
    download_cache = Path(net_models_dir()) / ".download_cache"
    download_cache.mkdir(parents=True, exist_ok=True)

    if force and dest.exists():
        LOGGER.info("Removing existing BGE-M3 at %s …", dest)
        shutil.rmtree(dest)

    LOGGER.info(
        "Downloading %s → %s (temporary cache %s) …",
        repo_id,
        dest,
        download_cache,
    )
    # Keep blobs out of the user HF hub cache (~/.cache/huggingface).
    path = snapshot_download(
        repo_id=repo_id,
        local_dir=str(dest),
        cache_dir=str(download_cache),
    )
    # Drop ephemeral hub cache under resources/modeling/net/
    if download_cache.exists():
        shutil.rmtree(download_cache, ignore_errors=True)
    if not local_bge_m3_ready(str(dest)):
        raise RuntimeError(
            f"Download finished but config.json missing under {dest}"
        )
    LOGGER.info("BGE-M3 ready at %s", path)
    return str(dest)


async def _run_ollama() -> int:
    """Pull configured Ollama embedding / LLM models and exit with status."""
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
    """CLI: ``python -m thot.tools.search.pull_models``."""
    parser = argparse.ArgumentParser(
        description=(
            "Download BGE-M3 into resources/modeling/net/bge-m3 "
            "(not the Hugging Face hub cache). "
            "Unless --bge-only, also pulls Ollama LLM/embedding when configured."
        )
    )
    parser.add_argument(
        "--bge-only",
        action="store_true",
        help="Only ensure local BGE-M3 under resources/modeling/net; skip Ollama",
    )
    parser.add_argument(
        "--skip-bge",
        action="store_true",
        help="Skip BGE download (Ollama pulls only)",
    )
    parser.add_argument(
        "--bge-model",
        default=None,
        help=f"Source Hugging Face repo id (default: {_DEFAULT_BGE_HF_ID})",
    )
    parser.add_argument(
        "--force-bge",
        action="store_true",
        help="Re-download into resources/modeling/net/bge-m3 even if present",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Debug logging",
    )
    args = parser.parse_args(argv)
    from thot.core.StructuredLogging import configure_text_logging

    configure_text_logging(
        level=logging.DEBUG if args.verbose else logging.INFO,
        force=True,
    )
    if not args.skip_bge:
        pull_bge_embedding_model(args.bge_model, force=args.force_bge)
    if args.bge_only:
        return 0
    return asyncio.run(_run_ollama())


if __name__ == "__main__":
    sys.exit(main())
