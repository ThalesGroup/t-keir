"""Title: Topic → business ontology resolution for the web collector.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from thot.tools.ingest.user_workspace import workspace_root


@dataclass(frozen=True)
class TopicOntologySpec:
    """Resolved ontology assets for one collector topic (+ optional language).

    Example:
        >>> TopicOntologySpec(topic="osint", business_ontology_dataset="osint").topic
        'osint'
    """

    topic: str
    description: str = ""
    business_ontology_dataset: str | None = None
    ontology_paths: list[str] = field(default_factory=list)
    business_ontology_path: Path | None = None
    language: str | None = None


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load a YAML mapping from ``path``, or ``{}`` if missing/invalid.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.collector.topics import _load_yaml
        >>> _load_yaml(Path("/no/such/file.yaml"))
        {}
    """
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def load_topics_catalog(path: Path) -> dict[str, Any]:
    """Load ``topics.yaml`` catalog.

    Example:
        >>> from pathlib import Path
        >>> from thot.core.TkeirPaths import configs_dir
        >>> from thot.tools.collector.topics import load_topics_catalog
        >>> cat = load_topics_catalog(Path(configs_dir()) / "collector" / "topics.yaml")
        >>> "topics" in cat
        True
    """
    return _load_yaml(path)


def normalize_language(code: str | None) -> str:
    """Normalize to a two-letter lowercase language tag.

    Example:
        >>> from thot.tools.collector.topics import normalize_language
        >>> normalize_language("fr-FR")
        'fr'
        >>> normalize_language(None)
        'en'
    """
    if not code or not str(code).strip():
        return "en"
    return str(code).strip().split("-")[0].lower()


def workspace_topic_dir(
    topic: str,
    *,
    workspace: Path | None = None,
    language: str | None = None,
) -> Path:
    """Return ``workspace/collector/topics/<topic>[/<lang>]``.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.collector.topics import workspace_topic_dir
        >>> workspace_topic_dir("osint", workspace=Path("/tmp/ws")).as_posix()
        '/tmp/ws/collector/topics/osint'
        >>> workspace_topic_dir(
        ...     "osint", workspace=Path("/tmp/ws"), language="fr"
        ... ).as_posix()
        '/tmp/ws/collector/topics/osint/fr'
    """
    root = Path(workspace) if workspace is not None else workspace_root()
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in (topic or "").strip()
    )
    base = root / "collector" / "topics" / (safe or "_unknown")
    if language:
        return base / normalize_language(language)
    return base


def _collect_ontology_files(directory: Path) -> list[str]:
    """List RDF/OWL ontology files under ``directory``.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.collector.topics import _collect_ontology_files
        >>> _collect_ontology_files(Path("/no/such/dir"))
        []
    """
    if not directory.is_dir():
        return []
    out: list[str] = []
    for path in sorted(directory.iterdir()):
        if path.suffix.lower() in {".ttl", ".owl", ".rdf", ".jsonld", ".nt"}:
            out.append(str(path.resolve()))
    return out


def _resolve_path(raw: str, *, catalog_path: Path) -> Path | None:
    """Resolve ``raw`` to an existing file path, or None.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.collector.topics import _resolve_path
        >>> _resolve_path("/no/such/file.ttl", catalog_path=Path(".")) is None
        True
    """
    p = Path(str(raw)).expanduser()
    if not p.is_absolute():
        from thot.core.TkeirPaths import repo_root

        p = (Path(repo_root()) / p).resolve()
    return p if p.is_file() else None


