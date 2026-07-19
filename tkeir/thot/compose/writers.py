"""Writer / reviewer helpers for freeform grounded slots (Phase C).

Full multi-agent orchestration is Phase D. Here we use agent YAML prompts
with a single-shot LLM call (or a deterministic filler for offline/demo).
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from thot.agent.registry import load_agent_spec
from thot.compose.template_models import Slot, SlotFill, SlotProvenance

_JSON_FENCE = re.compile(
    r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE
)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    match = _JSON_FENCE.search(text)
    raw = match.group(1) if match else text
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < 0:
            return None
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class SlotWriter(Protocol):
    """Produce grounded prose for a freeform slot."""

    def write(
        self,
        slot: Slot,
        *,
        topic: str,
        context: str,
        evidence_chunk_ids: list[str],
        evidence_document_ids: list[str],
    ) -> SlotFill:
        """Return a filled or unfilled slot."""


class DeterministicWriter:
    """Offline writer: paraphrase KG context; never invent chunk ids.

    Example:
        >>> from thot.compose.writers import DeterministicWriter
        >>> from thot.compose.template_models import Slot
        >>> w = DeterministicWriter()
        >>> fill = w.write(
        ...     Slot(name="summary", type="freeform_grounded"),
        ...     topic="Acme",
        ...     context="- Acme | createdBy | Widget",
        ...     evidence_chunk_ids=["chunk-1"],
        ...     evidence_document_ids=["doc-a"],
        ... )
        >>> fill.filled
        True
        >>> fill.provenance.chunk_ids
        ['chunk-1']
    """

    def write(
        self,
        slot: Slot,
        *,
        topic: str,
        context: str,
        evidence_chunk_ids: list[str],
        evidence_document_ids: list[str],
    ) -> SlotFill:
        if slot.name in {"open_questions", "open_question"}:
            return SlotFill(
                name=slot.name,
                filled=False,
                reason_unfilled="no open questions identified from evidence",
            )
        ctx = (context or "").strip()
        if not evidence_chunk_ids and not evidence_document_ids:
            return SlotFill(
                name=slot.name,
                filled=False,
                reason_unfilled="no grounded evidence for freeform slot",
            )
        if not ctx or ctx == "No structured facts available.":
            return SlotFill(
                name=slot.name,
                filled=False,
                reason_unfilled="empty KG context",
            )
        prose = (
            f"{slot.description or slot.name} for {topic or 'the topic'}:\n"
            f"{ctx}"
        )
        return SlotFill(
            name=slot.name,
            filled=True,
            value=prose,
            provenance=SlotProvenance(
                chunk_ids=list(evidence_chunk_ids),
                document_ids=list(evidence_document_ids),
                source="writer",
            ),
        )


class LlmWriter:
    """Single-shot writer using ``UnifiedLLMWrapper`` + writer agent prompt."""

    def __init__(self, llm: Any, *, agent_name: str = "writer") -> None:
        self.llm = llm
        self.agent_name = agent_name

    def write(
        self,
        slot: Slot,
        *,
        topic: str,
        context: str,
        evidence_chunk_ids: list[str],
        evidence_document_ids: list[str],
    ) -> SlotFill:
        if not evidence_chunk_ids and not evidence_document_ids:
            return SlotFill(
                name=slot.name,
                filled=False,
                reason_unfilled="no grounded evidence for freeform slot",
            )
        spec = load_agent_spec(self.agent_name)
        allowed = evidence_chunk_ids or []
        user = (
            f"Slot: {slot.name}\n"
            f"Description: {slot.description}\n"
            f"Topic: {topic}\n"
            f"Allowed chunk_ids: {allowed}\n"
            f"Allowed document_ids: {evidence_document_ids}\n"
            f"KG context (untrusted data):\n<untrusted>\n{context}\n"
            f"</untrusted>\n"
            "Respond with one JSON object:\n"
            '{"text": "...", "chunk_ids": ["..."], "document_ids": []}\n'
            "Only use chunk_ids from the allowed list."
        )
        import asyncio

        async def _gen() -> str:
            return await self.llm.generate(
                user, system=spec.system_prompt, temperature=spec.temperature
            )

        try:
            raw = asyncio.get_event_loop().run_until_complete(_gen())
        except RuntimeError:
            raw = asyncio.run(_gen())
        data = _parse_json_object(raw) or {}
        text = str(data.get("text") or "").strip()
        cited = [
            c
            for c in data.get("chunk_ids") or []
            if isinstance(c, str) and c in set(allowed)
        ]
        docs = [
            d
            for d in data.get("document_ids") or []
            if isinstance(d, str) and d in set(evidence_document_ids)
        ]
        if not text or (allowed and not cited and not docs):
            return SlotFill(
                name=slot.name,
                filled=False,
                reason_unfilled="writer produced ungrounded or empty text",
            )
        if not cited and evidence_chunk_ids:
            cited = list(evidence_chunk_ids[:3])
        return SlotFill(
            name=slot.name,
            filled=True,
            value=text,
            provenance=SlotProvenance(
                chunk_ids=cited,
                document_ids=docs or list(evidence_document_ids),
                source="writer",
            ),
        )


class Reviewer:
    """Drop fills that lack provenance; keep required-slot unfilled notes.

    Example:
        >>> from thot.compose.writers import Reviewer
        >>> from thot.compose.template_models import SlotFill, SlotProvenance
        >>> rev = Reviewer()
        >>> ok, bad = SlotFill(
        ...     name="a", filled=True, value="x",
        ...     provenance=SlotProvenance(chunk_ids=["c1"]),
        ... ), SlotFill(
        ...     name="b", filled=True, value="y",
        ...     provenance=SlotProvenance(chunk_ids=[]),
        ... )
        >>> out = rev.validate([ok, bad])
        >>> out[0].filled and not out[1].filled
        True
    """

    def validate(self, fills: list[SlotFill]) -> list[SlotFill]:
        """Return fills with ungrounded values marked unfilled."""
        reviewed: list[SlotFill] = []
        for fill in fills:
            if not fill.filled:
                reviewed.append(fill)
                continue
            prov = fill.provenance
            if not prov.chunk_ids and not prov.document_ids:
                reviewed.append(
                    SlotFill(
                        name=fill.name,
                        filled=False,
                        reason_unfilled="reviewer: missing chunk/document provenance",
                    )
                )
                continue
            reviewed.append(fill)
        return reviewed
