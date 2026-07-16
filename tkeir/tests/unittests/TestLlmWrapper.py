# -*- coding: utf-8 -*-
"""Tests for the unified LLM and embedding wrapper."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from thot.core.LlmWrapper import (
    Provider,
    UnifiedLLMWrapper,
    WrapperConfig,
    _normalize_embedding,
)


def _config(provider: Provider, **overrides: object) -> WrapperConfig:
    return WrapperConfig(
        provider=provider,
        embedding_model=str(overrides.get("embedding_model", "embed-model")),
        llm_model=str(overrides.get("llm_model", "llm-model")),
        reranker_model=str(
            overrides.get("reranker_model", "rerank-model")
        ),
        embedding_dim=cast(int, overrides.get("embedding_dim", 3)),
        timeout_seconds=cast(float, overrides.get("timeout_seconds", 5.0)),
        openai_api_key=cast(str | None, overrides.get("openai_api_key")),
        openai_base_url=str(
            overrides.get("openai_base_url", "https://api.openai.com/v1")
        ),
        ollama_base_url=str(
            overrides.get("ollama_base_url", "http://localhost:11434")
        ),
        vllm_base_url=str(
            overrides.get("vllm_base_url", "http://localhost:8000/v1")
        ),
    )


def _json_response(payload: object) -> MagicMock:
    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = payload
    return response


def test_normalize_embedding_keeps_matching_length():
    assert _normalize_embedding([1.0, 2.0, 3.0], 3) == [1.0, 2.0, 3.0]


def test_embed_batch_empty_returns_empty_list():
    client = AsyncMock()
    wrapper = UnifiedLLMWrapper(_config(Provider.OPENAI), client=client)

    async def _run() -> list[list[float]]:
        return await wrapper.embed_batch([])

    assert asyncio.run(_run()) == []


def test_openai_embed_batch_normalizes_vectors():
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_json_response(
            {"data": [{"index": 0, "embedding": [1.0, 2.0, 3.0, 4.0]}]}
        )
    )
    wrapper = UnifiedLLMWrapper(
        _config(Provider.OPENAI, openai_api_key="secret"),
        client=client,
    )

    async def _run() -> list[list[float]]:
        return await wrapper.embed_batch(["hello"])

    assert asyncio.run(_run()) == [[1.0, 2.0, 3.0]]
    headers = client.post.await_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer secret"


def test_openai_generate_with_system_message():
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_json_response(
            {"choices": [{"message": {"content": "  answer  "}}]}
        )
    )
    wrapper = UnifiedLLMWrapper(_config(Provider.OPENAI), client=client)

    async def _run() -> str:
        return await wrapper.generate("hello", system="sys", temperature=0.2)

    assert asyncio.run(_run()) == "answer"
    payload = client.post.await_args.kwargs["json"]
    assert payload["messages"][0]["role"] == "system"
    assert payload["temperature"] == 0.2


def test_generate_logs_llm_statistics(monkeypatch):
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_json_response(
            {"choices": [{"message": {"content": "generated text"}}]}
        )
    )
    wrapper = UnifiedLLMWrapper(_config(Provider.OPENAI), client=client)
    logged: list[str] = []
    monkeypatch.setattr(
        "thot.core.LlmWrapper.ThotLogger.info",
        lambda message, **_: logged.append(message),
    )

    async def _run() -> str:
        return await wrapper.generate("user prompt", system="system prompt")

    assert asyncio.run(_run()) == "generated text"
    assert len(logged) == 1
    message = logged[0]
    assert "prompt_size=24" in message
    assert "output_size=14" in message
    assert "elapsed=" in message
    assert "provider=openai" in message


def test_ollama_embed_and_generate():
    client = AsyncMock()
    client.post = AsyncMock(
        side_effect=[
            _json_response({"embedding": [0.5, 0.6]}),
            _json_response({"message": {"content": "ollama reply"}}),
        ]
    )
    wrapper = UnifiedLLMWrapper(_config(Provider.OLLAMA), client=client)

    async def _run() -> tuple[list[list[float]], str]:
        vectors = await wrapper.embed_batch(["one"])
        text = await wrapper.generate("prompt")
        return vectors, text

    vectors, text = asyncio.run(_run())
    assert vectors == [[0.5, 0.6, 0.0]]
    assert text == "ollama reply"


def test_vllm_embed_and_generate():
    client = AsyncMock()
    client.post = AsyncMock(
        side_effect=[
            _json_response(
                {"data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]}
            ),
            _json_response(
                {"choices": [{"message": {"content": "vllm reply"}}]}
            ),
        ]
    )
    wrapper = UnifiedLLMWrapper(
        _config(Provider.VLLM, openai_api_key="token"),
        client=client,
    )

    async def _run() -> tuple[list[list[float]], str]:
        vectors = await wrapper.embed_batch(["text"])
        text = await wrapper.generate("prompt", system="guide")
        return vectors, text

    vectors, text = asyncio.run(_run())
    assert vectors == [[0.1, 0.2, 0.3]]
    assert text == "vllm reply"


def test_embed_delegates_to_embed_batch():
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_json_response(
            {"data": [{"index": 0, "embedding": [1.0, 0.0, 0.0]}]}
        )
    )
    wrapper = UnifiedLLMWrapper(_config(Provider.OPENAI), client=client)

    async def _run() -> list[float]:
        return await wrapper.embed("single")

    assert asyncio.run(_run()) == [1.0, 0.0, 0.0]


def test_verify_provider_skips_non_ollama():
    client = AsyncMock()
    wrapper = UnifiedLLMWrapper(_config(Provider.OPENAI), client=client)
    asyncio.run(wrapper.verify_provider())
    client.get.assert_not_called()


def test_verify_provider_checks_ollama_tags():
    client = AsyncMock()
    client.get = AsyncMock(return_value=_json_response({}))
    wrapper = UnifiedLLMWrapper(_config(Provider.OLLAMA), client=client)
    asyncio.run(wrapper.verify_provider())
    client.get.assert_awaited_once_with("http://localhost:11434/api/tags")


def test_verify_provider_raises_when_ollama_unreachable():
    client = AsyncMock()
    client.get = AsyncMock(side_effect=httpx.HTTPError("down"))
    wrapper = UnifiedLLMWrapper(_config(Provider.OLLAMA), client=client)
    with pytest.raises(SystemExit, match="Cannot reach Ollama"):
        asyncio.run(wrapper.verify_provider())


def test_aclose_closes_owned_client_only():
    wrapper = UnifiedLLMWrapper(_config(Provider.OPENAI))
    mock_client = AsyncMock()
    wrapper._client = mock_client
    wrapper._owns_client = True
    asyncio.run(wrapper.aclose())
    mock_client.aclose.assert_awaited_once()

    external = AsyncMock()
    external.aclose = AsyncMock()
    shared = UnifiedLLMWrapper(_config(Provider.OPENAI), client=external)
    asyncio.run(shared.aclose())
    external.aclose.assert_not_called()


def test_async_context_manager_closes_wrapper():
    async def _run() -> Provider:
        async with UnifiedLLMWrapper(_config(Provider.OPENAI)) as wrapper:
            return wrapper._config.provider

    assert asyncio.run(_run()) is Provider.OPENAI


def test_wrapper_config_from_env_example(monkeypatch):
    monkeypatch.setenv("PROVIDER", "vllm")
    cfg = WrapperConfig.from_env(file_models={})
    assert cfg.provider is Provider.VLLM
    assert cfg.reranker_model


def test_wrapper_config_env_overrides_file_models(monkeypatch):
    monkeypatch.setenv("PROVIDER", "ollama")
    monkeypatch.setenv("EMBEDDING_MODEL", "env-embed")
    monkeypatch.setenv("RERANKER_MODEL", "env-rerank")
    cfg = WrapperConfig.from_env(
        file_models={
            "embedding_model": "file-embed",
            "reranker_model": "file-rerank",
            "llm_model": "file-llm",
        }
    )
    assert cfg.embedding_model == "env-embed"
    assert cfg.reranker_model == "env-rerank"
    assert cfg.llm_model == "file-llm"


def test_ollama_rerank_uses_api_endpoint():
    client = AsyncMock()
    client.post = AsyncMock(
        return_value=_json_response(
            {
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.1},
                ]
            }
        )
    )
    wrapper = UnifiedLLMWrapper(
        _config(Provider.OLLAMA, reranker_model="qllama/bge-reranker-v2-m3"),
        client=client,
    )

    async def _run() -> list[dict]:
        return await wrapper.rerank("query", ["a", "b"], top_n=2)

    ranked = asyncio.run(_run())
    assert ranked[0]["index"] == 1
    assert ranked[0]["relevance_score"] == 0.9
    assert client.post.await_args.args[0].endswith("/api/rerank")


def test_ollama_rerank_falls_back_to_generate():
    not_found = MagicMock()
    not_found.status_code = 404
    not_found.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError(
            "404", request=MagicMock(), response=not_found
        )
    )

    generate_ok = _json_response({"response": "0.91"})

    async def _post(url: str, **kwargs):
        del kwargs
        if url.endswith("/api/generate"):
            return generate_ok
        return not_found

    client = AsyncMock()
    client.post = AsyncMock(side_effect=_post)
    wrapper = UnifiedLLMWrapper(
        _config(
            Provider.OLLAMA,
            reranker_model="mistral-nemo",
            llm_model="mistral-nemo",
        ),
        client=client,
    )

    async def _run() -> list[dict]:
        return await wrapper.rerank("query", ["only-doc"], top_n=1)

    ranked = asyncio.run(_run())
    assert ranked == [{"index": 0, "relevance_score": 0.91}]
    assert any(
        call.args[0].endswith("/api/generate")
        for call in client.post.await_args_list
    )


def test_sync_entry_points_use_asyncio_for_context_exit():
    asyncio.run(
        UnifiedLLMWrapper(_config(Provider.OPENAI)).__aexit__(None, None, None)
    )
