#!/usr/bin/env python3
"""Title: OSINT ontology refactor smoke demo.

Run the canonical ontology layer on
``datasets/osint/c2_middle_east_multi_source_1000_v5_200w_en.json``
without Vespa. Use ``--live`` only when ingest (:8091) and RAG (:8090)
are already up.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
TKEIR = REPO / "tkeir"
if str(TKEIR) not in sys.path:
    sys.path.insert(0, str(TKEIR))

DEFAULT_CORPUS = (
    REPO
    / "datasets"
    / "osint"
    / "c2_middle_east_multi_source_1000_v5_200w_en.json"
)
DEFAULT_ONTOLOGY = REPO / "datasets" / "osint" / "business_ontology.yaml"


def _load_records(path: Path, *, limit: int) -> list[dict[str, Any]]:
    """Load the first ``limit`` records from a JSON corpus.

    Example:
        >>> from pathlib import Path
        >>> isinstance(DEFAULT_CORPUS, Path)
        True
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    return [row for row in records if isinstance(row, dict)][: max(1, limit)]


def _print_section(title: str) -> None:
    """Print a section header.

    Example:
        >>> True
        True
    """
    print()
    print(f"=== {title} ===")


def run_offline(records: list[dict[str, Any]], ontology_path: Path) -> int:
    """Print JSON concepts, expert mapping, relations, and expansion.

    Example:
        >>> callable(run_offline)
        True
    """
    import yaml

    from thot.ontology.expansion import ExpansionSpec
    from thot.ontology.json_concepts import extract_json_concepts
    from thot.ontology.service import OntologyService
    from thot.tools.ingest.json_records import extract_record_concepts

    raw = yaml.safe_load(ontology_path.read_text(encoding="utf-8")) or {}
    svc = OntologyService.from_business_payload(raw)
    expert_n = len(svc.expert.concepts)
    print(f"Expert ontology: {ontology_path.name} ({expert_n} concepts)")
    print(f"Corpus records in this run: {len(records)}")

    for record in records:
        doc_id = str(record.get("doc_id") or "?")
        _print_section(f"Record {doc_id}")
        print(f"title:  {record.get('title')}")
        print(f"domain: {record.get('domain')}  pir_ref: {record.get('pir_ref')}")
        loc = record.get("location") or {}
        if isinstance(loc, dict):
            print(
                f"location.country: {loc.get('country')}  "
                f"name: {loc.get('name')}"
            )

        json_ext = extract_json_concepts(record, max_concepts=64)
        print()
        print("JSON structural concepts (canonical IDs):")
        interesting = [
            cid
            for cid in json_ext.chunk_ids()
            if "location.country" in cid
            or "domain" in cid
            or cid.startswith("DOMAIN:")
            or "pir" in cid.lower()
        ]
        for cid in interesting[:12]:
            kind = "attr " if ":attribute:" in cid else "value" if ":value:" in cid else "legcy"
            print(f"  {kind} {cid}")
        print("  (plus other JSON fields; showing location/domain/PIR only)")
        if json_ext.ontology.relations:
            rel = json_ext.ontology.relations[0]
            print(
                f"  rel   {rel.subject_id} -[{rel.predicate_id}]-> {rel.object_id}"
            )
            print(f"  provenance: {rel.provenance.kind.value}")
        print("Legacy PATH:value tokens (backward compatible):")
        for token in json_ext.legacy_ids[:6]:
            print(f"  {token}")

        all_json_ids = json_ext.chunk_ids()
        checks = {
            "json:attribute:location.country": "JSON path concept",
            "json:value:location.country=egypt": "JSON value concept",
            "LOCATION_COUNTRY:Egypt": "legacy alias (old indexes)",
            "json:attribute:domain": "domain attribute",
            "DOMAIN:OSINT_SOCMINT": "legacy domain token",
        }
        print()
        print("Spec checks (must be true for the refactor):")
        for cid, label in checks.items():
            hit = cid in all_json_ids or cid in json_ext.legacy_ids
            # value IDs are casefolded
            if not hit:
                hit = any(cid.casefold() == x.casefold() for x in all_json_ids)
            print(f"  [{'ok' if hit else 'MISSING'}] {label}: {cid}")

        chunk_ids = extract_record_concepts(record, max_concepts=24)
        mapped, n_mapped = svc.map_concepts(
            [
                str(record.get("domain") or ""),
                str(record.get("pir_ref") or ""),
                str((loc or {}).get("country") or "") if isinstance(loc, dict) else "",
            ]
        )
        print()
        print(f"Expert mapping (mapped={n_mapped}): {mapped}")
        print(
            "Chunk Vespa IDs (canonical + legacy), first 10:",
            chunk_ids[:10],
        )

        enrichment = svc.enrich_chunk(
            {
                "chunk_id": f"{doc_id}#0",
                "text_raw": str(record.get("title") or "")
                + " "
                + str(record.get("text") or "")[:400],
            },
            {
                "source_doc_id": f"osint/{doc_id}",
                "record": record,
                "record_concept_ids": chunk_ids,
            },
            ontology_payload=raw,
        )
        print()
        print(
            "Enrichment: "
            f"concepts={len(enrichment.concept_ids)} "
            f"relations={len(enrichment.relations)} "
            f"new={enrichment.metrics.get('new', 0)} "
            f"json={enrichment.metrics.get('json_concepts', 0)} "
            f"mapped={enrichment.metrics.get('mapped', 0)}"
        )
        print("  concept_ids[:12]:", enrichment.concept_ids[:12])
        for rel in enrichment.relations[:4]:
            print(
                f"  relation {rel.subject_id} "
                f"-[{rel.predicate_id}]-> {rel.object_id} "
                f"({rel.provenance.kind.value})"
            )

    _print_section("Ontology expansion (OSINT_SOCMINT children)")
    expanded = svc.expand(
        ["OSINT_SOCMINT"],
        ExpansionSpec(include_children=True, max_depth=1, max_ids=16),
    )
    print("seeds:    ", expanded.seed_ids)
    print("expanded: ", expanded.expanded_ids)

    _print_section("Live API examples (optional)")
    print(
        "1) Index 3 records (ingest API must be up):\n"
        "   curl -sS -X POST http://localhost:8091/ingest/json-records \\\n"
        "     -H 'content-type: application/json' \\\n"
        "     -d '{\"dataset_path\":"
        "\"osint/c2_middle_east_multi_source_1000_v5_200w_en.json\","
        "\"index_target\":\"global\",\"limit\":3,"
        "\"business_ontology_dataset\":\"osint\"}'\n"
        "2) Text-only search (must still work):\n"
        "   curl -sS -X POST http://localhost:8090/search \\\n"
        "     -H 'content-type: application/json' \\\n"
        "     -d '{\"query\":\"Suez Gulf Approach\",\"hits\":5}'\n"
        "3) Concept-ID search (JSON country=Egypt even if wording differs):\n"
        "   curl -sS -X POST http://localhost:8090/search \\\n"
        "     -H 'content-type: application/json' \\\n"
        "     -d '{\"query\":\"country Egypt\",\"hits\":5,"
        "\"concept_ids\":[\"json:attribute:location.country\","
        "\"LOCATION_COUNTRY:Egypt\",\"OSINT_SOCMINT\"]}'\n"
        "4) Export catalog:\n"
        "   curl -sS -X POST http://localhost:8090/ontology/export "
        "-H 'content-type: application/json' -d '{}'\n"
        "5) Expand then retrieve children of OSINT_SOCMINT:\n"
        "   curl -sS -X POST http://localhost:8090/ontology/expand \\\n"
        "     -H 'content-type: application/json' \\\n"
        "     -d '{\"concept_ids\":[\"OSINT_SOCMINT\"],"
        "\"include_children\":true,\"business_ontology_dataset\":\"osint\"}'"
    )
    return 0