def resolve_topic_ontology(
    topic: str | None,
    *,
    catalog_path: Path,
    workspace: Path | None = None,
    language: str | None = None,
) -> TopicOntologySpec:
    """Resolve business ontology dataset + RDF paths for ``topic`` and language.

    Preference:

    1. ``workspace/collector/topics/<topic>/<lang>/`` (YAML + ``ontologies/``)
    2. ``workspace/collector/topics/<topic>/`` overrides
    3. Catalog ``by_language.<lang>`` under the topic entry
    4. Catalog topic defaults / ``default_topic``

    Example:
        >>> from pathlib import Path
        >>> from thot.core.TkeirPaths import configs_dir
        >>> from thot.tools.collector.topics import resolve_topic_ontology
        >>> spec = resolve_topic_ontology(
        ...     "osint",
        ...     catalog_path=Path(configs_dir()) / "collector" / "topics.yaml",
        ...     workspace=Path("/tmp/no-override"),
        ...     language="en",
        ... )
        >>> spec.business_ontology_dataset
        'osint'
        >>> spec.language
        'en'
    """
    catalog = load_topics_catalog(catalog_path)
    raw_topics = catalog.get("topics")
    topics: dict[str, Any] = raw_topics if isinstance(raw_topics, dict) else {}
    default_name = (
        str(catalog.get("default_topic") or "osint").strip() or "osint"
    )
    requested = (topic or "").strip() or default_name
    lang = normalize_language(language)

    topic_ws = workspace_topic_dir(requested, workspace=workspace)
    lang_ws = workspace_topic_dir(
        requested, workspace=workspace, language=lang
    )
    has_lang_ws = (lang_ws / "business_ontology.yaml").is_file() or bool(
        _collect_ontology_files(lang_ws / "ontologies")
    )
    has_topic_ws = (topic_ws / "business_ontology.yaml").is_file() or bool(
        _collect_ontology_files(topic_ws / "ontologies")
    )

    entry: dict[str, Any]
    if has_lang_ws or has_topic_ws:
        name = requested
        raw_entry = topics.get(name)
        entry = raw_entry if isinstance(raw_entry, dict) else {}
    else:
        raw_entry = topics.get(requested)
        entry_or_none: dict[str, Any] | None = (
            raw_entry if isinstance(raw_entry, dict) else None
        )
        if entry_or_none is None and requested != default_name:
            raw_default = topics.get(default_name)
            entry_or_none = (
                raw_default if isinstance(raw_default, dict) else None
            )
            name = default_name if entry_or_none is not None else requested
        else:
            name = requested
        entry = entry_or_none or {}
        topic_ws = workspace_topic_dir(name, workspace=workspace)
        lang_ws = workspace_topic_dir(name, workspace=workspace, language=lang)

    raw_by_language = entry.get("by_language")
    by_language: dict[str, Any] = (
        raw_by_language if isinstance(raw_by_language, dict) else {}
    )
    raw_lang_entry = by_language.get(lang)
    lang_entry: dict[str, Any] = (
        raw_lang_entry if isinstance(raw_lang_entry, dict) else {}
    )

    dataset = str(entry.get("business_ontology_dataset") or "").strip() or None
    if lang_entry.get("business_ontology_dataset"):
        dataset = (
            str(lang_entry["business_ontology_dataset"]).strip() or dataset
        )

    ontology_paths: list[str] = []
    bo_path: Path | None = None

    # Language-specific workspace first, then topic-level workspace.
    for ws_dir in (lang_ws, topic_ws):
        override_bo = ws_dir / "business_ontology.yaml"
        if bo_path is None and override_bo.is_file():
            bo_path = override_bo
            dataset = dataset or name
        ontology_paths.extend(_collect_ontology_files(ws_dir / "ontologies"))

    for raw in list(entry.get("ontology_paths") or []) + list(
        lang_entry.get("ontology_paths") or []
    ):
        resolved = _resolve_path(str(raw), catalog_path=catalog_path)
        if resolved is not None:
            ontology_paths.append(str(resolved))

    seen: set[str] = set()
    unique_paths: list[str] = []
    for item in ontology_paths:
        if item not in seen:
            seen.add(item)
            unique_paths.append(item)

    description = str(
        lang_entry.get("description") or entry.get("description") or ""
    )
    return TopicOntologySpec(
        topic=name,
        description=description,
        business_ontology_dataset=dataset,
        ontology_paths=unique_paths,
        business_ontology_path=bo_path,
        language=lang,
    )
