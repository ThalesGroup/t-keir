"""Title: Llm Wrapper

Unified embedding and LLM wrapper for OpenAI, Ollama, and vLLM.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import asyncio
import math
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


class RerankStrategy(str, Enum):
    """Supported second-stage rerank strategies."""

    CROSS_ENCODER = "cross_encoder"
    EMBEDDING_COSINE = "embedding_cosine"


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
# HuggingFace CrossEncoder id (sentence-transformers).
DEFAULT_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
DEFAULT_RERANKER_MODELS = {
    Provider.OPENAI: DEFAULT_RERANKER_MODEL,
    Provider.OLLAMA: DEFAULT_RERANKER_MODEL,
    Provider.VLLM: DEFAULT_RERANKER_MODEL,
}
DEFAULT_RERANK_STRATEGY = RerankStrategy.CROSS_ENCODER
_ALLOWED_RERANK_STRATEGIES = frozenset(
    strategy.value for strategy in RerankStrategy
)


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


def _first_non_empty(*values: object) -> str | None:
    """Return the first non-empty stripped string among ``values``.

    Example:
        >>> from thot.core.LlmWrapper import _first_non_empty
        >>> _first_non_empty("", None, "  bge-m3  ")
        'bge-m3'
    """
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _load_file_model_overrides() -> dict[str, Any]:
    """Load optional ``models`` overrides from ``configs/rag.yaml``.

    Returns:
        Mapping of model keys, or ``{}`` when the file is missing/unreadable.

    Example:
        >>> isinstance(_load_file_model_overrides(), dict)
        True
    """
    try:
        from thot.tools.search.rag_config import load_rag_config

        config = load_rag_config()
        models = config.models
    except Exception:  # noqa: BLE001
        return {}
    return {
        "provider": models.provider,
        "embedding_model": models.embedding_model,
        "llm_model": models.llm_model,
        "reranker_model": models.reranker_model,
        "embedding_dim": models.embedding_dim,
        "rerank_strategy": config.search.rerank.strategy,
    }


def _normalize_rerank_strategy(value: object) -> str:
    """Normalize a rerank strategy name to a supported value.

    Example:
        >>> from thot.core.LlmWrapper import _normalize_rerank_strategy
        >>> _normalize_rerank_strategy("EMBEDDING_COSINE")
        'embedding_cosine'
    """
    strategy = str(value or DEFAULT_RERANK_STRATEGY.value).strip().lower()
    if strategy not in _ALLOWED_RERANK_STRATEGIES:
        return DEFAULT_RERANK_STRATEGY.value
    return strategy


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    """Return cosine similarity of two equal-length vectors.

    Example:
        >>> from thot.core.LlmWrapper import _cosine_similarity
        >>> round(_cosine_similarity([1.0, 0.0], [1.0, 0.0]), 3)
        1.0
    """
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_left = math.sqrt(sum(a * a for a in left))
    norm_right = math.sqrt(sum(b * b for b in right))
    if norm_left == 0.0 or norm_right == 0.0:
        return 0.0
    return float(dot / (norm_left * norm_right))


@dataclass(frozen=True)
class WrapperConfig:
    provider: Provider
    embedding_model: str
    llm_model: str
    reranker_model: str
    rerank_strategy: str
    embedding_dim: int
    timeout_seconds: float
    openai_api_key: str | None
    openai_base_url: str
    ollama_base_url: str
    vllm_base_url: str

    @classmethod
    def from_env(
        cls,
        file_models: dict[str, Any] | None = None,
    ) -> WrapperConfig:
        """Build configuration: environment → config file → defaults.

        Resolution order for each model field:

        1. Environment variable (``PROVIDER``, ``EMBEDDING_MODEL``,
           ``LLM_MODEL``, ``RERANKER_MODEL``, ``RERANK_STRATEGY``,
           ``EMBEDDING_DIM``)
        2. ``configs/rag.yaml`` → ``models:`` / ``search.rerank.strategy``
        3. Provider-specific hard-coded defaults

        Args:
            file_models: Optional mapping already loaded from YAML. When
                ``None``, reads ``rag.yaml`` automatically.

        Returns:
            Frozen configuration used by :class:`UnifiedLLMWrapper`.

        Example:
            >>> import os
            >>> from thot.core.LlmWrapper import WrapperConfig, Provider
            >>> os.environ["PROVIDER"] = "ollama"
            >>> cfg = WrapperConfig.from_env(file_models={})
            >>> cfg.provider is Provider.OLLAMA
            True
        """
        file_cfg = (
            dict(file_models)
            if file_models is not None
            else _load_file_model_overrides()
        )
        provider_name = (
            _first_non_empty(
                os.getenv("PROVIDER"),
                file_cfg.get("provider"),
                Provider.OLLAMA.value,
            )
            or Provider.OLLAMA.value
        ).lower()
        provider = Provider(provider_name)
        embedding_dim_raw = _first_non_empty(
            os.getenv("EMBEDDING_DIM"),
            file_cfg.get("embedding_dim"),
            str(DEFAULT_EMBEDDING_DIM),
        )
        return cls(
            provider=provider,
            embedding_model=_first_non_empty(
                os.getenv("EMBEDDING_MODEL"),
                file_cfg.get("embedding_model"),
                DEFAULT_EMBEDDING_MODELS[provider],
            )
            or DEFAULT_EMBEDDING_MODELS[provider],
            llm_model=_first_non_empty(
                os.getenv("LLM_MODEL"),
                file_cfg.get("llm_model"),
                DEFAULT_LLM_MODELS[provider],
            )
            or DEFAULT_LLM_MODELS[provider],
            reranker_model=_first_non_empty(
                os.getenv("RERANKER_MODEL"),
                file_cfg.get("reranker_model"),
                DEFAULT_RERANKER_MODELS[provider],
            )
            or DEFAULT_RERANKER_MODELS[provider],
            rerank_strategy=_normalize_rerank_strategy(
                _first_non_empty(
                    os.getenv("RERANK_STRATEGY"),
                    file_cfg.get("rerank_strategy"),
                    DEFAULT_RERANK_STRATEGY.value,
                )
            ),
            embedding_dim=int(embedding_dim_raw or DEFAULT_EMBEDDING_DIM),
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
        self._cross_encoder = None

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

    async def verify_provider(
        self,
        *,
        pull_missing: bool = False,
        include_reranker: bool = False,
    ) -> None:
        """Fail fast when the configured embedding/LLM backend is unreachable.

        When ``pull_missing`` is True and the provider is Ollama, missing
        embedding / LLM models are pulled automatically. Cross-encoder
        rerankers are HuggingFace models (not Ollama pulls).

        Args:
            pull_missing: Pull absent Ollama models before returning.
            include_reranker: Unused (kept for call-site compatibility).

        Raises:
            SystemExit: When the provider health check fails.

        Example:
            >>> import asyncio
            >>> from thot.core.LlmWrapper import UnifiedLLMWrapper
            >>> asyncio.run(UnifiedLLMWrapper().verify_provider())  # doctest: +SKIP
        """
        del include_reranker
        if self._config.provider is not Provider.OLLAMA:
            return
        url = self._config.ollama_base_url
        try:
            response = await self._client.get(f"{url}/api/tags")
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SystemExit(
                f"Cannot reach Ollama at {url} ({exc}). "
                "On the host: run `ollama serve` and "
                f"`ollama pull {self._config.embedding_model}`. "
                "Inside the devcontainer use "
                "OLLAMA_BASE_URL=http://host.docker.internal:11434 "
                "(default in .devcontainer/docker-compose.yml)."
            ) from exc
        if pull_missing:
            await self.ensure_ollama_models(include_reranker=False)

    async def ensure_ollama_models(
        self,
        *,
        include_reranker: bool = False,
    ) -> None:
        """Pull configured Ollama embedding / LLM models when missing.

        Args:
            include_reranker: Ignored — rerankers use sentence-transformers /
                HuggingFace, not Ollama pulls.

        Example:
            >>> import asyncio
            >>> asyncio.run(UnifiedLLMWrapper().ensure_ollama_models())  # doctest: +SKIP
        """
        del include_reranker
        if self._config.provider is not Provider.OLLAMA:
            return
        for name in (self._config.embedding_model, self._config.llm_model):
            await self._ollama_pull_if_missing(name)

    async def _ollama_local_model_names(self) -> set[str]:
        """Return installed Ollama model names (including tags).

        Example:
            >>> import asyncio
            >>> asyncio.run(UnifiedLLMWrapper()._ollama_local_model_names())  # doctest: +SKIP
            set()
        """
        response = await self._client.get(
            f"{self._config.ollama_base_url}/api/tags"
        )
        response.raise_for_status()
        models = response.json().get("models") or []
        names: set[str] = set()
        for item in models:
            name = str(item.get("name") or "").strip()
            if name:
                names.add(name)
                names.add(name.split(":")[0])
        return names

    async def _ollama_pull_if_missing(self, model: str) -> None:
        """Pull one Ollama model when absent locally.

        Example:
            >>> import asyncio
            >>> asyncio.run(UnifiedLLMWrapper()._ollama_pull_if_missing("bge-m3"))  # doctest: +SKIP
        """
        model = (model or "").strip()
        if not model:
            return
        installed = await self._ollama_local_model_names()
        base = model.split(":")[0]
        if model in installed or base in installed:
            ThotLogger.info(f"Ollama model already present: {model}")
            return
        ThotLogger.info(f"Pulling Ollama model: {model}")
        response = await self._client.post(
            f"{self._config.ollama_base_url}/api/pull",
            json={"name": model, "stream": False},
            timeout=max(self._config.timeout_seconds, 600.0),
        )
        response.raise_for_status()
        ThotLogger.info(f"Pulled Ollama model: {model}")

    async def rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int | None = None,
        strategy: str | None = None,
    ) -> list[dict[str, Any]]:
        """Score documents against ``query`` with the configured strategy.

        Strategies (``RERANK_STRATEGY`` / ``search.rerank.strategy``):

        * ``cross_encoder`` — HuggingFace CrossEncoder via sentence-transformers
          (default ``BAAI/bge-reranker-v2-m3``)
        * ``embedding_cosine`` — embed query + docs with the configured
          embedding provider, rank by cosine similarity

        Args:
            query: User / claim query text.
            documents: Candidate document texts (same order as first stage).
            top_n: Optional max results; defaults to ``len(documents)``.
            strategy: Optional per-call override of ``rerank_strategy``.

        Returns:
            List of ``{"index": int, "relevance_score": float}`` sorted by
            score descending. ``index`` refers to the input ``documents`` list.

        Raises:
            ValueError: When the configured strategy is unknown.
            RuntimeError: When sentence-transformers is missing for
                ``cross_encoder``.

        Example:
            >>> import asyncio
            >>> asyncio.run(UnifiedLLMWrapper().rerank("q", ["a", "b"]))  # doctest: +SKIP
            [{'index': 0, 'relevance_score': 0.9}]
        """
        if not documents:
            return []
        keep = len(documents) if top_n is None else max(1, int(top_n))
        chosen = _normalize_rerank_strategy(
            strategy or self._config.rerank_strategy
        )
        if chosen == RerankStrategy.CROSS_ENCODER.value:
            return await self._cross_encoder_rerank(
                query, documents, top_n=keep
            )
        if chosen == RerankStrategy.EMBEDDING_COSINE.value:
            return await self._embedding_cosine_rerank(
                query, documents, top_n=keep
            )
        raise ValueError(f"Unknown rerank strategy: {chosen!r}")

    def _get_cross_encoder(self):
        """Lazily load the sentence-transformers CrossEncoder.

        Example:
            >>> UnifiedLLMWrapper()._get_cross_encoder()  # doctest: +SKIP
        """
        if self._cross_encoder is None:
            try:
                from sentence_transformers import CrossEncoder
            except ImportError as exc:  # pragma: no cover - env dependent
                raise RuntimeError(
                    "sentence-transformers is required for "
                    "RERANK_STRATEGY=cross_encoder. "
                    "Install with: uv sync  (or uv add sentence-transformers)"
                ) from exc
            ThotLogger.info(
                "Loading CrossEncoder reranker "
                + f"model={self._config.reranker_model}"
            )
            self._cross_encoder = CrossEncoder(self._config.reranker_model)
        return self._cross_encoder

    async def _cross_encoder_rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Rerank with a sentence-transformers CrossEncoder.

        Example:
            >>> import asyncio
            >>> asyncio.run(UnifiedLLMWrapper()._cross_encoder_rerank(
            ...     "q", ["a"], top_n=1,
            ... ))  # doctest: +SKIP
        """
        model = self._get_cross_encoder()
        pairs = [(query, document) for document in documents]

        def _predict() -> list[float]:
            scores = model.predict(pairs, show_progress_bar=False)
            return [float(score) for score in scores]

        scores = await asyncio.to_thread(_predict)
        ranked = [
            {"index": index, "relevance_score": score}
            for index, score in enumerate(scores)
        ]
        ranked.sort(key=lambda row: row["relevance_score"], reverse=True)
        kept = ranked[:top_n]
        ThotLogger.info(
            "LLM rerank strategy=cross_encoder "
            + f"model={self._config.reranker_model} "
            + f"docs={len(documents)} kept={len(kept)}"
        )
        return kept

    async def _embedding_cosine_rerank(
        self,
        query: str,
        documents: list[str],
        *,
        top_n: int,
    ) -> list[dict[str, Any]]:
        """Rerank by cosine similarity of query/document embeddings.

        Example:
            >>> import asyncio
            >>> asyncio.run(UnifiedLLMWrapper()._embedding_cosine_rerank(
            ...     "q", ["a"], top_n=1,
            ... ))  # doctest: +SKIP
        """
        vectors = await self.embed_batch([query, *documents])
        query_vec = vectors[0]
        ranked = [
            {
                "index": index,
                "relevance_score": _cosine_similarity(query_vec, doc_vec),
            }
            for index, doc_vec in enumerate(vectors[1:])
        ]
        ranked.sort(key=lambda row: row["relevance_score"], reverse=True)
        kept = ranked[:top_n]
        ThotLogger.info(
            "LLM rerank strategy=embedding_cosine "
            + f"model={self._config.embedding_model} "
            + f"docs={len(documents)} kept={len(kept)}"
        )
        return kept

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
