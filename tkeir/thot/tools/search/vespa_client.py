"""Title: Vespa client

Vespa HTTP client for 2-level document/chunk indexing and search.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from thot.core.ThotLogger import ThotLogger
from thot.tools.search.chunk_index_labels import strip_chunk_index_protocol

_ILLEGAL_STRING_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_CONTEXT_BEFORE_TAG_RE = re.compile(r"\[CONTEXT_BEFORE\]\s*", re.IGNORECASE)
_CONTEXT_AFTER_TAG_RE = re.compile(r"\s*\[CONTEXT_AFTER\]\s*", re.IGNORECASE)
_WHITESPACE_RE = re.compile(r"\s+")


def sanitize_vespa_string(value: str) -> str:
    """Remove control characters rejected by Vespa string fields.

    Args:
        value: Raw string that may contain illegal control characters.

    Returns:
        Sanitized string safe to index in Vespa.

    Example:
        >>> from thot.tools.search.vespa_client import sanitize_vespa_string
        >>> sanitize_vespa_string("hello\\fworld")
        'hello world'
    """
    return _ILLEGAL_STRING_CHARS.sub(" ", value or "").strip()


def sanitize_vespa_strings(values: list[str]) -> list[str]:
    """Sanitize a list of strings for Vespa indexing.

    Args:
        values: Candidate string field values.

    Returns:
        Sanitized non-empty strings.

    Example:
        >>> from thot.tools.search.vespa_client import sanitize_vespa_strings
        >>> sanitize_vespa_strings(["ok", "bad\\f", ""])
        ['ok', 'bad', '']
    """
    return [
        sanitize_vespa_string(value) for value in values if value is not None
    ]


def strip_search_vector_payload(payload: str) -> str:
    """Return searchable chunk text without context padding tags.

    Args:
        payload: Golden chunk ``search_vector_payload`` value.

    Returns:
        Text with ``[CONTEXT_BEFORE]`` / ``[CONTEXT_AFTER]`` removed.

    Example:
        >>> from thot.tools.search.vespa_client import strip_search_vector_payload
        >>> strip_search_vector_payload(
        ...     "[CONTEXT_BEFORE] intro Core text [CONTEXT_AFTER] outro"
        ... )
        'intro Core text outro'
    """
    text = payload or ""
    text = _CONTEXT_BEFORE_TAG_RE.sub("", text)
    text = _CONTEXT_AFTER_TAG_RE.sub(" ", text)
    return sanitize_vespa_string(_WHITESPACE_RE.sub(" ", text))


def clean_chunk_text_for_prompt(text: str) -> str:
    """Remove indexing metadata wrappers from chunk text for LLM prompts.

    Example:
        >>> from thot.tools.search.vespa_client import clean_chunk_text_for_prompt
        >>> sample = (
        ...     'Active entities: Taylor. Topic: critic regards song '
        ...     'George Harrison liked Abbey Road.'
        ... )
        >>> cleaned = clean_chunk_text_for_prompt(sample)
        >>> 'Active entities' not in cleaned
        True
        >>> 'George Harrison' in cleaned
        True
    """
    cleaned = strip_search_vector_payload(text)
    cleaned = strip_chunk_index_protocol(cleaned)
    return sanitize_vespa_string(_WHITESPACE_RE.sub(" ", cleaned)).strip()


def trim_passage_leading_noise(text: str, focal_entity: str = "") -> str:
    """Drop leading noise before the focal entity when possible.

    Example:
        >>> sample = (
        ...     'Donate Create account Log in Claudio Miranda '
        ...     'Claudio Miranda , ASC is a cinematographer.'
        ... )
        >>> trimmed = trim_passage_leading_noise(sample, "Claudio Miranda")
        >>> trimmed.startswith("Claudio Miranda")
        True
    """
    cleaned = clean_chunk_text_for_prompt(text).strip()
    if not cleaned:
        return cleaned

    focal = (focal_entity or "").strip()
    if focal:
        match = re.search(re.escape(focal), cleaned, re.I)
        if match and match.start() > 20:
            cleaned = cleaned[match.start() :].lstrip(" ,.;:")
    return cleaned


def chunk_embedding_text(chunk: dict[str, Any]) -> str:
    """Select the text used for chunk vector indexing.

    Args:
        chunk: Golden chunk dict from pipeline output.

    Returns:
        Cleaned ``search_vector_payload`` when present, otherwise ``text_raw``.

    Example:
        >>> from thot.tools.search.vespa_client import chunk_embedding_text
        >>> chunk_embedding_text({
        ...     "text_raw": "Core",
        ...     "search_vector_payload": "[CONTEXT_BEFORE] ctx Core [CONTEXT_AFTER]",
        ... })
        'ctx Core'
    """
    payload = (chunk.get("search_vector_payload") or "").strip()
    if payload:
        return strip_search_vector_payload(payload)
    return sanitize_vespa_string(chunk.get("text_raw") or "")


def stable_document_key(source_doc_id: str) -> str:
    """Derive a stable Vespa document key from ``source_doc_id``.

    Args:
        source_doc_id: Pipeline document identifier (often a ``file://`` URI).

    Returns:
        32-character hexadecimal hash prefix.

    Example:
        >>> from thot.tools.search.vespa_client import stable_document_key
        >>> len(stable_document_key("file://tests/indexing/input/doc.pdf"))
        32
    """
    digest = hashlib.sha256(source_doc_id.encode("utf-8")).hexdigest()[:32]
    return digest


def normalize_user_space(user_space: str | None = None) -> str:
    """Normalize a streaming group / user-space name for Vespa.

    Args:
        user_space: Explicit space, or ``None`` to read ``VESPA_USER_SPACE``
            (fallback ``dev@tkeir`` for local/dev when unset).

    Returns:
        Safe non-empty group name.

    Example:
        >>> from thot.tools.search.vespa_client import normalize_user_space
        >>> normalize_user_space("alice@example.com")
        'alice@example.com'
        >>> normalize_user_space("bad:group")
        'bad_group'
        >>> normalize_user_space("dev@tkeir")
        'dev@tkeir'
    """
    from thot.tools.search.user_space import DEV_USER_SPACE

    if user_space is None:
        raw = os.getenv("VESPA_USER_SPACE", DEV_USER_SPACE)
    else:
        raw = user_space
    value = (raw or DEV_USER_SPACE).strip() or DEV_USER_SPACE
    # ':' separates id components; keep common identity punctuation.
    return re.sub(r"[^A-Za-z0-9._@+-]+", "_", value)[:200]


def document_vespa_id(
    source_doc_id: str, *, user_space: str | None = None
) -> str:
    """Build the Vespa document reference for a parent document.

    Streaming mode requires a group (``g=<user_space>``) so each user's
    corpus is co-located and searched via ``streaming.groupname``.

    Args:
        source_doc_id: Pipeline ``source_doc_id`` value.
        user_space: Streaming group; defaults to ``VESPA_USER_SPACE`` / default.

    Returns:
        Vespa id string for schema ``tkeir_document``.

    Example:
        >>> from thot.tools.search.vespa_client import document_vespa_id
        >>> document_vespa_id("file://doc.pdf", user_space="demo").startswith(
        ...     "id:default:tkeir_document:g=demo:"
        ... )
        True
    """
    group = normalize_user_space(user_space)
    return (
        f"id:default:tkeir_document:g={group}:"
        f"{stable_document_key(source_doc_id)}"
    )


def chunk_vespa_id(chunk_id: str, *, user_space: str | None = None) -> str:
    """Build the Vespa document reference for a chunk.

    Args:
        chunk_id: Golden chunk identifier.
        user_space: Streaming group; defaults to ``VESPA_USER_SPACE`` / default.

    Returns:
        Vespa id string for schema ``chunk``.

    Example:
        >>> from thot.tools.search.vespa_client import chunk_vespa_id
        >>> chunk_vespa_id("doc.pdf#chunk-0", user_space="demo").startswith(
        ...     "id:default:chunk:g=demo:"
        ... )
        True
    """
    group = normalize_user_space(user_space)
    digest = hashlib.sha256(chunk_id.encode("utf-8")).hexdigest()[:32]
    return f"id:default:chunk:g={group}:{digest}"


def build_questions_tensor(
    embeddings: list[list[float]],
    embedding_dim: int = 384,
) -> dict[str, list[float]]:
    """Format question embeddings for Vespa mapped tensor input.

    Args:
        embeddings: Batch of embedding vectors.
        embedding_dim: Target dimensionality (truncates longer vectors).

    Returns:
        Dict keyed by string indices for Vespa ``questions_embeddings``.

    Example:
        >>> from thot.tools.search.vespa_client import build_questions_tensor
        >>> build_questions_tensor([[0.1, 0.2]], embedding_dim=2)
        {'0': [0.1, 0.2]}
    """
    if not embeddings:
        return {}
    return {
        str(index): vector[:embedding_dim]
        for index, vector in enumerate(embeddings)
    }


def build_chunk_tensor(
    embedding: list[float],
    embedding_dim: int = 384,
) -> list[float]:
    """Truncate a chunk embedding vector to the schema dimension.

    Args:
        embedding: Raw embedding vector from the LLM provider.
        embedding_dim: Vespa tensor width.

    Returns:
        Truncated float list.

    Example:
        >>> from thot.tools.search.vespa_client import build_chunk_tensor
        >>> build_chunk_tensor([1.0, 2.0, 3.0], embedding_dim=2)
        [1.0, 2.0]
    """
    return embedding[:embedding_dim]


def escape_yql_literal(value: str) -> str:
    """Escape a user query for safe inclusion in YQL string literals.

    Args:
        value: Raw user query text.

    Returns:
        Escaped string safe to embed in double quotes.

    Example:
        >>> from thot.tools.search.vespa_client import escape_yql_literal
        >>> escape_yql_literal('say "hello"').startswith("say ")
        True
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def build_field_contains_or_clause(field: str, query_text: str) -> str | None:
    """Build a YQL ``<field> contains`` clause with phrase and per-term OR.

    Example:
        >>> build_field_contains_or_clause("parent_title", "Michael Chang")
        '(parent_title contains "Michael Chang" OR parent_title contains "Michael" OR parent_title contains "Chang")'
    """
    terms: list[str] = []
    seen: set[str] = set()
    for term in _WHITESPACE_RE.split((query_text or "").strip()):
        if not term:
            continue
        key = term.lower()
        if key in seen:
            continue
        seen.add(key)
        terms.append(term)
    if not terms:
        return None
    if len(terms) == 1:
        return f'{field} contains "{escape_yql_literal(terms[0])}"'
    phrase = " ".join(terms)
    clauses = [
        f'{field} contains "{escape_yql_literal(phrase)}"',
        *(f'{field} contains "{escape_yql_literal(term)}"' for term in terms),
    ]
    return "(" + " OR ".join(clauses) + ")"


def build_text_raw_contains_or_clause(query_text: str) -> str | None:
    """Build a YQL ``text_raw contains`` clause for hybrid keyword retrieval.

    Vespa ``contains`` on a multi-word string requires every term (AND). This
    helper adds a phrase clause for the full query plus per-term OR clauses so
    entity names like ``Charles Sutton`` match indexed chunk text.

    Args:
        query_text: Raw user query.

    Returns:
        YQL fragment, or ``None`` when there are no searchable terms.

    Example:
        >>> from thot.tools.search.vespa_client import build_text_raw_contains_or_clause
        >>> build_text_raw_contains_or_clause("Michael Chang")
        '(text_raw contains "Michael Chang" OR text_raw contains "Michael" OR text_raw contains "Chang")'
    """
    return build_field_contains_or_clause("text_raw", query_text)


def build_multi_field_contains_or_clause(
    terms: list[str],
    *,
    fields: tuple[str, ...],
) -> str | None:
    """Build OR clauses across multiple BM25 fields for each search term.

    Example:
        >>> build_multi_field_contains_or_clause(
        ...     ["Microsoft"],
        ...     fields=("text_raw", "parent_title"),
        ... )
        '(text_raw contains "Microsoft" OR parent_title contains "Microsoft")'
    """
    if not terms or not fields:
        return None
    per_term: list[str] = []
    seen: set[str] = set()
    for term in terms:
        cleaned = (term or "").strip()
        if not cleaned:
            continue
        key = cleaned.lower()
        if key in seen:
            continue
        seen.add(key)
        field_clauses = [
            clause
            for field in fields
            if (clause := build_field_contains_or_clause(field, cleaned))
        ]
        if field_clauses:
            per_term.append("(" + " OR ".join(field_clauses) + ")")
    if not per_term:
        return None
    if len(per_term) == 1:
        return per_term[0]
    return "(" + " OR ".join(per_term) + ")"


@dataclass(frozen=True)
class VespaConfig:
    document_api_url: str
    search_api_url: str
    config_server_url_base: str
    timeout_seconds: float
    embedding_dim: int
    user_space: str = "dev@tkeir"

    @classmethod
    def from_env(cls) -> VespaConfig:
        """Build Vespa client settings from environment / rag.yaml / defaults.

        Resolution order (highest wins):
        1. ``VESPA_URL``, ``VESPA_CONFIG_URL``, ``VESPA_TIMEOUT_SECONDS``,
           ``VESPA_USER_SPACE``, ``EMBEDDING_DIM``
        2. ``configs/rag.yaml`` ``vespa:`` / ``models.embedding_dim``
        3. ``http://localhost:8080``, ``:19071``, ``60s``, space ``dev@tkeir``,
           dim ``384``

        Returns:
            Frozen configuration for :class:`VespaClient`.

        Example:
            >>> from thot.tools.search.vespa_client import VespaConfig
            >>> cfg = VespaConfig.from_env()
            >>> cfg.embedding_dim
            384
            >>> bool(cfg.user_space)
            True
        """
        from thot.core.LlmWrapper import WrapperConfig
        from thot.tools.search.rag_config import load_rag_config

        try:
            rag_vespa = load_rag_config().vespa
        except Exception:  # noqa: BLE001
            from thot.tools.search.rag_config import RagVespaConfig

            rag_vespa = RagVespaConfig()

        base_url = os.getenv("VESPA_URL", rag_vespa.url).rstrip("/")
        config_url = os.getenv(
            "VESPA_CONFIG_URL", rag_vespa.config_url
        ).rstrip("/")
        timeout_raw = os.getenv(
            "VESPA_TIMEOUT_SECONDS", str(rag_vespa.timeout_seconds)
        )
        user_space = normalize_user_space(
            os.getenv("VESPA_USER_SPACE", rag_vespa.user_space)
        )
        models = WrapperConfig.from_env()
        return cls(
            document_api_url=f"{base_url}/document/v1",
            search_api_url=f"{base_url}/search/",
            config_server_url_base=config_url,
            timeout_seconds=float(timeout_raw),
            embedding_dim=models.embedding_dim,
            user_space=user_space,
        )

    def config_server_url(self) -> str:
        """Return the Vespa config server base URL.

        Returns:
            Config server URL without a trailing slash.

        Example:
            >>> from thot.tools.search.vespa_client import VespaConfig
            >>> VespaConfig(
            ...     document_api_url="http://localhost:8080/document/v1",
            ...     search_api_url="http://localhost:8080/search/",
            ...     config_server_url_base="http://localhost:19071",
            ...     timeout_seconds=60.0,
            ...     embedding_dim=384,
            ... ).config_server_url()
            'http://localhost:19071'
        """
        return self.config_server_url_base


class VespaClient:
    """Async HTTP client for Vespa document indexing and hybrid search."""

    def __init__(
        self,
        config: VespaConfig | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        """Initialize the client with optional config and HTTP client.

        Args:
            config: Vespa endpoint settings; defaults to
                :meth:`VespaConfig.from_env`.
            client: Shared async HTTP client; a new client is created when
                omitted.

        Example:
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> client = VespaClient()
            >>> client.config.embedding_dim > 0
            True
        """
        self._config = config or VespaConfig.from_env()
        self._client = client or httpx.AsyncClient(
            timeout=self._config.timeout_seconds
        )
        self._owns_client = client is None

    async def aclose(self) -> None:
        """Close the owned HTTP client when this client created it.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient().aclose())  # doctest: +SKIP
        """
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> VespaClient:
        """Enter an async context manager returning this client.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> async def _demo():
            ...     async with VespaClient() as client:
            ...         return client.config.embedding_dim
            >>> asyncio.run(_demo())  # doctest: +SKIP
        """
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Exit the async context manager and close owned resources.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient().__aexit__(None, None, None))  # doctest: +SKIP
        """
        await self.aclose()

    async def health(self) -> bool:
        """Check whether Vespa is ready for document indexing.

        Verifies the config server is up, the default application is deployed,
        and the document API accepts connections.

        Returns:
            ``True`` when Vespa is ready to index documents.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient().health())  # doctest: +SKIP
        """
        if not await self._config_server_healthy():
            return False
        return await self._application_ready()

    async def _config_server_healthy(self) -> bool:
        """Return whether the Vespa config server health endpoint is up.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient()._config_server_healthy())  # doctest: +SKIP
        """
        try:
            response = await self._client.get(
                f"{self._config.config_server_url()}/state/v1/health",
            )
            if response.status_code != 200:
                return False
            payload = response.json()
            code = str((payload.get("status") or {}).get("code", "")).lower()
            return code in {"up", "ok", "green"}
        except httpx.HTTPError:
            return False

    async def _application_ready(self) -> bool:
        """Return whether the default application and document API are ready.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient()._application_ready())  # doctest: +SKIP
        """
        try:
            app_url = (
                f"{self._config.config_server_url()}"
                "/application/v2/tenant/default/application/default"
            )
            response = await self._client.get(app_url)
            if response.status_code != 200:
                return False
            doc_root = f"{self._config.document_api_url}/"
            probe = await self._client.get(doc_root, timeout=10.0)
            return probe.status_code < 500
        except httpx.HTTPError:
            return False

    async def _upsert_fields(
        self,
        namespace: str,
        document_type: str,
        document_key: str,
        fields: dict[str, Any],
        *,
        user_space: str | None = None,
    ) -> None:
        """POST document fields to the Vespa document API (streaming group).

        Args:
            namespace: Vespa namespace (for example ``default``).
            document_type: Schema name (for example ``chunk``).
            document_key: Stable document key within the schema.
            fields: Field payload indexed by Vespa.
            user_space: Streaming group; defaults to client config.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient()._upsert_fields("default", "chunk", "k", {}))  # doctest: +SKIP
        """
        group = normalize_user_space(user_space or self._config.user_space)
        url = (
            f"{self._config.document_api_url}/{namespace}/{document_type}/"
            f"group/{quote(group, safe='')}/"
            f"{quote(document_key, safe='')}"
        )
        response = await self._client.post(url, json={"fields": fields})
        if response.is_error:
            detail = response.text.strip()
            raise httpx.HTTPStatusError(
                f"{response.status_code} for {url}: {detail}",
                request=response.request,
                response=response,
            )

    async def upsert_document(
        self,
        fields: dict[str, Any],
        source_doc_id: str,
        *,
        user_space: str | None = None,
    ) -> None:
        """Create or update a parent ``tkeir_document`` record.

        Args:
            fields: Sanitized parent document fields.
            source_doc_id: Pipeline ``source_doc_id`` used to derive the key.
            user_space: Streaming group for this user's corpus.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient().upsert_document({"title": "Doc"}, "doc.pdf"))  # doctest: +SKIP
        """
        space = normalize_user_space(user_space or self._config.user_space)
        payload = dict(fields)
        payload.setdefault("user_space", space)
        await self._upsert_fields(
            "default",
            "tkeir_document",
            stable_document_key(source_doc_id),
            payload,
            user_space=space,
        )

    async def upsert_chunk(
        self,
        fields: dict[str, Any],
        chunk_id: str,
        *,
        user_space: str | None = None,
    ) -> None:
        """Create or update a ``chunk`` record linked to a parent document.

        Args:
            fields: Sanitized chunk fields including embeddings.
            chunk_id: Golden chunk identifier.
            user_space: Streaming group (must match the parent document).

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient().upsert_chunk({"text_raw": "hi"}, "c1"))  # doctest: +SKIP
        """
        space = normalize_user_space(user_space or self._config.user_space)
        _, _, _group, key = _parse_vespa_id(
            chunk_vespa_id(chunk_id, user_space=space)
        )
        payload = dict(fields)
        payload.setdefault("user_space", space)
        await self._upsert_fields(
            "default", "chunk", key, payload, user_space=space
        )

    async def get_document_by_ref(self, doc_ref: str) -> dict[str, Any]:
        """Fetch parent document fields by Vespa document reference.

        Args:
            doc_ref: Full Vespa id for schema ``tkeir_document``.

        Returns:
            Document ``fields`` dict from the Vespa API response.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient, document_vespa_id
            >>> ref = document_vespa_id("file://doc.pdf")
            >>> asyncio.run(VespaClient().get_document_by_ref(ref))  # doctest: +SKIP
        """
        namespace, _schema, group, key = _parse_vespa_id(doc_ref)
        if group:
            url = (
                f"{self._config.document_api_url}/{namespace}/tkeir_document/"
                f"group/{quote(group, safe='')}/{quote(key, safe='')}"
            )
        else:
            url = (
                f"{self._config.document_api_url}/{namespace}/tkeir_document/"
                f"docid/{quote(key, safe='')}"
            )
        response = await self._client.get(url)
        response.raise_for_status()
        payload = response.json()
        return payload.get("fields") or {}

    @property
    def config(self) -> VespaConfig:
        """Return the active Vespa configuration.

        Example:
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> VespaClient().config.embedding_dim
            384
        """
        return self._config

    def build_hybrid_search_payload(
        self,
        query_text: str,
        q_chunk_emb: list[float],
        q_question_emb: list[float],
        *,
        hits: int = 20,
        user_space: str | None = None,
    ) -> dict[str, Any]:
        """Build the Vespa hybrid search HTTP payload without executing it.

        Example:
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> payload = VespaClient().build_hybrid_search_payload(
            ...     "hello", [0.0] * 384, [0.0] * 384, user_space="demo"
            ... )
            >>> payload["ranking.profile"]
            'hybrid_2_level'
            >>> payload["streaming.groupname"]
            'demo'
        """
        text_clause = build_text_raw_contains_or_clause(query_text)
        yql_parts = [
            f'([{{"targetNumHits": {hits}}}]nearestNeighbor(chunk_embedding, q_chunk_emb))',
            f'([{{"targetNumHits": {hits}}}]nearestNeighbor(questions_embeddings, q_question_emb))',
        ]
        if text_clause:
            yql_parts.append(text_clause)
        yql = "select * from chunk where " + " or ".join(yql_parts)
        space = normalize_user_space(user_space or self._config.user_space)
        return {
            "yql": yql,
            "hits": hits,
            "timeout": f"{int(self._config.timeout_seconds)}s",
            "ranking.profile": "hybrid_2_level",
            "streaming.groupname": space,
            "input.query(q_chunk_emb)": q_chunk_emb[
                : self._config.embedding_dim
            ],
            "input.query(q_question_emb)": q_question_emb[
                : self._config.embedding_dim
            ],
        }

    async def hybrid_search(
        self,
        query_text: str,
        q_chunk_emb: list[float],
        q_question_emb: list[float],
        *,
        hits: int = 20,
        user_space: str | None = None,
    ) -> dict[str, Any]:
        """Run hybrid vector and keyword search over chunk documents.

        Args:
            query_text: User query matched against ``text_raw``.
            q_chunk_emb: Query embedding for ``chunk_embedding`` NN search.
            q_question_emb: Query embedding for ``questions_embeddings`` NN search.
            hits: Maximum number of hits to request.
            user_space: Streaming group to search (required for isolation).

        Returns:
            Parsed JSON response from the Vespa search API.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient().hybrid_search("hello", [0.0]*384, [0.0]*384))  # doctest: +SKIP
        """
        payload = self.build_hybrid_search_payload(
            query_text,
            q_chunk_emb,
            q_question_emb,
            hits=hits,
            user_space=user_space,
        )
        ThotLogger.info(
            f"Vespa hybrid search query={query_text!r} "
            f"group={payload.get('streaming.groupname')!r} yql={payload['yql']}"
        )
        response = await self._client.post(
            self._config.search_api_url,
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    async def search(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute a pre-built Vespa search payload.

        Example:
            >>> import asyncio
            >>> from thot.tools.search.vespa_client import VespaClient
            >>> asyncio.run(VespaClient().search({"yql": "select * from chunk where true"}))  # doctest: +SKIP
        """
        response = await self._client.post(
            self._config.search_api_url,
            json=payload,
        )
        if response.is_error:
            ThotLogger.error(
                "Vespa search failed "
                + f"status={response.status_code} "
                + f"body={response.text[:500]}"
            )
        response.raise_for_status()
        return response.json()


def _parse_vespa_id(doc_id: str) -> tuple[str, str, str | None, str]:
    """Split a Vespa document id into namespace, schema, group, and key.

    Args:
        doc_id: Vespa id ``id:ns:type:g=group:key`` or ``id:ns:type::key``.

    Returns:
        Tuple ``(namespace, schema, group_or_none, key)``.

    Raises:
        ValueError: When ``doc_id`` does not match the expected format.

    Example:
        >>> from thot.tools.search.vespa_client import _parse_vespa_id
        >>> _parse_vespa_id("id:default:tkeir_document:g=demo:abc123")
        ('default', 'tkeir_document', 'demo', 'abc123')
        >>> _parse_vespa_id("id:default:chunk::legacy")
        ('default', 'chunk', None, 'legacy')
    """
    grouped = re.match(r"id:([^:]+):([^:]+):g=([^:]+):(.+)", doc_id)
    if grouped:
        return (
            grouped.group(1),
            grouped.group(2),
            grouped.group(3),
            grouped.group(4),
        )
    match = re.match(r"id:([^:]+):([^:]+)::(.+)", doc_id)
    if not match:
        raise ValueError(f"Invalid Vespa document id: {doc_id}")
    return match.group(1), match.group(2), None, match.group(3)
