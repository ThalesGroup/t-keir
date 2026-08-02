"""Title: Ontology-driven template models (Phase C).

Templates declare typed slots filled from the fused KG and/or a Writer agent.
Every filled slot must carry provenance (``chunk_ids`` / ``document_ids``);
ungrounded slots are reported as unfilled — never hallucinated.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SlotType = Literal[
    "entity",
    "svo_pattern",
    "keyword",
    "sparql",
    "freeform_grounded",
]


class SlotConstraint(BaseModel):
    """Cardinality / requirement constraints for a slot."""

    min_items: int = 0
    max_items: int = 20
    required: bool = False


class Slot(BaseModel):
    """One fillable field in a template.

    Types:
        entity: match RDF entities by label (``label`` / ``query``).
        svo_pattern: subject|predicate|object triples.
        keyword: ``tkeir:Keyword`` labels.
        sparql: custom SELECT; bind columns into the slot value.
        freeform_grounded: prose via Writer, must cite chunk/doc ids.
    """

    name: str
    type: SlotType
    description: str = ""
    query: str | None = None
    label: str | None = None
    constraints: SlotConstraint = Field(default_factory=SlotConstraint)


class TemplateSpec(BaseModel):
    """Versioned template loaded from ``tkeir/configs/templates/*.yaml``."""

    name: str
    version: int = 1
    title: str = ""
    description: str = ""
    slots: list[Slot] = Field(default_factory=list)
    markdown_template: str = ""


class SlotProvenance(BaseModel):
    """Grounding for a filled slot."""

    chunk_ids: list[str] = Field(default_factory=list)
    document_ids: list[str] = Field(default_factory=list)
    source: Literal[
        "kg", "sparql", "writer", "retrieval", "param", "findings"
    ] = "kg"


class SlotFill(BaseModel):
    """Result of attempting to fill one slot."""

    name: str
    filled: bool = False
    value: Any = None
    provenance: SlotProvenance = Field(default_factory=SlotProvenance)
    reason_unfilled: str | None = None


class ComposeResult(BaseModel):
    """Composer output: markdown + structured JSON + citations."""

    schema_: str = Field(default="tkeir.compose.result.v1", alias="schema")
    template: str
    template_version: int = 1
    user_space: str
    topic: str = ""
    markdown: str = ""
    structured_json: dict[str, Any] = Field(default_factory=dict)
    citations_map: dict[str, list[str]] = Field(default_factory=dict)
    unfilled: list[str] = Field(default_factory=list)
    fills: list[SlotFill] = Field(default_factory=list)

    model_config = {"populate_by_name": True}
