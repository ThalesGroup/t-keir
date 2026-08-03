"""Title: Apply okf_curator enrichments back onto OKF concept files.

Example:
    >>> from thot.okf.applicator import OkfEnrichmentApplicator
    >>> OkfEnrichmentApplicator  # doctest: +ELLIPSIS
    <class 'thot.okf.applicator.OkfEnrichmentApplicator'>

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from thot.agent.models import GroundedFindings
from thot.okf.models import (
    OkfEnrichment,
    OkfEnrichmentFinding,
    OkfEnrichmentPayload,
)

LOGGER = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


def parse_concept_file(text: str) -> tuple[dict[str, Any], str]:
    """Split YAML frontmatter and Markdown body.

    Args:
        text: Full concept file contents.

    Returns:
        Tuple of frontmatter dict and markdown body.

    Example:
        >>> fm, body = parse_concept_file('---\\ntype: Document\\n---\\n\\n# Hi\\n')
        >>> fm['type']
        'Document'
        >>> '# Hi' in body
        True
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    raw = match.group(1)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    body = text[match.end() :]
    return data, body


def render_concept_file(frontmatter: dict[str, Any], body: str) -> str:
    """Serialize frontmatter + body to an OKF concept file.

    Args:
        frontmatter: YAML frontmatter fields.
        body: Markdown body after the closing ``---``.

    Returns:
        Full concept file text with YAML frontmatter block.

    Example:
        >>> from thot.okf.applicator import render_concept_file
        >>> out = render_concept_file({"type": "Document"}, "# Hi\\n")
        >>> '---' in out and '# Hi' in out
        True
    """
    dumped = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    ).strip()
    return f"---\n{dumped}\n---\n\n{body.lstrip()}\n"


def enrichments_from_grounded(
    result: GroundedFindings | None,
    *,
    raw_notes: str | None = None,
) -> OkfEnrichment:
    """Recover ``okf_enrichment_v1`` from agent notes + grounded findings.

    AgentLoop keeps ``claim`` + ``chunk_ids`` only; the curator embeds the full
    enrichment payload as JSON in ``notes`` (or ``notes.enrichments``).

    Args:
        result: Researcher grounded findings, when available.
        raw_notes: Optional notes override (JSON or plain text).

    Returns:
        Parsed or synthesized ``OkfEnrichment`` payload.

    Example:
        >>> import json
        >>> from thot.agent.models import GroundedFinding, GroundedFindings
        >>> from thot.okf.applicator import enrichments_from_grounded
        >>> notes = json.dumps(
        ...     {"schema": "okf_enrichment_v1", "findings": [], "unfilled": []}
        ... )
        >>> e = enrichments_from_grounded(None, raw_notes=notes)
        >>> e.schema_
        'okf_enrichment_v1'
        >>> gf = GroundedFindings(
        ...     findings=[
        ...         GroundedFinding(
        ...             claim="x", document_ids=["okf:foo"], chunk_ids=["c1"]
        ...         )
        ...     ]
        ... )
        >>> enrichments_from_grounded(gf).findings[0].concept_id
        'foo'
    """
    notes = (
        raw_notes
        if raw_notes is not None
        else (result.notes if result else "")
    )
    findings: list[OkfEnrichmentFinding] = []
    unfilled: list[str] = list(result.unfilled) if result else []
    parsed: dict[str, Any] | None = None
    if notes and notes.strip().startswith("{"):
        try:
            loaded = json.loads(notes)
            if isinstance(loaded, dict):
                parsed = loaded
        except json.JSONDecodeError:
            parsed = None
    if parsed and (
        parsed.get("schema") == "okf_enrichment_v1" or "findings" in parsed
    ):
        try:
            return OkfEnrichment.model_validate(parsed)
        except Exception:  # noqa: BLE001
            LOGGER.warning("failed to validate okf enrichment notes JSON")
    # Fallback: map grounded claims onto concept_ids listed in document_ids
    if result:
        for finding in result.findings:
            concept_id = ""
            for doc_id in finding.document_ids:
                if str(doc_id).startswith("okf:"):
                    concept_id = str(doc_id)[4:]
                    break
            if not concept_id and finding.document_ids:
                concept_id = str(finding.document_ids[0])
            if not concept_id:
                continue
            findings.append(
                OkfEnrichmentFinding(
                    concept_id=concept_id,
                    claim=finding.claim,
                    chunk_ids=list(finding.chunk_ids),
                    document_ids=list(finding.document_ids),
                    confidence=finding.confidence,
                    enrichments=OkfEnrichmentPayload(
                        description=finding.claim,
                        tags=[],
                        body_sections={"Summary": finding.claim},
                    ),
                )
            )
    return OkfEnrichment(
        findings=findings, unfilled=unfilled, notes=notes or ""
    )


