"""Title: Spacy Model Loader

Load spaCy models by language with multilingual fallback and a process-wide
cache so tokenizer / morphosyntax / NER / syntax do not each keep a full copy
of ``en_core_web_md`` in RAM (a common cause of ingest OOM / exit 137).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time

import spacy
from spacy.language import Language

from thot.core.SentenceSegmenter import normalize_language_code
from thot.core.ThotLogger import ThotLogger

MULTILINGUAL_MODEL = "xx_ent_wiki_sm"

# English uses core_web; most other spaCy models use core_news.
ENGLISH_MODEL_FAMILY = "core_web"
DEFAULT_MODEL_FAMILY = "core_news"

# Process-wide cache: model_name → Language.
# Callers may mutate tokenizer / pipes; re-entrant inits must remove/replace
# pipes (see Tokenizer / NERTagger) rather than assuming a pristine nlp.
_MODEL_CACHE: dict[str, Language] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def model_name_candidates(language: str | None, size: str = "sm") -> list[str]:
    """Return spaCy model names to try, most specific first.

    Args:
        language: Requested language or locale code.
        size: spaCy model size suffix such as ``"sm"`` or ``"md"``.

    Returns:
        Ordered list of candidate model names.

    Example:
        >>> from thot.core.SpacyModelLoader import model_name_candidates
        >>> model_name_candidates("en")[0]
        'en_core_web_sm'
        >>> model_name_candidates("fr", size="md")[0]
        'fr_core_news_md'
    """
    lang = normalize_language_code(language)
    suffix = size if size in {"sm", "md", "lg"} else "sm"
    candidates: list[str] = []

    if lang == "en":
        candidates.append(f"en_{ENGLISH_MODEL_FAMILY}_{suffix}")
    else:
        candidates.append(f"{lang}_{DEFAULT_MODEL_FAMILY}_{suffix}")
        candidates.append(f"{lang}_{ENGLISH_MODEL_FAMILY}_{suffix}")

    if suffix == "md":
        if lang == "en":
            candidates.append(f"en_{ENGLISH_MODEL_FAMILY}_sm")
        else:
            candidates.append(f"{lang}_{DEFAULT_MODEL_FAMILY}_sm")

    candidates.append(MULTILINGUAL_MODEL)
    return candidates


def _download_spacy_model(
    model_name: str,
    call_context=None,
    task_name: str | None = None,
) -> None:
    """Download a spaCy model via ``python -m spacy download``.

    Example:
        >>> _download_spacy_model("en_core_web_sm")  # doctest: +SKIP
    """
    prefix = (task_name + ": ") if task_name else ""
    ThotLogger.info(
        prefix
        + "spaCy model "
        + model_name
        + " is not installed; downloading (this may take a few minutes)",
        context=call_context,
    )
    started = time.perf_counter()
    subprocess.run(
        [sys.executable, "-m", "spacy", "download", model_name],
        check=True,
    )
    ThotLogger.info(
        prefix
        + "Downloaded spaCy model "
        + model_name
        + f" in {time.perf_counter() - started:.1f}s",
        context=call_context,
    )


def _load_model(
    model_name: str,
    call_context=None,
    task_name: str | None = None,
) -> Language:
    """Load one spaCy model (or reuse the process cache) and log timing.

    Example:
        >>> from thot.core.SpacyModelLoader import _load_model
        >>> _load_model("en_core_web_sm")  # doctest: +SKIP
    """
    prefix = (task_name + ": ") if task_name else ""
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(model_name)
        if cached is not None:
            ThotLogger.debug(
                prefix + "Reusing cached spaCy model " + model_name,
                context=call_context,
            )
            return cached

        ThotLogger.info(
            prefix + "Loading spaCy model " + model_name + " ...",
            context=call_context,
        )
        started = time.perf_counter()
        nlp = spacy.load(model_name)
        _MODEL_CACHE[model_name] = nlp
        ThotLogger.info(
            prefix
            + "Loaded spaCy model "
            + model_name
            + f" in {time.perf_counter() - started:.1f}s",
            context=call_context,
        )
        return nlp


def clear_spacy_model_cache() -> None:
    """Drop cached spaCy models (tests / memory reclaim).

    Example:
        >>> clear_spacy_model_cache() is None
        True
    """
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()


def load_spacy_model(
    language: str | None,
    size: str = "sm",
    call_context=None,
    download_if_missing: bool = False,
    task_name: str | None = None,
) -> tuple[Language, str]:
    """Load the best available spaCy model for a language.

    Args:
        language: Requested language or locale code.
        size: spaCy model size suffix such as ``"sm"`` or ``"md"``.
        call_context: Optional logging context.
        download_if_missing: When ``True``, download the primary model if missing.
        task_name: Optional pipeline task name included in log messages.

    Returns:
        Tuple of loaded spaCy language object and model name.

    Raises:
        OSError: When no candidate model can be loaded.

    Example:
        >>> from thot.core.SpacyModelLoader import load_spacy_model
        >>> load_spacy_model("en", size="sm")  # doctest: +SKIP
    """
    last_error: OSError | None = None
    candidates = model_name_candidates(language, size=size)
    primary_model = candidates[0] if candidates else ""
    for model_name in candidates:
        try:
            nlp = _load_model(model_name, call_context, task_name)
            return nlp, model_name
        except OSError as error:
            last_error = error
            ThotLogger.debug(
                "spaCy model not installed: " + model_name,
                context=call_context,
            )
            if download_if_missing and model_name == primary_model:
                _download_spacy_model(model_name, call_context, task_name)
                nlp = _load_model(model_name, call_context, task_name)
                return nlp, model_name

    message = (
        "No spaCy model available for language "
        + normalize_language_code(language)
        + " (tried "
        + ", ".join(model_name_candidates(language, size=size))
        + "). Install models with: "
        + "uv sync --directory tkeir --group models "
        + "(or: make install-spacy-models from the repo root)"
    )
    raise OSError(message) from last_error
