#!/usr/bin/env python3
"""Initialize Vespa Docker container and deploy 2-level schemas."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx

from thot.core.TkeirPaths import vespa_dir

VESPA_ROOT = vespa_dir()
START_SCRIPT = Path(VESPA_ROOT) / "start_vespa.sh"
INIT_SCRIPT = Path(VESPA_ROOT) / "init_schema.sh"


def _run(script: Path) -> None:
    """Execute a Vespa shell script from the Vespa project root.

    Args:
        script: Path to a bash script under ``VESPA_ROOT``.

    Example:
        >>> from pathlib import Path
        >>> from thot.tools.search.init_vespa import _run, VESPA_ROOT, START_SCRIPT
        >>> _run(START_SCRIPT)  # doctest: +SKIP
    """
    subprocess.run(["bash", str(script)], check=True, cwd=VESPA_ROOT)


def _health_is_up(payload: dict[str, Any]) -> bool:
    """Return whether a Vespa health payload reports a ready status.

    Args:
        payload: JSON body from a Vespa ``/state/v1/health`` endpoint.

    Returns:
        ``True`` when status code is ``up``, ``ok``, or ``green``.

    Example:
        >>> from thot.tools.search.init_vespa import _health_is_up
        >>> _health_is_up({"status": {"code": "up"}})
        True
        >>> _health_is_up({"status": {"code": "down"}})
        False
    """
    status = payload.get("status") or {}
    code = str(status.get("code", "")).lower()
    return code in {"up", "ok", "green"}


def _wait_for_config_server(config_url: str, timeout_seconds: int) -> None:
    """Wait until the Vespa config server accepts health checks.

    Args:
        config_url: Base URL of the Vespa config server.
        timeout_seconds: Maximum seconds to wait before raising.

    Raises:
        TimeoutError: When the config server does not become ready in time.

    Example:
        >>> from thot.tools.search.init_vespa import _wait_for_config_server
        >>> _wait_for_config_server("http://localhost:19071", 1)  # doctest: +SKIP
    """
    deadline = time.time() + timeout_seconds
    health_url = f"{config_url.rstrip('/')}/state/v1/health"
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            response = httpx.get(health_url, timeout=5.0)
            if response.status_code == 200:
                payload = response.json()
                if _health_is_up(payload):
                    print(f"[✓] Vespa config server is up ({health_url})")
                    return
        except (httpx.HTTPError, json.JSONDecodeError):
            pass
        if attempt == 1 or attempt % 5 == 0:
            print(
                f"[…] Waiting for Vespa config server ({attempt} attempt(s), "
                f"{int(deadline - time.time())}s left)…"
            )
        time.sleep(3)
    raise TimeoutError(
        f"Vespa config server did not become ready within {timeout_seconds}s "
        f"({health_url})"
    )


def _wait_for_application(search_url: str, timeout_seconds: int) -> None:
    """Wait until the deployed application responds on the search endpoint.

    Args:
        search_url: Base URL of the Vespa container/search service.
        timeout_seconds: Maximum seconds to wait before raising.

    Raises:
        TimeoutError: When the search endpoint does not become ready in time.

    Example:
        >>> from thot.tools.search.init_vespa import _wait_for_application
        >>> _wait_for_application("http://localhost:8080", 1)  # doctest: +SKIP
    """
    deadline = time.time() + timeout_seconds
    probe_url = f"{search_url.rstrip('/')}/search/"
    payload = {
        "yql": "select * from sources * where true limit 1",
        "hits": 1,
        "streaming.groupname": os.getenv("VESPA_USER_SPACE", "dev@tkeir"),
    }
    attempt = 0
    while time.time() < deadline:
        attempt += 1
        try:
            response = httpx.post(probe_url, json=payload, timeout=10.0)
            if response.status_code in {200, 400}:
                print(f"[✓] Vespa search endpoint is ready ({probe_url})")
                return
        except httpx.HTTPError:
            pass
        if attempt == 1 or attempt % 5 == 0:
            print(
                f"[…] Waiting for Vespa search endpoint ({attempt} attempt(s), "
                f"{int(deadline - time.time())}s left)…"
            )
        time.sleep(3)
    raise TimeoutError(
        f"Vespa search endpoint did not become ready within {timeout_seconds}s "
        f"({probe_url})"
    )


def main() -> int:
    """Start Vespa, deploy schemas, and wait for readiness.

    Returns:
        Process exit code (``0`` on success).

    Example:
        >>> from thot.tools.search.init_vespa import main
        >>> main()  # doctest: +SKIP
    """
    parser = argparse.ArgumentParser(
        description="Initialize Vespa for T-KEIR RAG."
    )
    parser.add_argument(
        "--skip-start",
        action="store_true",
        help="Skip Docker container startup",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=180,
        help="Maximum seconds to wait for Vespa readiness (default: 180)",
    )
    parser.add_argument(
        "--vespa-url",
        default="http://localhost:8080",
        help="Vespa container/search URL",
    )
    parser.add_argument(
        "--config-url",
        default="http://localhost:19071",
        help="Vespa config server URL",
    )
    args = parser.parse_args()

    if not args.skip_start:
        _run(START_SCRIPT)
        _wait_for_config_server(args.config_url, args.wait_seconds)
    else:
        _wait_for_config_server(args.config_url, min(args.wait_seconds, 30))

    _run(INIT_SCRIPT)
    _wait_for_application(args.vespa_url, args.wait_seconds)
    print("[✓] Vespa 2-level schemas deployed (document + chunk).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