class OkfEnrichmentApplicator:
    """Mutate concept Markdown files with curator enrichments.

    Never overwrites ``tkeir_*`` frontmatter keys.

    Example:
        >>> import tempfile
        >>> from pathlib import Path
        >>> from thot.okf.applicator import OkfEnrichmentApplicator
        >>> applicator = OkfEnrichmentApplicator(tempfile.mkdtemp())
        >>> applicator.root.is_dir()
        True
    """

    def __init__(self, bundle_root: Path | str) -> None:
        """Bind the applicator to one OKF bundle directory.

        Args:
            bundle_root: Root path of the bundle on disk.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.okf.applicator import OkfEnrichmentApplicator
            >>> td = tempfile.mkdtemp()
            >>> OkfEnrichmentApplicator(td).root == Path(td)
            True
        """
        self.root = Path(bundle_root)

    def _concept_path(self, concept_id: str) -> Path:
        """Resolve a concept id to an on-disk ``.md`` path under the bundle.

        Args:
            concept_id: Relative concept path (with or without ``.md``).

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.okf.applicator import OkfEnrichmentApplicator
            >>> td = tempfile.mkdtemp()
            >>> applicator = OkfEnrichmentApplicator(td)
            >>> _ = (Path(td) / "foo.md").write_text("# foo\\n")
            >>> applicator._concept_path("foo") == Path(td) / "foo.md"
            True
        """
        rel = concept_id[:-3] if concept_id.endswith(".md") else concept_id
        candidate = self.root / f"{rel}.md"
        if candidate.is_file():
            return candidate
        # Also try under concepts/
        alt = self.root / "concepts" / f"{Path(rel).name}.md"
        if alt.is_file():
            return alt
        return candidate

    def apply_one(self, finding: OkfEnrichmentFinding) -> bool:
        """Apply one finding; return True when a file was updated.

        Args:
            finding: One curator enrichment finding.

        Returns:
            ``True`` when the concept file existed and was rewritten.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.okf.applicator import OkfEnrichmentApplicator
            >>> from thot.okf.models import OkfEnrichmentFinding, OkfEnrichmentPayload
            >>> td = tempfile.mkdtemp()
            >>> applicator = OkfEnrichmentApplicator(td)
            >>> _ = (Path(td) / "foo.md").write_text(
            ...     "---\\ntype: Document\\n---\\n\\n# Foo\\n"
            ... )
            >>> finding = OkfEnrichmentFinding(
            ...     concept_id="foo",
            ...     claim="summary",
            ...     chunk_ids=["c1"],
            ...     enrichments=OkfEnrichmentPayload(
            ...         description="desc", tags=["t1"]
            ...     ),
            ... )
            >>> applicator.apply_one(finding)
            True
        """
        path = self._concept_path(finding.concept_id)
        if not path.is_file():
            LOGGER.info(
                "okf applicator: missing concept %s", finding.concept_id
            )
            return False
        text = path.read_text(encoding="utf-8")
        frontmatter, body = parse_concept_file(text)
        # Preserve all tkeir_* keys
        protected = {
            k: v for k, v in frontmatter.items() if str(k).startswith("tkeir_")
        }
        enrichments = finding.enrichments
        if enrichments.description:
            frontmatter["description"] = enrichments.description
        elif finding.claim:
            frontmatter["description"] = finding.claim
        if enrichments.tags:
            existing = list(frontmatter.get("tags") or [])
            merged: list[str] = []
            seen: set[str] = set()
            for tag in [*existing, *enrichments.tags]:
                low = str(tag).lower()
                if low in seen:
                    continue
                seen.add(low)
                merged.append(str(tag))
            frontmatter["tags"] = merged
        frontmatter.update(protected)
        # Append body sections (do not rewrite Entities/Relations/KG/Citations)
        sections = dict(enrichments.body_sections or {})
        if sections:
            parts = [body.rstrip(), "", "## Curator enrichments", ""]
            for heading, content in sections.items():
                parts.extend([f"### {heading}", "", str(content).rstrip(), ""])
            body = "\n".join(parts)
        path.write_text(
            render_concept_file(frontmatter, body), encoding="utf-8"
        )
        return True

    def apply(self, enrichment: OkfEnrichment) -> dict[str, Any]:
        """Apply all findings; return summary counts.

        Args:
            enrichment: Full curator enrichment payload.

        Returns:
            Dict with ``applied``, ``missing``, and ``unfilled`` keys.

        Example:
            >>> import tempfile
            >>> from pathlib import Path
            >>> from thot.okf.applicator import OkfEnrichmentApplicator
            >>> from thot.okf.models import (
            ...     OkfEnrichment,
            ...     OkfEnrichmentFinding,
            ...     OkfEnrichmentPayload,
            ... )
            >>> td = tempfile.mkdtemp()
            >>> applicator = OkfEnrichmentApplicator(td)
            >>> _ = (Path(td) / "bar.md").write_text(
            ...     "---\\ntype: Document\\n---\\n\\n# Bar\\n"
            ... )
            >>> finding = OkfEnrichmentFinding(
            ...     concept_id="bar",
            ...     claim="claim",
            ...     chunk_ids=["c1"],
            ...     enrichments=OkfEnrichmentPayload(description="d"),
            ... )
            >>> result = applicator.apply(OkfEnrichment(findings=[finding]))
            >>> result["applied"]
            1
        """
        applied = 0
        missing: list[str] = []
        for finding in enrichment.findings:
            if not finding.chunk_ids and not finding.document_ids:
                missing.append(finding.concept_id)
                continue
            if self.apply_one(finding):
                applied += 1
            else:
                missing.append(finding.concept_id)
        return {
            "applied": applied,
            "missing": missing,
            "unfilled": list(enrichment.unfilled),
        }
