"""Title: Agent orchestrator usecase configuration

Load report-form templates and slot hints from dataset packs
(``datasets/<pack>/agent_orchestrator.yaml``) so the orchestrator stays
usecase-agnostic.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from thot.core.TkeirPaths import package_root, repo_root

LOGGER = logging.getLogger(__name__)

_CONFIG_FILENAME = "agent_orchestrator.yaml"


@dataclass(frozen=True)
class OrchestratorConfig:
    """Merged orchestrator settings from one or more usecase packs.

    Attributes:
        name: Active pack name (``osint``, ``enterprise``, …).
        default_report_form: Default HMI / workflow form key.
        report_form_templates: Form alias → compose template name.
        report_form_slot_hints: Form alias → writer slot hint text.

    Example:
        >>> from thot.agent.orchestrator_config import OrchestratorConfig
        >>> cfg = OrchestratorConfig(name="osint", default_report_form="intsum")
        >>> cfg.name
        'osint'
    """

    name: str = ""
    default_report_form: str = "intsum"
    report_form_templates: dict[str, str] = field(default_factory=dict)
    report_form_slot_hints: dict[str, str] = field(default_factory=dict)

    def template_for(self, report_form: str | None) -> str | None:
        """Resolve a compose template name for ``report_form``.

        Args:
            report_form: HMI / workflow form alias (for example ``intsum``).

        Returns:
            Template stem under ``configs/templates/``, or ``None`` if unknown.

        Example:
            >>> cfg = OrchestratorConfig(
            ...     report_form_templates={"intsum": "otan_intsum"}
            ... )
            >>> cfg.template_for("intsum")
            'otan_intsum'
            >>> cfg.template_for(None) is None
            True
        """
        form_key = _normalize_form_key(report_form)
        if not form_key:
            return None
        return self.report_form_templates.get(
            form_key
        ) or self.report_form_templates.get(
            form_key.removeprefix("otan_").removeprefix("ent_")
        )

    def slot_hint_for(self, report_form: str | None) -> str:
        """Return writer slot hints for ``report_form``.

        Args:
            report_form: Form alias; falls back to ``default_report_form``.

        Returns:
            Slot-hint string injected as ``{report_form_slots}``.

        Example:
            >>> cfg = OrchestratorConfig(
            ...     default_report_form="intsum",
            ...     report_form_slot_hints={"intsum": "otan_intsum slots: situation"},
            ... )
            >>> "otan_intsum" in cfg.slot_hint_for("intsum")
            True
        """
        form_key = _normalize_form_key(report_form) or self.default_report_form
        hint = self.report_form_slot_hints.get(form_key)
        if hint:
            return hint
        stripped = form_key.removeprefix("otan_").removeprefix("ent_")
        hint = self.report_form_slot_hints.get(stripped)
        if hint:
            return hint
        return f"compose template for report_form={form_key}"


def _normalize_form_key(report_form: str | None) -> str:
    """Normalize a report-form alias to a stable lookup key.

    Args:
        report_form: Raw form string (may contain spaces or hyphens).

    Returns:
        Lowercase underscore key, or ``\"\"`` when empty.

    Example:
        >>> _normalize_form_key("Commander Brief")
        'commander_brief'
        >>> _normalize_form_key(None)
        ''
    """
    return (
        str(report_form or "")
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def orchestrator_config_paths() -> list[Path]:
    """Return ``agent_orchestrator.yaml`` paths under dataset / pack roots.

    Example:
        >>> from thot.agent.orchestrator_config import orchestrator_config_paths
        >>> isinstance(orchestrator_config_paths(), list)
        True
    """
    paths: list[Path] = []
    for base in (
        Path(repo_root()) / "datasets",
        Path(package_root()) / "packs",
    ):
        if not base.is_dir():
            continue
        for pack in sorted(base.iterdir()):
            if not pack.is_dir() or pack.name.startswith("."):
                continue
            candidate = pack / _CONFIG_FILENAME
            if candidate.is_file():
                paths.append(candidate)
    extra = os.getenv("TKEIR_AGENT_ORCHESTRATOR_CONFIG", "").strip()
    if extra:
        path = Path(extra).expanduser()
        if path.is_file():
            paths.append(path)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        key = path.resolve()
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def _parse_config_mapping(raw: Any, *, source: Path) -> dict[str, Any]:
    """Validate and normalize one orchestrator YAML mapping.

    Args:
        raw: Parsed YAML root (must be a ``dict``).
        source: Path used only for error messages / default ``name``.

    Returns:
        Normalized dict with ``name``, ``default_report_form``,
        ``report_form_templates``, and ``report_form_slot_hints``.

    Example:
        >>> from pathlib import Path
        >>> data = _parse_config_mapping(
        ...     {
        ...         "name": "osint",
        ...         "default_report_form": "intsum",
        ...         "report_form_templates": {"intsum": "otan_intsum"},
        ...         "report_form_slot_hints": {"intsum": "slots"},
        ...     },
        ...     source=Path("osint/agent_orchestrator.yaml"),
        ... )
        >>> data["report_form_templates"]["intsum"]
        'otan_intsum'
    """
    if not isinstance(raw, dict):
        raise ValueError(f"orchestrator config must be a mapping: {source}")
    templates = raw.get("report_form_templates") or {}
    hints = raw.get("report_form_slot_hints") or {}
    if not isinstance(templates, dict) or not isinstance(hints, dict):
        raise ValueError(
            f"report_form_templates / report_form_slot_hints must be mappings: {source}"
        )
    return {
        "name": str(raw.get("name") or source.parent.name).strip(),
        "default_report_form": (
            str(raw.get("default_report_form") or "intsum").strip().lower()
        ),
        "report_form_templates": {
            _normalize_form_key(key): str(value).strip()
            for key, value in templates.items()
            if str(key).strip() and str(value).strip()
        },
        "report_form_slot_hints": {
            _normalize_form_key(key): str(value).strip()
            for key, value in hints.items()
            if str(key).strip() and str(value).strip()
        },
    }


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load and normalize an ``agent_orchestrator.yaml`` file.

    Args:
        path: Filesystem path to the YAML pack.

    Returns:
        Normalized mapping from :func:`_parse_config_mapping`.

    Example:
        >>> from pathlib import Path
        >>> from thot.core.TkeirPaths import repo_root
        >>> p = Path(repo_root()) / "datasets" / "osint" / "agent_orchestrator.yaml"
        >>> _load_yaml(p)["name"] in {"osint", p.parent.name}
        True
    """
    with path.open(encoding="utf-8") as handle:
        return _parse_config_mapping(yaml.safe_load(handle), source=path)


