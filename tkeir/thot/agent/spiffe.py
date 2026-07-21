"""SPIFFE identity resolution for T-KEIR agents (ADR-0008).

Agents must carry a workload SPIFFE ID on every ActionRecord so mastering
(governor kill switch, budgets, approvals) attributes machine actors, not
only the human ``user_space`` tenant.

Resolution order:

1. Explicit ``SPIFFE_ID`` env (Compose / K8s inject).
2. Workload API via optional ``spiffe`` package + ``SPIFFE_ENDPOINT_SOCKET``.
3. Side-car / init file ``SPIFFE_ID_FILE`` (default
   ``/var/run/secrets/spiffe/spiffe_id``).
4. ``SPIFFE_MODE=dev`` synthesizes ``spiffe://{trust}/agent/{name}``.
5. Otherwise ``None`` (P0 without agents/SPIRE).

When ``SPIFFE_ENFORCE=true`` (or governor ``enforce`` with agents), missing
or disallowed IDs are denied.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

DEFAULT_TRUST_DOMAIN = "tkeir.local"
DEFAULT_ID_FILE = "/var/run/secrets/spiffe/spiffe_id"
_AGENT_SEGMENT = re.compile(r"[^a-zA-Z0-9._-]+")


def trust_domain() -> str:
    """Return configured SPIFFE trust domain.

    Returns:
        Trust domain string (default ``tkeir.local``).

    Example:
        >>> import os
        >>> os.environ.pop("SPIFFE_TRUST_DOMAIN", None)
        >>> trust_domain()
        'tkeir.local'
    """
    return (os.getenv("SPIFFE_TRUST_DOMAIN") or DEFAULT_TRUST_DOMAIN).strip()


def spiffe_mode() -> str:
    """Return the SPIFFE resolution mode.

    Returns:
        One of ``off``, ``dev``, or ``workload`` (invalid values → ``dev``).

    Example:
        >>> import os
        >>> os.environ["SPIFFE_MODE"] = "dev"
        >>> spiffe_mode()
        'dev'
        >>> os.environ["SPIFFE_MODE"] = "weird"
        >>> spiffe_mode()
        'dev'
    """
    raw = (os.getenv("SPIFFE_MODE") or "dev").strip().lower()
    if raw in {"off", "dev", "workload"}:
        return raw
    return "dev"


def spiffe_enforce() -> bool:
    """Whether agent actions require a valid SPIFFE ID.

    Returns:
        True when ``SPIFFE_ENFORCE`` is truthy, or when governor mode is
        ``enforce`` and SPIFFE mode is not ``off``.

    Example:
        >>> import os
        >>> os.environ["SPIFFE_ENFORCE"] = "true"
        >>> spiffe_enforce()
        True
        >>> del os.environ["SPIFFE_ENFORCE"]
    """
    flag = (os.getenv("SPIFFE_ENFORCE") or "").strip().lower()
    if flag in {"1", "true", "yes", "on"}:
        return True
    if flag in {"0", "false", "no", "off"}:
        return False
    mode = (os.getenv("GOVERNOR_MODE") or "observe").strip().lower()
    return mode == "enforce" and spiffe_mode() != "off"


def sanitize_agent_segment(agent_name: str) -> str:
    """Sanitize an agent YAML name for a SPIFFE path segment.

    Args:
        agent_name: Agent id from configs (may contain spaces/punctuation).

    Returns:
        Safe path segment for ``spiffe://…/agent/{segment}``.

    Example:
        >>> sanitize_agent_segment("Researcher / v1")
        'Researcher-v1'
    """
    cleaned = _AGENT_SEGMENT.sub("-", (agent_name or "agent").strip())
    return cleaned.strip("-._") or "agent"


def synthesize_dev_spiffe_id(agent_name: str) -> str:
    """Build a deterministic SPIFFE ID for local / Compose without Workload API.

    Args:
        agent_name: Agent YAML name.

    Returns:
        ``spiffe://{trust}/agent/{sanitized}`` string.

    Example:
        >>> import os
        >>> os.environ.pop("SPIFFE_TRUST_DOMAIN", None)
        >>> synthesize_dev_spiffe_id("researcher")
        'spiffe://tkeir.local/agent/researcher'
    """
    return (
        f"spiffe://{trust_domain()}/agent/{sanitize_agent_segment(agent_name)}"
    )


def allowed_prefixes() -> tuple[str, ...]:
    """Return prefixes accepted when enforcing agent SPIFFE IDs.

    Returns:
        Tuple of allowed SPIFFE ID prefixes (from env or trust-domain default).

    Example:
        >>> import os
        >>> os.environ.pop("SPIFFE_AGENT_ID_PREFIX", None)
        >>> os.environ.pop("SPIFFE_TRUST_DOMAIN", None)
        >>> allowed_prefixes()
        ('spiffe://tkeir.local/agent/',)
    """
    raw = (os.getenv("SPIFFE_AGENT_ID_PREFIX") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return (f"spiffe://{trust_domain()}/agent/",)


def is_allowed_agent_spiffe_id(spiffe_id: str | None) -> bool:
    """Return True if ``spiffe_id`` matches configured agent prefixes.

    Args:
        spiffe_id: Candidate SPIFFE ID or ``None``.

    Returns:
        Whether the ID is allow-listed for agent workloads.

    Example:
        >>> import os
        >>> os.environ.pop("SPIFFE_AGENT_ID_PREFIX", None)
        >>> os.environ.pop("SPIFFE_TRUST_DOMAIN", None)
        >>> is_allowed_agent_spiffe_id("spiffe://tkeir.local/agent/researcher")
        True
        >>> is_allowed_agent_spiffe_id("spiffe://evil/agent/x")
        False
    """
    if not spiffe_id or not spiffe_id.startswith("spiffe://"):
        return False
    return any(spiffe_id.startswith(prefix) for prefix in allowed_prefixes())


def _read_id_file() -> str | None:
    """Read a SPIFFE ID from ``SPIFFE_ID_FILE`` when the file exists.

    Returns:
        Stripped SPIFFE ID string, or ``None`` if missing/unreadable.

    Example:
        >>> import os, tempfile
        >>> from pathlib import Path
        >>> with tempfile.TemporaryDirectory() as td:
        ...     path = Path(td) / "spiffe_id"
        ...     _ = path.write_text("spiffe://tkeir.local/agent/x\\n", encoding="utf-8")
        ...     os.environ["SPIFFE_ID_FILE"] = str(path)
        ...     value = _read_id_file()
        ...     del os.environ["SPIFFE_ID_FILE"]
        ...     value
        'spiffe://tkeir.local/agent/x'
    """
    path = Path(os.getenv("SPIFFE_ID_FILE") or DEFAULT_ID_FILE)
    try:
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            return value or None
    except OSError:
        return None
    return None


def _from_workload_api() -> str | None:
    """Best-effort X.509-SVID SPIFFE ID via optional ``spiffe`` package.

    Returns:
        SPIFFE ID from the Workload API, or ``None`` when unavailable.

    Example:
        >>> import os
        >>> os.environ.pop("SPIFFE_ENDPOINT_SOCKET", None)
        >>> _from_workload_api() is None
        True
    """
    socket = (os.getenv("SPIFFE_ENDPOINT_SOCKET") or "").strip()
    if not socket:
        return None
    try:
        from spiffe import WorkloadApiClient
    except ImportError:
        return None
    try:
        with WorkloadApiClient(socket_path=socket) as client:
            svid = client.fetch_x509_svid()
            spiffe_id = getattr(svid, "spiffe_id", None)
            if spiffe_id is None:
                return None
            return str(spiffe_id)
    except Exception:  # noqa: BLE001 — optional path must not crash agents
        return None


def resolve_agent_spiffe_id(agent_name: str = "tkeir-agent") -> str | None:
    """Resolve the workload SPIFFE ID for an agent process / run.

    Args:
        agent_name: Agent YAML name used when synthesizing a ``dev`` ID.

    Returns:
        SPIFFE ID string, or ``None`` when mode is ``off`` / workload failed.

    Example:
        >>> import os
        >>> os.environ["SPIFFE_MODE"] = "dev"
        >>> os.environ.pop("SPIFFE_ID", None)
        >>> os.environ.pop("SPIFFE_TRUST_DOMAIN", None)
        >>> resolve_agent_spiffe_id("researcher")
        'spiffe://tkeir.local/agent/researcher'
    """
    mode = spiffe_mode()
    if mode == "off":
        return None

    explicit = (os.getenv("SPIFFE_ID") or "").strip()
    if explicit:
        return explicit

    from_file = _read_id_file()
    if from_file:
        return from_file

    if mode == "workload":
        from_api = _from_workload_api()
        if from_api:
            return from_api
        return None

    return synthesize_dev_spiffe_id(agent_name)


def require_agent_spiffe_id(agent_name: str = "tkeir-agent") -> str:
    """Resolve and validate SPIFFE ID when enforcement is on.

    Args:
        agent_name: Agent YAML name used for synthesis / error context.

    Returns:
        A non-empty allow-listed SPIFFE ID.

    Raises:
        PermissionError: When enforcement requires a valid agent SPIFFE ID.

    Example:
        >>> import os
        >>> os.environ["SPIFFE_MODE"] = "dev"
        >>> os.environ["SPIFFE_ENFORCE"] = "false"
        >>> require_agent_spiffe_id("researcher").startswith("spiffe://")
        True
    """
    spiffe_id = resolve_agent_spiffe_id(agent_name)
    if not spiffe_enforce():
        return spiffe_id or synthesize_dev_spiffe_id(agent_name)
    if not is_allowed_agent_spiffe_id(spiffe_id):
        raise PermissionError(
            "agent SPIFFE identity missing or not allowed "
            f"(got={spiffe_id!r}; prefixes={allowed_prefixes()!r})"
        )
    assert spiffe_id is not None
    return spiffe_id
