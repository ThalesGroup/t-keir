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


def global_vespa_id(passage_id: str) -> str:
    """Build Vespa id for schema ``global`` (index mode, no streaming group).

    Args:
        passage_id: Stable passage key (e.g. ``beir:scifact:42#chunk-0``).

    Returns:
        ``id:default:global::…`` document reference.

    Example:
        >>> global_vespa_id("beir:scifact:42#chunk-0").startswith("id:default:global::")
        True
    """
    digest = hashlib.sha256(passage_id.encode("utf-8")).hexdigest()[:40]
    return f"id:default:global::{digest}"


def user_vespa_id(passage_id: str, *, user_space: str | None = None) -> str:
    """Build Vespa id for schema ``user`` (streaming mode with group).

    Args:
        passage_id: Stable passage key.
        user_space: Streaming group (``streaming.groupname``).

    Returns:
        ``id:default:user:g=<space>:…`` document reference.

    Example:
        >>> user_vespa_id("chunk-1", user_space="demo").startswith("id:default:user:g=demo:")
        True
    """
    group = normalize_user_space(user_space)
    digest = hashlib.sha256(passage_id.encode("utf-8")).hexdigest()[:40]
    return f"id:default:user:g={group}:{digest}"


def document_vespa_id(
    source_doc_id: str, *, user_space: str | None = None
) -> str:
    """Compatibility alias → :func:`user_vespa_id` (streaming user schema).

    Example:
        >>> document_vespa_id("file://doc.pdf", user_space="demo").startswith("id:default:user:g=demo:")
        True
    """
    return user_vespa_id(source_doc_id, user_space=user_space)


def chunk_vespa_id(chunk_id: str, *, user_space: str | None = None) -> str:
    """Compatibility alias → :func:`user_vespa_id`.

    Example:
        >>> chunk_vespa_id("doc.pdf#chunk-0", user_space="demo").startswith("id:default:user:g=demo:")
        True
    """
    return user_vespa_id(chunk_id, user_space=user_space)