def resolve_usecase(explicit: str | None = None) -> str:
    """Resolve active usecase pack name (``osint``, ``enterprise``, …).

    Args:
        explicit: Optional override (for example from run ``params.usecase``).

    Returns:
        Lowercase pack name, or ``\"\"`` when unset.

    Example:
        >>> resolve_usecase("OSINT")
        'osint'
        >>> resolve_usecase("enterprise")
        'enterprise'
    """
    if explicit and str(explicit).strip():
        return str(explicit).strip().lower()
    for env_key in (
        "TKEIR_AGENT_USECASE",
        "TKEIR_DATASET",
        "TKEIR_BUSINESS_ONTOLOGY_DATASET",
    ):
        value = os.getenv(env_key, "").strip()
        if value:
            return value.lower()
    return ""


def load_orchestrator_config(
    *,
    usecase: str | None = None,
    paths: list[Path] | None = None,
) -> OrchestratorConfig:
    """Load and merge usecase orchestrator YAML files.

    All discovered packs contribute ``report_form_*`` maps (later packs and the
    selected usecase override on key conflict). ``default_report_form`` comes
    from the selected usecase when present.

    Args:
        usecase: Optional pack name (``osint``, ``enterprise``, …).
        paths: Optional explicit YAML paths (tests); default discovers packs.

    Returns:
        Merged :class:`OrchestratorConfig`.

    Example:
        >>> from thot.agent.orchestrator_config import load_orchestrator_config
        >>> cfg = load_orchestrator_config(usecase="osint")
        >>> cfg.template_for("intsum")
        'otan_intsum'
    """
    selected = resolve_usecase(usecase)
    discovered = (
        list(paths) if paths is not None else orchestrator_config_paths()
    )
    if not discovered:
        LOGGER.warning(
            "No %s found under datasets/; using empty orchestrator config",
            _CONFIG_FILENAME,
        )
        return OrchestratorConfig(name=selected or "default")

    parsed: list[tuple[Path, dict[str, Any]]] = []
    for path in discovered:
        try:
            parsed.append((path, _load_yaml(path)))
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to load orchestrator config %s", path)

    if not parsed:
        return OrchestratorConfig(name=selected or "default")

    # Prefer selected usecase last so it wins on conflicts.
    if selected:
        primary = [item for item in parsed if item[1].get("name") == selected]
        others = [item for item in parsed if item[1].get("name") != selected]
        ordered = others + primary
    else:
        ordered = parsed

    templates: dict[str, str] = {}
    hints: dict[str, str] = {}
    default_form = "intsum"
    name = selected or (ordered[-1][1].get("name") if ordered else "default")
    for _path, data in ordered:
        templates.update(data["report_form_templates"])
        hints.update(data["report_form_slot_hints"])
        default_form = data["default_report_form"] or default_form
        name = data.get("name") or name

    return OrchestratorConfig(
        name=str(name),
        default_report_form=_normalize_form_key(default_form) or "intsum",
        report_form_templates=templates,
        report_form_slot_hints=hints,
    )


@lru_cache(maxsize=8)
def get_orchestrator_config(usecase: str = "") -> OrchestratorConfig:
    """Cached :func:`load_orchestrator_config` (empty string = auto usecase).

    Args:
        usecase: Pack name; empty string selects via env / discovery.

    Returns:
        Cached :class:`OrchestratorConfig` instance.

    Example:
        >>> clear_orchestrator_config_cache()
        >>> cfg = get_orchestrator_config("osint")
        >>> cfg.template_for("sitrep")
        'otan_sitrep'
    """
    return load_orchestrator_config(usecase=usecase or None)


def clear_orchestrator_config_cache() -> None:
    """Drop the cached orchestrator config (tests / hot reload).

    Example:
        >>> clear_orchestrator_config_cache()
    """
    get_orchestrator_config.cache_clear()
