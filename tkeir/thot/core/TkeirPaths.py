"""Title: Tkeir Paths

Resolve bundled T-KEIR configuration and resource paths.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os

_PATH_KEYS = ("resources-base-path",)


def package_root() -> str:
    """Return the absolute path to the ``tkeir`` package root.

    Returns:
        Absolute directory containing ``thot/``, ``configs/``, and ``resources/``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import package_root
        >>> root = package_root()
        >>> os.path.isdir(os.path.join(root, "thot"))
        True
    """
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))


def configs_dir() -> str:
    """Return the bundled configuration directory.

    Returns:
        Absolute path to ``tkeir/configs``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import configs_dir
        >>> os.path.isfile(os.path.join(configs_dir(), "pipeline.yaml"))
        True
    """
    return os.path.join(package_root(), "configs")


def resources_dir(language: str = "en") -> str:
    """Return tokenizer resources for a language or the shared ``any`` pack.

    Args:
        language: ISO language code (for example ``"en"`` or ``"fr"``),
            or ``"any"`` for language-agnostic gazetteers.

    Returns:
        Absolute path to ``resources/modeling/tokenizer/<language>``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import resources_dir
        >>> os.path.isdir(resources_dir("en"))
        True
        >>> os.path.isdir(resources_dir("any"))
        True
    """
    return os.path.join(
        package_root(), "resources", "modeling", "tokenizer", language
    )


SHARED_TOKENIZER_LANGUAGE = "any"
DEFAULT_MWE_FILENAME = "tkeir_mwe.pkl"


def shared_resources_dir() -> str:
    """Return the language-agnostic tokenizer gazetteer directory.

    Example:
        >>> from thot.core.TkeirPaths import shared_resources_dir
        >>> shared_resources_dir().endswith("tokenizer/any")
        True
    """
    return resources_dir(SHARED_TOKENIZER_LANGUAGE)


def resolve_mwe_path(
    resources_base_path: str | None,
    mwe_filename: str = DEFAULT_MWE_FILENAME,
) -> str | None:
    """Locate the compiled MWE pickle in ``tokenizer/any``, then a language dir.

    The shared gazetteer trie is the default. A pickle in the language
    directory is used only when the shared file is missing.

    Args:
        resources_base_path: Language-specific tokenizer resources directory.
        mwe_filename: Pickle basename (default ``tkeir_mwe.pkl``).

    Returns:
        Absolute path of the first existing pickle, or ``None``.

    Example:
        >>> from thot.core.TkeirPaths import resolve_mwe_path, shared_resources_dir
        >>> import os
        >>> found = resolve_mwe_path(shared_resources_dir())
        >>> found is None or found.endswith("tkeir_mwe.pkl")
        True
    """
    name = mwe_filename or DEFAULT_MWE_FILENAME
    candidates: list[str] = []
    shared = os.path.join(shared_resources_dir(), name)
    candidates.append(shared)
    if resources_base_path:
        lang_path = os.path.join(resources_base_path, name)
        if lang_path not in candidates:
            candidates.append(lang_path)
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


def net_models_dir() -> str:
    """Return the local neural model directory (not Hugging Face hub cache).

    Returns:
        Absolute path to ``resources/modeling/net``.

    Example:
        >>> from thot.core.TkeirPaths import net_models_dir
        >>> net_models_dir().endswith("resources/modeling/net")
        True
    """
    return os.path.join(package_root(), "resources", "modeling", "net")


def spacy_models_dir() -> str:
    """Return the on-disk spaCy pipeline directory.

    Override with ``TKEIR_SPACY_MODELS_DIR`` (tests / custom layouts).
    Models are downloaded by ``make install-spacy-models`` / ``make setup``.

    Returns:
        Absolute path to ``resources/modeling/spacy``.

    Example:
        >>> from thot.core.TkeirPaths import spacy_models_dir
        >>> spacy_models_dir().endswith("resources/modeling/spacy")
        True
    """
    override = os.environ.get("TKEIR_SPACY_MODELS_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(package_root(), "resources", "modeling", "spacy")


def bge_m3_model_dir() -> str:
    """Return the on-disk BGE-M3 directory under ``resources/modeling/net``.

    Returns:
        Absolute path to ``resources/modeling/net/bge-m3``.

    Example:
        >>> from thot.core.TkeirPaths import bge_m3_model_dir
        >>> bge_m3_model_dir().endswith("resources/modeling/net/bge-m3")
        True
    """
    return os.path.join(net_models_dir(), "bge-m3")


def tessdata_dir() -> str:
    """Return the bundled Tesseract ``*.traineddata`` directory.

    Override with ``TKEIR_TESSDATA_DIR``. Downloaded by
    ``make install-converter-models`` / ``make setup``.

    Returns:
        Absolute path to ``resources/modeling/tesseract``.

    Example:
        >>> from thot.core.TkeirPaths import tessdata_dir
        >>> tessdata_dir().endswith("resources/modeling/tesseract")
        True
    """
    override = os.environ.get("TKEIR_TESSDATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    return os.path.join(package_root(), "resources", "modeling", "tesseract")


def blip_model_dir() -> str:
    """Return the local BLIP captioning directory under ``net``.

    Returns:
        Absolute path to ``resources/modeling/net/blip-image-captioning-base``.

    Example:
        >>> from thot.core.TkeirPaths import blip_model_dir
        >>> blip_model_dir().endswith(
        ...     "resources/modeling/net/blip-image-captioning-base"
        ... )
        True
    """
    return os.path.join(net_models_dir(), "blip-image-captioning-base")


def ontologies_dir() -> str:
    """Return the bundled generic ontologies directory.

    Application / corpus ontologies must not live here — upload them at
    ingest time. Only product-neutral reference graphs belong under
    ``resources/ontologies/``.

    Returns:
        Absolute path to ``resources/ontologies``.

    Example:
        >>> from thot.core.TkeirPaths import ontologies_dir
        >>> ontologies_dir().endswith("resources/ontologies")
        True
    """
    return os.path.join(package_root(), "resources", "ontologies")


def repo_root() -> str:
    """Return the repository root (parent of the ``tkeir`` package).

    Returns:
        Absolute path to the git repository root.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import repo_root, vespa_dir
        >>> os.path.isdir(vespa_dir())
        True
        >>> vespa_dir().startswith(repo_root())
        True
    """
    return os.path.abspath(os.path.join(package_root(), ".."))


def vespa_dir() -> str:
    """Return the Vespa deployment directory.

    Returns:
        Absolute path to ``vespa/`` at the repository root.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import vespa_dir
        >>> os.path.isdir(vespa_dir())
        True
        >>> os.path.isfile(os.path.join(vespa_dir(), "start_vespa.sh"))
        True
    """
    return os.path.join(repo_root(), "vespa")


def rag_prompts_path() -> str:
    """Return the RAG prompt template file used by the search API.

    Returns:
        Absolute path to ``configs/rag-prompts.yaml``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import rag_prompts_path
        >>> os.path.isfile(rag_prompts_path())
        True
    """
    return os.path.join(configs_dir(), "rag-prompts.yaml")


def rag_config_path() -> str:
    """Return the RAG runtime configuration file.

    Returns:
        Absolute path to ``configs/rag.yaml``.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import rag_config_path
        >>> os.path.isfile(rag_config_path())
        True
    """
    return os.path.join(configs_dir(), "rag.yaml")


def docs_dir() -> str:
    """Return the MkDocs documentation directory.

    Returns:
        Absolute path to ``docs/`` at the repository root.

    Example:
        >>> import os
        >>> from thot.core.TkeirPaths import docs_dir, repo_root
        >>> os.path.isdir(docs_dir())
        True
        >>> docs_dir() == os.path.join(repo_root(), "docs")
        True
    """
    return os.path.join(repo_root(), "docs")


def evaluation_report_path() -> str:
    """Return the BEIR evaluation report path under documentation.

    Returns:
        Absolute path to ``docs/evaluation_report.md``.

    Example:
        >>> from thot.core.TkeirPaths import evaluation_report_path
        >>> evaluation_report_path().endswith("docs/evaluation_report.md")
        True
    """
    return os.path.join(docs_dir(), "evaluation_report.md")


def evaluation_generate_report_path() -> str:
    """Return the generation-eval report path under documentation.

    Returns:
        Absolute path to ``docs/evaluation_generate_report.md``.

    Example:
        >>> from thot.core.TkeirPaths import evaluation_generate_report_path
        >>> evaluation_generate_report_path().endswith(
        ...     "docs/evaluation_generate_report.md"
        ... )
        True
    """
    return os.path.join(docs_dir(), "evaluation_generate_report.md")


def evaluation_rag_report_path() -> str:
    """Deprecated alias for :func:`evaluation_generate_report_path`.

    Example:
        >>> from thot.core.TkeirPaths import (
        ...     evaluation_rag_report_path,
        ...     evaluation_generate_report_path,
        ... )
        >>> evaluation_rag_report_path() == evaluation_generate_report_path()
        True
    """
    return evaluation_generate_report_path()


def resolve_path(path: str) -> str:
    """Expand a path relative to the ``tkeir`` package root.

    Args:
        path: Relative or absolute filesystem path.

    Returns:
        Absolute path when ``path`` is relative; unchanged when already absolute.

    Example:
        >>> from thot.core.TkeirPaths import resolve_path
        >>> resolve_path("configs/pipeline.yaml").endswith("configs/pipeline.yaml")
        True
    """
    if not path or os.path.isabs(path):
        return path
    return os.path.abspath(os.path.join(package_root(), path))


def resolve_tkeir_paths(configuration):
    """Recursively resolve known path fields in a loaded configuration dict.

    Args:
        configuration: Nested dict or list loaded from a JSON config file.

    Returns:
        The same object with ``resources-base-path`` entries expanded in place.

    Example:
        >>> from thot.core.TkeirPaths import resolve_tkeir_paths
        >>> cfg = {"segmenters": [{"resources-base-path": "resources/modeling/tokenizer/en"}]}
        >>> resolved = resolve_tkeir_paths(cfg)
        >>> resolved["segmenters"][0]["resources-base-path"].endswith("tokenizer/en")
        True
    """
    if isinstance(configuration, dict):
        for key, value in configuration.items():
            if key in _PATH_KEYS and isinstance(value, str):
                configuration[key] = resolve_path(value)
            else:
                resolve_tkeir_paths(value)
    elif isinstance(configuration, list):
        for item in configuration:
            resolve_tkeir_paths(item)
    return configuration


def effective_resources_path(
    resource_path: str | None, language: str = "en"
) -> str | None:
    """Return a usable resources directory, falling back to bundled defaults.

    Args:
        resource_path: Configured resources path, or ``None``.
        language: Fallback language when the configured path is missing.

    Returns:
        Existing directory path, bundled default when available, or ``resource_path``.

    Example:
        >>> from thot.core.TkeirPaths import effective_resources_path, resources_dir
        >>> effective_resources_path(None, "en") == resources_dir("en")
        True
    """
    if resource_path and os.path.isdir(resource_path):
        return resource_path
    candidate = resources_dir(language)
    if os.path.isdir(candidate):
        return candidate
    return resource_path
