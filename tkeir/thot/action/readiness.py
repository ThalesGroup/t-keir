"""Title: Readiness

Readiness probes for Vespa and the configured LLM provider.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any

import httpx

from thot.core.LlmWrapper import Provider, UnifiedLLMWrapper, WrapperConfig


async def probe_provider(
    llm: UnifiedLLMWrapper | None = None,
    *,
    config: WrapperConfig | None = None,
    client: httpx.AsyncClient | None = None,
) -> tuple[bool, str]:
    """Check that the configured ``PROVIDER`` endpoint is reachable.

    Unlike :meth:`UnifiedLLMWrapper.verify_provider`, this never exits the
    process — it returns ``(False, reason)`` on failure.

    Returns:
        ``(True, detail)`` when ready; ``(False, reason)`` otherwise.

    Example:
        >>> import inspect
        >>> inspect.iscoroutinefunction(probe_provider)
        True
    """
    cfg = config or (
        llm._config if llm is not None else WrapperConfig.from_env()
    )
    owns_client = client is None
    timeout = min(float(cfg.timeout_seconds), 5.0)
    http = client or httpx.AsyncClient(timeout=timeout)
    try:
        if cfg.provider is Provider.OLLAMA:
            url = f"{cfg.ollama_base_url.rstrip('/')}/api/tags"
            response = await http.get(url)
            response.raise_for_status()
            return True, f"ollama ok ({cfg.ollama_base_url})"
        if cfg.provider is Provider.OPENAI:
            url = f"{cfg.openai_base_url.rstrip('/')}/models"
            headers: dict[str, str] = {}
            if cfg.openai_api_key:
                headers["Authorization"] = f"Bearer {cfg.openai_api_key}"
            response = await http.get(url, headers=headers)
            response.raise_for_status()
            return True, "openai ok"
        if cfg.provider is Provider.VLLM:
            url = f"{cfg.vllm_base_url.rstrip('/')}/models"
            response = await http.get(url)
            response.raise_for_status()
            return True, f"vllm ok ({cfg.vllm_base_url})"
        return False, f"unknown provider {cfg.provider}"
    except Exception as exc:  # noqa: BLE001 — readiness must not raise
        return False, str(exc)
    finally:
        if owns_client:
            await http.aclose()


async def readiness_report(
    *,
    vespa_ok: bool,
    llm: UnifiedLLMWrapper | None = None,
) -> dict[str, Any]:
    """Build a readiness payload for ``GET /ready``.

    Example:
        >>> import asyncio
        >>> report = asyncio.run(readiness_report(vespa_ok=False))
        >>> report["status"]
        'not_ready'
    """
    provider_ok, provider_detail = await probe_provider(llm)
    ready = vespa_ok and provider_ok
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "vespa": {"ok": vespa_ok},
            "provider": {"ok": provider_ok, "detail": provider_detail},
        },
    }
