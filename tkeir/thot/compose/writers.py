"""Title: Writer / reviewer helpers for freeform grounded slots (Phase C).

Full multi-agent orchestration is Phase D. Here we use agent YAML prompts
with a single-shot LLM call (or a deterministic filler for offline/demo).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
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
_SLOT_TAG = re.compile(r"^\[([A-Za-z0-9_]+)\]\s*", re.IGNORECASE)


def _parse_json_object(text: str) -> dict[str, Any] | None:
    """Extract the first JSON object from LLM output (fenced or raw).

    Example:
        >>> from thot.compose.writers import _parse_json_object
        >>> _parse_json_object('```json\\n{"text": "hi"}\\n```')["text"]
        'hi'
        >>> _parse_json_object("no json") is None
        True
    """
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
        """Return a filled or unfilled slot.

        Example:
            >>> import inspect
            >>> from thot.compose.writers import SlotWriter
            >>> inspect.isfunction(SlotWriter.write)
            True
        """


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
        """Write grounded prose from KG context or mark slot unfilled.

        Example:
            >>> from thot.compose.writers import DeterministicWriter
            >>> from thot.compose.template_models import Slot
            >>> fill = DeterministicWriter().write(
            ...     Slot(name="summary", type="freeform_grounded"),
            ...     topic="Acme",
            ...     context="- Acme | createdBy | Widget",
            ...     evidence_chunk_ids=["chunk-1"],
            ...     evidence_document_ids=["doc-a"],
            ... )
            >>> fill.filled
            True
        """
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


class FindingsGroundedWriter:
    """Prefer researcher grounded claims for freeform slots; never invent ids.

    When claims are tagged ``[slot_name] …`` (persona OTAN writers), only the
    matching tags fill that compose slot. Untagged findings remain a legacy
    fallback (same prose for every freeform slot).
    """

    def __init__(
        self,
        *,
        findings_context: str,
        chunk_ids: list[str],
        document_ids: list[str],
        fallback: DeterministicWriter | None = None,
    ) -> None:
        """Store findings context and evidence ids for slot-tagged prose.

        Example:
            >>> from thot.compose.writers import FindingsGroundedWriter
            >>> w = FindingsGroundedWriter(
            ...     findings_context="- [summary] Acme launched Widget",
            ...     chunk_ids=["c1"],
            ...     document_ids=["d1"],
            ... )
            >>> w.chunk_ids
            ['c1']
        """
        self.findings_context = (findings_context or "").strip()
        self.chunk_ids = list(chunk_ids or [])
        self.document_ids = list(document_ids or [])
        self.fallback = fallback or DeterministicWriter()

    @staticmethod
    def prose_for_slot(findings_context: str, slot_name: str) -> str | None:
        """Return slot-tagged bullets, empty string if tags exist but none match,
        or ``None`` when findings are untagged (legacy dump-all mode).

        Example:
            >>> from thot.compose.writers import FindingsGroundedWriter
            >>> FindingsGroundedWriter.prose_for_slot(
            ...     "- [summary] Acme launched Widget\\n- [risks] Supply delay",
            ...     "summary",
            ... )
            '- Acme launched Widget'
        """
        text = (findings_context or "").strip()
        if not text:
            return None
        slot_key = (slot_name or "").strip().lower()
        matched: list[str] = []
        saw_tag = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            body = line[2:].strip() if line.startswith("- ") else line
            tag = _SLOT_TAG.match(body)
            if not tag:
                continue
            saw_tag = True
            if tag.group(1).lower() != slot_key:
                continue
            rest = body[tag.end() :].strip()
            matched.append(f"- {rest}" if rest else f"- {body}")
        if matched:
            return "\n".join(matched)
        if saw_tag:
            return ""
        return None

    def write(
        self,
        slot: Slot,
        *,
        topic: str,
        context: str,
        evidence_chunk_ids: list[str],
        evidence_document_ids: list[str],
    ) -> SlotFill:
        """Prefer slot-tagged findings; fall back to deterministic writer.

        Example:
            >>> from thot.compose.writers import FindingsGroundedWriter
            >>> from thot.compose.template_models import Slot
            >>> w = FindingsGroundedWriter(
            ...     findings_context="- [summary] Acme launched Widget",
            ...     chunk_ids=["c1"],
            ...     document_ids=["d1"],
            ... )
            >>> fill = w.write(
            ...     Slot(name="summary", type="freeform_grounded"),
            ...     topic="Acme", context="", evidence_chunk_ids=["c1"],
            ...     evidence_document_ids=["d1"],
            ... )
            >>> fill.filled and "Acme" in str(fill.value)
            True
        """
        if slot.name in {"open_questions", "open_question"}:
            return self.fallback.write(
                slot,
                topic=topic,
                context=context,
                evidence_chunk_ids=evidence_chunk_ids,
                evidence_document_ids=evidence_document_ids,
            )
        chunks = list(self.chunk_ids or evidence_chunk_ids)
        docs = list(self.document_ids or evidence_document_ids)
        if self.findings_context and chunks:
            slotted = self.prose_for_slot(self.findings_context, slot.name)
            if slotted is not None:
                if not slotted.strip():
                    return SlotFill(
                        name=slot.name,
                        filled=False,
                        reason_unfilled=(
                            f"no [{slot.name}] tagged findings for this slot"
                        ),
                    )
                header = slot.description or slot.name
                prose = f"{header}\n\n{slotted}"
            else:
                header = slot.description or slot.name
                prose = (
                    f"{header}\n\n"
                    f"Grounded findings for {topic or 'the topic'}:\n"
                    f"{self.findings_context}"
                )
            return SlotFill(
                name=slot.name,
                filled=True,
                value=prose,
                provenance=SlotProvenance(
                    chunk_ids=chunks,
                    document_ids=docs,
                    source="findings",
                ),
            )
        return self.fallback.write(
            slot,
            topic=topic,
            context=context,
            evidence_chunk_ids=chunks,
            evidence_document_ids=docs,
        )


class LlmWriter:
    """Single-shot writer using ``UnifiedLLMWrapper`` + writer agent prompt."""

    def __init__(self, llm: Any, *, agent_name: str = "writer") -> None:
        """Bind an LLM client and writer agent spec name.

        Example:
            >>> from thot.compose.writers import LlmWriter
            >>> LlmWriter(None).agent_name
            'writer'
        """
        self.llm = llm
        self.agent_name = agent_name

    def _build_user_prompt(
        self,
        slot: Slot,
        *,
        topic: str,
        context: str,
        evidence_chunk_ids: list[str],
        evidence_document_ids: list[str],
    ) -> str:
        """Build the user prompt for a single-shot writer call.

        Example:
            >>> from thot.compose.writers import LlmWriter
            >>> from thot.compose.template_models import Slot
            >>> prompt = LlmWriter(None)._build_user_prompt(
            ...     Slot(name="summary", type="freeform_grounded", description="Summary"),
            ...     topic="Acme", context="facts", evidence_chunk_ids=["c1"],
            ...     evidence_document_ids=["d1"],
            ... )
            >>> "Allowed chunk_ids: ['c1']" in prompt
            True
        """
        allowed = evidence_chunk_ids or []
        return (
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

    def _run_llm(self, user: str, system: str, temperature: float) -> str:
        """Run the async LLM generate call from sync writer code.

        Example:
            >>> import asyncio
            >>> from thot.compose.writers import LlmWriter
            >>> class _FakeLlm:
            ...     async def generate(self, user, *, system, temperature):
            ...         return '{"text": "ok", "chunk_ids": ["c1"]}'
            >>> out = LlmWriter(_FakeLlm())._run_llm("u", "s", 0.0)
            >>> '"text"' in out
            True
        """
        import asyncio

        async def _gen() -> str:
            return await self.llm.generate(
                user, system=system, temperature=temperature
            )

        try:
            return asyncio.get_event_loop().run_until_complete(_gen())
        except RuntimeError:
            return asyncio.run(_gen())

    def _grounded_citations(
        self,
        data: dict[str, Any],
        *,
        allowed: list[str],
        evidence_document_ids: list[str],
    ) -> tuple[str, list[str], list[str]]:
        """Filter LLM citations to allowed chunk and document ids.

        Example:
            >>> from thot.compose.writers import LlmWriter
            >>> LlmWriter(None)._grounded_citations(
            ...     {"text": "hi", "chunk_ids": ["c1", "evil"], "document_ids": ["d1"]},
            ...     allowed=["c1"],
            ...     evidence_document_ids=["d1"],
            ... )
            ('hi', ['c1'], ['d1'])
        """
        text = str(data.get("text") or "").strip()
        allowed_set = set(allowed)
        cited = [
            c
            for c in data.get("chunk_ids") or []
            if isinstance(c, str) and c in allowed_set
        ]
        doc_set = set(evidence_document_ids)
        docs = [
            d
            for d in data.get("document_ids") or []
            if isinstance(d, str) and d in doc_set
        ]
        return text, cited, docs

    def _slot_fill_from_response(
        self,
        slot: Slot,
        *,
        text: str,
        cited: list[str],
        docs: list[str],
        allowed: list[str],
        evidence_chunk_ids: list[str],
        evidence_document_ids: list[str],
    ) -> SlotFill:
        """Convert validated LLM output into a grounded ``SlotFill``.

        Example:
            >>> from thot.compose.writers import LlmWriter
            >>> from thot.compose.template_models import Slot
            >>> fill = LlmWriter(None)._slot_fill_from_response(
            ...     Slot(name="summary", type="freeform_grounded"),
            ...     text="Grounded text",
            ...     cited=["c1"],
            ...     docs=["d1"],
            ...     allowed=["c1"],
            ...     evidence_chunk_ids=["c1"],
            ...     evidence_document_ids=["d1"],
            ... )
            >>> fill.filled and fill.provenance.chunk_ids == ["c1"]
            True
        """
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

    def write(
        self,
        slot: Slot,
        *,
        topic: str,
        context: str,
        evidence_chunk_ids: list[str],
        evidence_document_ids: list[str],
    ) -> SlotFill:
        """Call the writer agent LLM and return a grounded slot fill.

        Example:
            >>> from thot.compose.writers import LlmWriter
            >>> from thot.compose.template_models import Slot
            >>> class _FakeLlm:
            ...     async def generate(self, user, *, system, temperature):
            ...         return '{"text": "Summary text", "chunk_ids": ["c1"]}'
            >>> fill = LlmWriter(_FakeLlm()).write(
            ...     Slot(name="summary", type="freeform_grounded"),
            ...     topic="Acme", context="facts",
            ...     evidence_chunk_ids=["c1"], evidence_document_ids=["d1"],
            ... )
            >>> fill.filled
            True
        """
        if not evidence_chunk_ids and not evidence_document_ids:
            return SlotFill(
                name=slot.name,
                filled=False,
                reason_unfilled="no grounded evidence for freeform slot",
            )
        spec = load_agent_spec(self.agent_name)
        allowed = evidence_chunk_ids or []
        user = self._build_user_prompt(
            slot,
            topic=topic,
            context=context,
            evidence_chunk_ids=evidence_chunk_ids,
            evidence_document_ids=evidence_document_ids,
        )
        raw = self._run_llm(user, spec.system_prompt, spec.temperature)
        data = _parse_json_object(raw) or {}
        text, cited, docs = self._grounded_citations(
            data,
            allowed=allowed,
            evidence_document_ids=evidence_document_ids,
        )
        return self._slot_fill_from_response(
            slot,
            text=text,
            cited=cited,
            docs=docs,
            allowed=allowed,
            evidence_chunk_ids=evidence_chunk_ids,
            evidence_document_ids=evidence_document_ids,
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
        """Return fills with ungrounded values marked unfilled.

        Example:
            >>> from thot.compose.writers import Reviewer
            >>> from thot.compose.template_models import SlotFill, SlotProvenance
            >>> ok = SlotFill(
            ...     name="a", filled=True, value="x",
            ...     provenance=SlotProvenance(chunk_ids=["c1"]),
            ... )
            >>> bad = SlotFill(
            ...     name="b", filled=True, value="y",
            ...     provenance=SlotProvenance(chunk_ids=[]),
            ... )
            >>> out = Reviewer().validate([ok, bad])
            >>> out[0].filled and not out[1].filled
            True
        """
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
