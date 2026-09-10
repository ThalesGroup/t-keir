"""Title: Spacy Model Loader

Load spaCy models by language with multilingual fallback and a process-wide
cache so tokenizer / morphosyntax / NER / syntax do not each keep a full copy
of ``en_core_web_md`` in RAM (a common cause of ingest OOM / exit 137).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

import spacy
from spacy.language import Language

from thot.core.SentenceSegmenter import normalize_language_code
from thot.core.ThotLogger import ThotLogger
from thot.core.TkeirPaths import spacy_models_dir

MULTILINGUAL_MODEL = "xx_ent_wiki_sm"

# Official spaCy 3.6 trained pipelines (core_news / core_web). Arabic has no
# Explosion pipeline in 3.6 — use ``spacy.blank("ar")`` instead of xx NER.
TRAINED_PIPELINE_LANGUAGES = frozenset(
    {
        "ca",
        "da",
        "de",
        "el",
        "en",
        "es",
        "fi",
        "fr",
        "hr",
        "it",
        "ja",
        "ko",
        "lt",
        "mk",
        "nb",
        "nl",
        "pl",
        "pt",
        "ro",
        "ru",
        "sl",
        "sv",
        "uk",
        "zh",
    }
)
BLANK_PREFERRED_LANGUAGES = frozenset({"ar"})

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


def blank_model_name(language: str | None) -> str:
    """Return the cache key for a blank spaCy language pipeline.

    Example:
        >>> from thot.core.SpacyModelLoader import blank_model_name
        >>> blank_model_name("AR")
        'blank:ar'
    """
    return "blank:" + normalize_language_code(language)


def resolve_spacy_load_name(
    model_name: str, models_dir: str | None = None
) -> str:
    """Return a filesystem path or package name for ``spacy.load``.

    Prefers ``resources/modeling/spacy/<name>/`` (setup/install), then a
    pip-installed package name.

    Args:
        model_name: spaCy pipeline name such as ``en_core_web_sm``.
        models_dir: Optional override for the spaCy resources directory.

    Returns:
        Absolute model directory, or ``model_name`` for package / blank loads.

    Example:
        >>> from thot.core.SpacyModelLoader import resolve_spacy_load_name
        >>> resolve_spacy_load_name("blank:ar")
        'blank:ar'
        >>> isinstance(resolve_spacy_load_name("en_core_web_sm"), str)
        True
    """
    name = (model_name or "").strip()
    if not name or name.startswith("blank:"):
        return name
    root = Path(models_dir or spacy_models_dir()) / name
    if (root / "config.cfg").is_file():
        return str(root)
    if root.is_dir():
        versioned = sorted(root.glob(name + "-*/config.cfg"))
        if versioned:
            return str(versioned[-1].parent)
        nested = root / name / "config.cfg"
        if nested.is_file():
            return str(nested.parent)
    return name


def spacy_model_is_available(model_name: str) -> bool:
    """Return True when a named spaCy pipeline can be loaded.

    Example:
        >>> from thot.core.SpacyModelLoader import spacy_model_is_available
        >>> isinstance(spacy_model_is_available("en_core_web_sm"), bool)
        True
    """
    name = (model_name or "").strip()
    if not name:
        return False
    if name.startswith("blank:"):
        return True
    resolved = resolve_spacy_load_name(name)
    if resolved != name:
        return True
    import importlib.util

    return importlib.util.find_spec(name) is not None


def _load_blank_language(
    language: str,
    call_context=None,
    task_name: str | None = None,
) -> Language:
    """Build ``spacy.blank(lang)`` with a sentencizer (no trained weights).

    Example:
        >>> from thot.core.SpacyModelLoader import _load_blank_language
        >>> nlp = _load_blank_language("ar")
        >>> nlp.lang
        'ar'
    """
    prefix = (task_name + ": ") if task_name else ""
    lang = normalize_language_code(language)
    cache_key = blank_model_name(lang)
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached
        ThotLogger.info(
            prefix + "Loading blank spaCy language " + lang + " ...",
            context=call_context,
        )
        nlp = spacy.blank(lang)
        if "sentencizer" not in nlp.pipe_names:
            nlp.add_pipe("sentencizer")
        _MODEL_CACHE[cache_key] = nlp
        return nlp


def _download_spacy_model(
    model_name: str,
    call_context=None,
    task_name: str | None = None,
) -> None:
    """Download a spaCy model into ``resources/modeling/spacy``.

    Example:
        >>> _download_spacy_model("en_core_web_sm")  # doctest: +SKIP
    """
    prefix = (task_name + ": ") if task_name else ""
    ThotLogger.info(
        prefix
        + "spaCy model "
        + model_name
        + " is not installed; downloading into resources/modeling/spacy",
        context=call_context,
    )
    started = time.perf_counter()
    from thot.tools.install_spacy_models import install_one_model

    install_one_model(model_name, force=True)
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
        source = resolve_spacy_load_name(model_name)
        nlp = spacy.load(source)
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
    lang = normalize_language_code(language)
    if lang in BLANK_PREFERRED_LANGUAGES:
        try:
            nlp = _load_blank_language(lang, call_context, task_name)
            return nlp, blank_model_name(lang)
        except Exception as error:
            last_error = OSError(str(error))
            ThotLogger.debug(
                "spaCy blank language failed: " + lang,
                context=call_context,
            )
    candidates = model_name_candidates(language, size=size)
    trained = [name for name in candidates if name != MULTILINGUAL_MODEL]
    primary_model = trained[0] if trained else ""
    for model_name in trained:
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
                try:
                    _download_spacy_model(model_name, call_context, task_name)
                    nlp = _load_model(model_name, call_context, task_name)
                    return nlp, model_name
                except Exception as download_error:
                    last_error = OSError(str(download_error))

    try:
        nlp = _load_model(MULTILINGUAL_MODEL, call_context, task_name)
        return nlp, MULTILINGUAL_MODEL
    except OSError as error:
        last_error = error

    message = (
        "No spaCy model available for language "
        + lang
        + " (tried "
        + ", ".join(model_name_candidates(language, size=size))
        + "). Install models with: "
        + "make install-spacy-models "
        + "(extracts wheels into tkeir/resources/modeling/spacy)"
    )
    raise OSError(message) from last_error