def run_live(*, limit: int) -> int:
    """Queue a tiny ingest if :8091 is up (does not wait for NLP).

    Example:
        >>> callable(run_live)
        True
    """
    from urllib.error import URLError
    from urllib.request import Request, urlopen

    body = json.dumps(
        {
            "dataset_path": (
                "osint/c2_middle_east_multi_source_1000_v5_200w_en.json"
            ),
            "index_target": "global",
            "limit": limit,
            "business_ontology_dataset": "osint",
        }
    ).encode("utf-8")
    req = Request(
        "http://localhost:8091/ingest/json-records",
        data=body,
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except URLError as exc:
        print(f"Live ingest skipped (is make ingest running?): {exc}")
        return 1
    print("Queued ingest:", json.dumps(payload, indent=2)[:800])
    print("Wait for jobs to finish, then use the curl examples above.")
    return 0


def main() -> int:
    """CLI entry.

    Example:
        >>> callable(main)
        True
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        default=DEFAULT_CORPUS,
        help="OSINT JSON corpus",
    )
    parser.add_argument(
        "--ontology",
        type=Path,
        default=DEFAULT_ONTOLOGY,
        help="business_ontology.yaml",
    )
    parser.add_argument("--limit", type=int, default=1, help="Records to inspect")
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also POST 3 records to localhost:8091",
    )
    args = parser.parse_args()
    if not args.corpus.is_file():
        print(f"Missing corpus: {args.corpus}", file=sys.stderr)
        return 1
    records = _load_records(args.corpus, limit=args.limit)
    rc = run_offline(records, args.ontology)
    if args.live:
        rc = run_live(limit=max(args.limit, 3)) or rc
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