def build_chunk_tensor(
    embedding: list[float],
    embedding_dim: int = 1024,
) -> list[float]:
    """Truncate a dense embedding to the schema dimension.

    Example:
        >>> build_chunk_tensor([1.0, 2.0, 3.0], embedding_dim=2)
        [1.0, 2.0]
    """
    values = [float(x) for x in embedding[:embedding_dim]]
    if len(values) < embedding_dim:
        values.extend([0.0] * (embedding_dim - len(values)))
    return values[:embedding_dim]


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
    """Frozen Vespa HTTP endpoint and embedding settings.

    Example:
        >>> VespaConfig(
        ...     document_api_url="http://localhost:8080/document/v1",
        ...     search_api_url="http://localhost:8080/search/",
        ...     config_server_url_base="http://localhost:19071",
        ...     timeout_seconds=60.0,
        ...     embedding_dim=1024,
        ... ).embedding_dim
        1024
    """

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
           dim ``1024``

        Returns:
            Frozen configuration for :class:`VespaClient`.

        Example:
            >>> from thot.tools.search.vespa_client import VespaConfig
            >>> cfg = VespaConfig.from_env()
            >>> cfg.embedding_dim
            1024
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
    """Async HTTP client for Vespa document indexing and hybrid search.

    Example:
        >>> VespaClient().config.embedding_dim > 0
        True
    """

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
        streaming: bool = True,
    ) -> None:
        """POST document fields to the Vespa document API.

        Args:
            namespace: Vespa namespace (for example ``default``).
            document_type: Schema name (``global`` or ``user``).
            document_key: Stable document key within the schema.
            fields: Field payload indexed by Vespa.
            user_space: Streaming group (required when ``streaming``).
            streaming: When True, use ``…/group/<space>/<key>`` (user schema).
                When False, use ``…/docid/<key>`` (global index schema).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient._upsert_fields)
            True
        """
        if streaming:
            group = normalize_user_space(user_space or self._config.user_space)
            url = (
                f"{self._config.document_api_url}/{namespace}/{document_type}/"
                f"group/{quote(group, safe='')}/"
                f"{quote(document_key, safe='')}"
            )
        else:
            url = (
                f"{self._config.document_api_url}/{namespace}/{document_type}/"
                f"docid/{quote(document_key, safe='')}"
            )
        response = await self._client.post(url, json={"fields": fields})
        if response.is_error:
            detail = response.text.strip()
            raise httpx.HTTPStatusError(
                f"{response.status_code} for {url}: {detail}",
                request=response.request,
                response=response,
            )

    async def upsert_global_passage(
        self,
        fields: dict[str, Any],
        passage_id: str,
    ) -> None:
        """Create or update a ``global`` (index-mode) passage.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.upsert_global_passage)
            True
        """
        _, _, _group, key = _parse_vespa_id(global_vespa_id(passage_id))
        await self._upsert_fields(
            "default", "global", key, fields, streaming=False
        )

    async def upsert_user_passage(
        self,
        fields: dict[str, Any],
        passage_id: str,
        *,
        user_space: str | None = None,
    ) -> None:
        """Create or update a ``user`` (streaming) passage.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.upsert_user_passage)
            True
        """
        space = normalize_user_space(user_space or self._config.user_space)
        payload = dict(fields)
        payload.setdefault("userspace_id", space)
        _, _, _group, key = _parse_vespa_id(
            user_vespa_id(passage_id, user_space=space)
        )
        await self._upsert_fields(
            "default", "user", key, payload, user_space=space
        )

    async def delete_user_passage(
        self,
        passage_id: str,
        *,
        user_space: str | None = None,
    ) -> bool:
        """Delete one ``user`` (streaming) passage by logical ``chunk_id``.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.delete_user_passage)
            True
        """
        space = normalize_user_space(user_space or self._config.user_space)
        return await self.delete_document_ref(
            user_vespa_id(passage_id, user_space=space)
        )

    async def delete_document_ref(self, doc_ref: str) -> bool:
        """Delete a Vespa document by full ``id:…`` reference. False if missing.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.delete_document_ref)
            True
        """
        namespace, schema, group, key = _parse_vespa_id(doc_ref)
        if group:
            url = (
                f"{self._config.document_api_url}/{namespace}/{schema}/"
                f"group/{quote(group, safe='')}/{quote(key, safe='')}"
            )
        else:
            url = (
                f"{self._config.document_api_url}/{namespace}/{schema}/"
                f"docid/{quote(key, safe='')}"
            )
        response = await self._client.delete(url)
        if response.status_code == 404:
            return False
        if response.is_error:
            detail = response.text.strip()
            raise httpx.HTTPStatusError(
                f"{response.status_code} for {url}: {detail}",
                request=response.request,
                response=response,
            )
        return True

    async def find_user_vespa_ids_by_source_ref(
        self,
        source_ref: str,
        *,
        user_space: str | None = None,
        hits: int = 200,
    ) -> list[str]:
        """Return Vespa document ids in the user group for ``source_ref``.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.find_user_vespa_ids_by_source_ref)
            True
        """
        space = normalize_user_space(user_space or self._config.user_space)
        ref = sanitize_vespa_string(source_ref)
        if not ref:
            return []
        escaped = ref.replace("\\", "\\\\").replace('"', '\\"')
        payload: dict[str, Any] = {
            "yql": (
                f"select source_ref from user where "
                f'source_ref contains "{escaped}" limit {max(1, int(hits))}'
            ),
            "hits": max(1, int(hits)),
            "ranking.profile": "unranked",
            "streaming.groupname": space,
        }
        response = await self.search(payload)
        children = (
            ((response.get("root") or {}).get("children"))
            if isinstance(response, dict)
            else None
        ) or []
        out: list[str] = []
        seen: set[str] = set()
        for child in children:
            if not isinstance(child, dict):
                continue
            fields = child.get("fields") or {}
            if (
                isinstance(fields, dict)
                and str(fields.get("source_ref") or "") != ref
            ):
                continue
            raw_id = str(child.get("id") or "").strip()
            if raw_id.startswith("id:") and raw_id not in seen:
                seen.add(raw_id)
                out.append(raw_id)
        return out

    async def delete_user_passages_by_source_ref(
        self,
        source_ref: str,
        *,
        user_space: str | None = None,
        passage_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Delete streaming passages for a source_ref (catalog and/or search).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.delete_user_passages_by_source_ref)
            True
        """
        space = normalize_user_space(user_space or self._config.user_space)
        deleted = 0
        missing = 0
        refs: list[str] = []
        for passage_id in passage_ids or []:
            refs.append(user_vespa_id(passage_id, user_space=space))
        if not refs:
            refs = await self.find_user_vespa_ids_by_source_ref(
                source_ref, user_space=space
            )
        for doc_ref in refs:
            ok = await self.delete_document_ref(doc_ref)
            if ok:
                deleted += 1
            else:
                missing += 1
        return {
            "source_ref": source_ref,
            "user_space": space,
            "requested": len(refs),
            "deleted": deleted,
            "missing": missing,
            "vespa_ids": refs,
        }

    async def upsert_document(
        self,
        fields: dict[str, Any],
        source_doc_id: str,
        *,
        user_space: str | None = None,
    ) -> None:
        """Compatibility shim → :meth:`upsert_user_passage` (no parent schema).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.upsert_document)
            True
        """
        await self.upsert_user_passage(
            fields, source_doc_id, user_space=user_space
        )

    async def upsert_chunk(
        self,
        fields: dict[str, Any],
        chunk_id: str,
        *,
        user_space: str | None = None,
    ) -> None:
        """Compatibility shim → :meth:`upsert_user_passage`.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.upsert_chunk)
            True
        """
        await self.upsert_user_passage(fields, chunk_id, user_space=user_space)

    async def get_document_by_ref(self, doc_ref: str) -> dict[str, Any]:
        """Fetch passage fields by Vespa document reference (global or user).

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.get_document_by_ref)
            True
        """
        namespace, schema, group, key = _parse_vespa_id(doc_ref)
        schema = schema or "global"
        if group:
            url = (
                f"{self._config.document_api_url}/{namespace}/{schema}/"
                f"group/{quote(group, safe='')}/{quote(key, safe='')}"
            )
        else:
            url = (
                f"{self._config.document_api_url}/{namespace}/{schema}/"
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
            1024
        """
        return self._config

    def build_hybrid_search_payload(
        self,
        query_text: str,
        q_dense: list[float],
        *,
        hits: int = 20,
        user_space: str | None = None,
        schema: str = "user",
    ) -> dict[str, Any]:
        """Build a hybrid search payload for ``global`` or ``user`` schema.

        Prefer :class:`~thot.tools.search.passage_retrieval.PassageRetrievalPipeline`
        for production search.

        Example:
            >>> client = VespaClient()
            >>> payload = client.build_hybrid_search_payload("hello", [0.0] * client.config.embedding_dim)
            >>> "yql" in payload and payload["hits"] == 20
            True
        """
        text_clause = build_field_contains_or_clause("chunk_text", query_text)
        yql_parts = [
            f'([{{"targetNumHits": {hits}}}]nearestNeighbor(dense_vector, q_dense))',
        ]
        if text_clause:
            yql_parts.append(text_clause)
        yql = f"select * from {schema} where " + " or ".join(yql_parts)
        payload: dict[str, Any] = {
            "yql": yql,
            "hits": hits,
            "timeout": f"{int(self._config.timeout_seconds)}s",
            "ranking.profile": "hybrid",
            "input.query(q_dense)": build_chunk_tensor(
                q_dense, embedding_dim=self._config.embedding_dim
            ),
        }
        if schema == "user":
            space = normalize_user_space(user_space or self._config.user_space)
            payload["streaming.groupname"] = space
        return payload

    async def hybrid_search(
        self,
        query_text: str,
        q_dense: list[float],
        *,
        hits: int = 20,
        user_space: str | None = None,
        schema: str = "user",
    ) -> dict[str, Any]:
        """Run hybrid dense + BM25 search over ``global`` or ``user``.

        Example:
            >>> import inspect
            >>> inspect.iscoroutinefunction(VespaClient.hybrid_search)
            True
        """
        payload = self.build_hybrid_search_payload(
            query_text,
            q_dense,
            hits=hits,
            user_space=user_space,
            schema=schema,
        )
        ThotLogger.info(
            f"Vespa hybrid search query={query_text!r} "
            f"schema={schema!r} "
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
            >>> asyncio.run(VespaClient().search({"yql": "select * from global where true"}))  # doctest: +SKIP
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
        >>> _parse_vespa_id("id:default:user:g=demo:abc123")
        ('default', 'user', 'demo', 'abc123')
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
