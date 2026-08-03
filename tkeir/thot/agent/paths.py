"""Title: Resolve default AGENT_ROOT under the shared workspace.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import os
from pathlib import Path


def default_agent_root() -> Path:
    """Return the agent run-store root.

    Preference:

    1. ``AGENT_ROOT`` when set
    2. ``<workspace>/agent`` (same durable tree as ingest / users / okf)

    Returns:
        Absolute path for run manifests, blackboard, publishes.

    Example:
        >>> import os
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.agent.paths import default_agent_root
        >>> with tempfile.TemporaryDirectory() as td:
        ...     os.environ["AGENT_ROOT"] = td
        ...     default_agent_root() == Path(td).resolve()
        ...     del os.environ["AGENT_ROOT"]
        True
    """
    env = (os.getenv("AGENT_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    from thot.tools.ingest.user_workspace import workspace_root

    return (workspace_root() / "agent").resolve()
