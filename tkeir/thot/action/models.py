"""ActionRecord v1 model and ULID helper.

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

SCHEMA_ID = "tkeir.action.v1"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_action_id() -> str:
    """Generate a Crockford-base32 ULID (26 characters).

    Example:
        >>> aid = new_action_id()
        >>> len(aid) == 26 and all(c in _CROCKFORD for c in aid)
        True
    """
    ms = int(time.time() * 1000)
    if ms < 0 or ms >= (1 << 48):
        raise ValueError("timestamp out of ULID range")
    entropy = int.from_bytes(secrets.token_bytes(10), "big")
    value = (ms << 80) | entropy
    chars: list[str] = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def utc_now_rfc3339() -> str:
    """Return current UTC time as RFC 3339 with ``Z`` suffix.

    Example:
        >>> utc_now_rfc3339().endswith("Z")
        True
    """
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def sha256_hex(payload: str | bytes) -> str:
    """Return the hex SHA-256 digest of ``payload``.

    Example:
        >>> sha256_hex("abc") == hashlib.sha256(b"abc").hexdigest()
        True
    """
    data = payload if isinstance(payload, bytes) else payload.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def canonical_json(data: dict[str, Any]) -> str:
    """Serialize ``data`` with sorted keys for stable hashing.

    Example:
        >>> canonical_json({"b": 1, "a": 2})
        '{"a":2,"b":1}'
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class ActorInfo(BaseModel):
    type: Literal["human", "service", "agent"] = "service"
    id: str = "anonymous"
    spiffe_id: str | None = None
    session_id: str | None = None


class DelegationHop(BaseModel):
    from_sub: str
    to_client: str
    jti: str
    expires_at: str


class IntentInfo(BaseModel):
    declared: str = "search"
    scope_source: Literal["oauth-scope", "manual"] = "manual"
    mandate_ref: str | None = None


class ContextVersions(BaseModel):
    app: str = ""
    embedder: str = ""
    llm: str = ""
    reranker: str = ""
    policy_bundle_sha: str = ""
    vespa_schema: str = ""


class ActionContext(BaseModel):
    env: str = "dev"
    service: str = "tkeir-api"
    versions: ContextVersions = Field(default_factory=ContextVersions)
    request_hash: str = ""


class DecisionInfo(BaseModel):
    policy_result: Literal["allow", "deny", "escalate"] = "allow"
    rules_fired: list[str] = Field(default_factory=list)
    model: dict[str, str] = Field(default_factory=dict)


class ExecutionInfo(BaseModel):
    started_at: str = ""
    ended_at: str = ""
    status: Literal["success", "failure", "blocked", "rolled_back"] = "success"


class ResultInfo(BaseModel):
    output_hash: str = ""
    doc_ids: list[str] = Field(default_factory=list)
    chunk_ids: list[str] = Field(default_factory=list)
    scores_digest: str = ""
    error: str | None = None


class BudgetConsumed(BaseModel):
    units: str = "docs"
    amount: float = 0


class ImpactInfo(BaseModel):
    class_: Literal["read", "write", "destructive", "financial"] = Field(
        default="read",
        alias="class",
    )
    budget_consumed: BudgetConsumed = Field(default_factory=BudgetConsumed)

    model_config = {"populate_by_name": True}


class EvidenceInfo(BaseModel):
    trace_id: str = ""
    log_stream: str = ""
    prev_hash: str = ""
    record_hash: str = ""
    signature: str | None = None
    worm_segment: str | None = None


class PrivacyInfo(BaseModel):
    subject_refs: list[str] = Field(default_factory=list)
    pii: bool = False


class ActionRecord(BaseModel):
    """ActionRecord v1 — one attributable action in the system."""

    schema_: str = Field(default=SCHEMA_ID, alias="schema")
    action_id: str = Field(default_factory=new_action_id)
    correlation_id: str = ""
    parent_action_id: str | None = None
    occurred_at: str = Field(default_factory=utc_now_rfc3339)
    actor: ActorInfo = Field(default_factory=ActorInfo)
    delegation_chain: list[DelegationHop] = Field(default_factory=list)
    intent: IntentInfo = Field(default_factory=IntentInfo)
    context: ActionContext = Field(default_factory=ActionContext)
    decision: DecisionInfo = Field(default_factory=DecisionInfo)
    execution: ExecutionInfo = Field(default_factory=ExecutionInfo)
    result: ResultInfo = Field(default_factory=ResultInfo)
    impact: ImpactInfo = Field(default_factory=ImpactInfo)
    evidence: EvidenceInfo = Field(default_factory=EvidenceInfo)
    privacy: PrivacyInfo = Field(default_factory=PrivacyInfo)
    ext: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}

    def to_canonical_dict(self) -> dict[str, Any]:
        """Serialize excluding ``record_hash`` for chain hashing."""
        data = self.model_dump(by_alias=True, mode="json")
        evidence = dict(data.get("evidence") or {})
        evidence.pop("record_hash", None)
        data["evidence"] = evidence
        return data

    def compute_record_hash(self, prev_hash: str = "") -> str:
        """Hash ``canonical_json(record \\ record_hash) || prev_hash``.

        Example:
            >>> rec = ActionRecord(correlation_id="a" * 32)
            >>> len(rec.compute_record_hash("")) == 64
            True
        """
        data = self.to_canonical_dict()
        data.setdefault("evidence", {})["prev_hash"] = prev_hash
        return sha256_hex(canonical_json(data) + prev_hash)

    def seal(self, prev_hash: str = "") -> ActionRecord:
        """Return a copy with ``prev_hash`` / ``record_hash`` filled.

        Args:
            prev_hash: Previous chain head (empty string for the first record).

        Returns:
            A deep copy with evidence hashes set.

        Example:
            >>> rec = ActionRecord(correlation_id="b" * 32)
            >>> sealed = rec.seal("")
            >>> len(sealed.evidence.record_hash) == 64
            True
            >>> sealed.evidence.prev_hash
            ''
        """
        sealed = self.model_copy(deep=True)
        sealed.evidence.prev_hash = prev_hash
        sealed.evidence.trace_id = sealed.correlation_id
        sealed.evidence.record_hash = sealed.compute_record_hash(prev_hash)
        return sealed
