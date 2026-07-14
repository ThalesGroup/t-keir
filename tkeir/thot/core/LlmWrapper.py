# -*- coding: utf-8 -*-
"""Unified embedding and LLM wrapper for OpenAI, Ollama, and vLLM."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

import httpx

from thot.core.ThotLogger import ThotLogger


class Provider(str, Enum):
    OPENAI = "openai"
    OLLAMA = "ollama"
    VLLM = "vllm"


DEFAULT_EMBEDDING_DIM = 384
DEFAULT_EMBEDDING_MODELS = {
    Provider.OPENAI: "text-embedding-3-small",
    Provider.OLLAMA: "bge-m3",
    Provider.VLLM: "bge-small-en-v1.5",
}
DEFAULT_LLM_MODELS = {
    Provider.OPENAI: "gpt-4o",
    Provider.OLLAMA: "mistral-nemo",
    Provider.VLLM: "mistral-nemo",
}


class EmbeddingClient(Protocol):
    async def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(EmbeddingClient.embed)
            True
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of text strings.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(EmbeddingClient.embed_batch)
            True
        """
        ...


class LLMClient(Protocol):
    async def generate(self, prompt: str, *, temperature: float = 0.1) -> str:
        """Generate text from a prompt.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(LLMClient.generate)
            True
        """
        ...


@dataclass(frozen=True)
class WrapperConfig:
    provider: Provider
    embedding_model: str
    llm_model: str
    embedding_dim: int
    timeout_seconds: float
    openai_api_key: str | None
    openai_base_url: str
    ollama_base_url: str
    vllm_base_url: str

    @classmethod
    def from_env(cls) -> WrapperConfig:
        """Build configuration from environment variables.

        Reads ``PROVIDER``, ``EMBEDDING_MODEL``, ``LLM_MODEL``, ``EMBEDDING_DIM``,
        and provider-specific base URLs.

        Returns:
            Frozen configuration used by :class:`UnifiedLLMWrapper`.

        Example:
            >>> import os
            >>> from thot.core.LlmWrapper import WrapperConfig, Provider
            >>> os.environ["PROVIDER"] = "ollama"
            >>> cfg = WrapperConfig.from_env()
            >>> cfg.provider is Provider.OLLAMA
            True
        """
        provider_name = os.getenv("PROVIDER", Provider.OLLAMA.value).lower()
        provider = Provider(provider_name)
        return cls(
            provider=provider,
            embedding_model=os.getenv(
                "EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODELS[provider]
            ),
            llm_model=os.getenv("LLM_MODEL", DEFAULT_LLM_MODELS[provider]),
            embedding_dim=int(
                os.getenv("EMBEDDING_DIM", str(DEFAULT_EMBEDDING_DIM))
            ),
            timeout_seconds=float(os.getenv("HTTP_TIMEOUT_SECONDS", "120")),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_base_url=os.getenv(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/"),
            ollama_base_url=os.getenv(
                "OLLAMA_BASE_URL", "http://localhost:11434"
            ).rstrip("/"),
            vllm_base_url=os.getenv(
                "VLLM_BASE_URL", "http://localhost:8000/v1"
            ).rstrip("/"),
        )


def _normalize_embedding(
    vector: list[float],
    expected_dim: int,
) -> list[float]:
    """Pad or truncate an embedding vector to the configured dimension.

    Args:
        vector: Raw embedding returned by a provider.
        expected_dim: Target vector length.

    Returns:
        Vector of length ``expected_dim``.

    Example:
        >>> from thot.core.LlmWrapper import _normalize_embedding
        >>> _normalize_embedding([1.0, 2.0, 3.0], 2)
        [1.0, 2.0]
        >>> _normalize_embedding([1.0], 3)
        [1.0, 0.0, 0.0]
    """
    if len(vector) == expected_dim:
        return vector
    if len(vector) > expected_dim:
        return vector[:expected_dim]
    return vector + [0.0] * (expected_dim - len(vector))


def _log_llm_generate_stats(
    *,
    elapsed_seconds: float,
    prompt_size: int,
    output_size: int,
    provider: Provider,
    model: str,
) -> None:
    """Log prompt size, elapsed time, and output size for one LLM call.

    Example:
        >>> from thot.core.LlmWrapper import _log_llm_generate_stats, Provider
        >>> _log_llm_generate_stats(
        ...     elapsed_seconds=0.5,
        ...     prompt_size=120,
        ...     output_size=40,
        ...     provider=Provider.OLLAMA,
        ...     model="llama3",
        ... )
    """
    ThotLogger.info(
        "LLM generate "
        + f"elapsed={elapsed_seconds:.3f}s "
        + f"prompt_size={prompt_size} "
        + f"output_size={output_size} "
        + f"provider={provider.value} "
        + f"model={model}"
    )


class UnifiedLLMWrapper:
    """Provider-agnostic embedding and text generation client."""

    def __init__(
        self,
        config: WrapperConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        """Initialize the wrapper with optional config and HTTP client.

        Args:
            config: Provider settings; defaults to :meth:`WrapperConfig.from_env`.
            client: Shared async HTTP client; a new client is created when omitted.

        Example:
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> wrapper = UnifiedLLMWrapper()
            >>> wrapper._config.embedding_dim > 0
            True
        """
        self._config = config or WrapperConfig.from_env()
        self._client = client or httpx.AsyncClient(
            timeout=self._config.timeout_seconds
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        """Close the owned HTTP client when this wrapper created it.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper().aclose())  # doctest: +SKIP
        """
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> UnifiedLLMWrapper:
        """Enter an async context manager returning this wrapper.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> async def _demo():
            ...     async with UnifiedLLMWrapper() as wrapper:
            ...         return wrapper._config.provider.value
            >>> asyncio.run(_demo())  # doctest: +SKIP
        """
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Exit the async context manager and close owned resources.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper().__aexit__(None, None, None))  # doctest: +SKIP
        """
        await self.aclose()

    async def verify_provider(self) -> None:
        """Fail fast when the configured embedding/LLM backend is unreachable.

        Raises:
            SystemExit: When the provider health check fails.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper().verify_provider())  # doctest: +SKIP
        """
        if self._config.provider is not Provider.OLLAMA:
            return
        url = self._config.ollama_base_url
        try:
            response = await self._client.get(f"{url}/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SystemExit(
                f"Cannot reach Ollama at {url} ({exc}). "
                "On the host: run `ollama serve` and `ollama pull bge-m3`. "
                "Inside the devcontainer use "
                "OLLAMA_BASE_URL=http://host.docker.internal:11434 "
                "(default in .devcontainer/docker-compose.yml)."
            ) from exc

    async def embed(self, text: str) -> list[float]:
        """Embed a single text string.

        Args:
            text: Input text to embed.

        Returns:
            Normalized embedding vector of length ``embedding_dim``.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> wrapper = UnifiedLLMWrapper()
            >>> asyncio.run(wrapper.aclose())  # doctest: +SKIP
        """
        vectors = await self.embed_batch([text])
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed multiple text strings in provider-specific batches.

        Args:
            texts: Input strings to embed.

        Returns:
            List of normalized embedding vectors, one per input string.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper().embed_batch(["hello"]))  # doctest: +SKIP
        """
        if not texts:
            return []
        if self._config.provider is Provider.OPENAI:
            return await self._openai_embed_batch(texts)
        if self._config.provider is Provider.OLLAMA:
            return await self._ollama_embed_batch(texts)
        return await self._vllm_embed_batch(texts)

    async def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        temperature: float = 0.1,
    ) -> str:
        """Generate text from a prompt using the configured LLM provider.

        Args:
            prompt: User prompt sent to the chat/completions API.
            system: Optional system instructions passed as a separate message.
            temperature: Sampling temperature passed to the provider.

        Returns:
            Stripped model response text.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper().generate("Hello"))  # doctest: +SKIP
        """
        prompt_size = len(prompt) + len(system or "")
        started = time.perf_counter()
        result = ""
        try:
            if self._config.provider is Provider.OPENAI:
                result = await self._openai_generate(
                    prompt,
                    system=system,
                    temperature=temperature,
                )
            elif self._config.provider is Provider.OLLAMA:
                result = await self._ollama_generate(
                    prompt,
                    system=system,
                    temperature=temperature,
                )
            else:
                result = await self._vllm_generate(
                    prompt,
                    system=system,
                    temperature=temperature,
                )
            return result
        finally:
            _log_llm_generate_stats(
                elapsed_seconds=time.perf_counter() - started,
                prompt_size=prompt_size,
                output_size=len(result),
                provider=self._config.provider,
                model=self._config.llm_model,
            )

    async def _openai_embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings from the OpenAI-compatible embeddings API.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper()._openai_embed_batch(["a"]))  # doctest: +SKIP
        """
        headers = {"Content-Type": "application/json"}
        if self._config.openai_api_key:
            headers["Authorization"] = f"Bearer {self._config.openai_api_key}"
        payload: dict[str, Any] = {
            "model": self._config.embedding_model,
            "input": texts,
            "dimensions": self._config.embedding_dim,
        }
        response = await self._client.post(
            f"{self._config.openai_base_url}/embeddings",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [
            _normalize_embedding(item["embedding"], self._config.embedding_dim)
            for item in sorted(data, key=lambda item: item["index"])
        ]

    async def _openai_generate(
        self,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
    ) -> str:
        """Request chat completion from the OpenAI-compatible API.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper()._openai_generate("hi", system="sys", temperature=0.1))  # doctest: +SKIP
        """
        headers = {"Content-Type": "application/json"}
        if self._config.openai_api_key:
            headers["Authorization"] = f"Bearer {self._config.openai_api_key}"
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self._config.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        response = await self._client.post(
            f"{self._config.openai_base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()

    async def _ollama_embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings from the Ollama embeddings API.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper()._ollama_embed_batch(["a"]))  # doctest: +SKIP
        """
        vectors: list[list[float]] = []
        for text in texts:
            response = await self._client.post(
                f"{self._config.ollama_base_url}/api/embeddings",
                json={"model": self._config.embedding_model, "prompt": text},
            )
            response.raise_for_status()
            vectors.append(
                _normalize_embedding(
                    response.json()["embedding"],
                    self._config.embedding_dim,
                )
            )
        return vectors

    async def _ollama_generate(
        self,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
    ) -> str:
        """Request chat completion from the Ollama chat API.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper()._ollama_generate("hi", system="sys", temperature=0.1))  # doctest: +SKIP
        """
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = await self._client.post(
            f"{self._config.ollama_base_url}/api/chat",
            json={
                "model": self._config.llm_model,
                "messages": messages,
                "stream": False,
                "options": {"temperature": temperature},
            },
        )
        response.raise_for_status()
        return response.json()["message"]["content"].strip()

    async def _vllm_embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Request embeddings from the vLLM OpenAI-compatible API.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper()._vllm_embed_batch(["a"]))  # doctest: +SKIP
        """
        headers = {"Content-Type": "application/json"}
        if self._config.openai_api_key:
            headers["Authorization"] = f"Bearer {self._config.openai_api_key}"
        payload = {
            "model": self._config.embedding_model,
            "input": texts,
        }
        response = await self._client.post(
            f"{self._config.vllm_base_url}/embeddings",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()["data"]
        return [
            _normalize_embedding(item["embedding"], self._config.embedding_dim)
            for item in sorted(data, key=lambda item: item["index"])
        ]

    async def _vllm_generate(
        self,
        prompt: str,
        *,
        system: str | None,
        temperature: float,
    ) -> str:
        """Request chat completion from the vLLM OpenAI-compatible API.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper()._vllm_generate("hi", system="sys", temperature=0.1))  # doctest: +SKIP
        """
        headers = {"Content-Type": "application/json"}
        if self._config.openai_api_key:
            headers["Authorization"] = f"Bearer {self._config.openai_api_key}"
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = {
            "model": self._config.llm_model,
            "messages": messages,
            "temperature": temperature,
        }
        response = await self._client.post(
            f"{self._config.vllm_base_url}/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
