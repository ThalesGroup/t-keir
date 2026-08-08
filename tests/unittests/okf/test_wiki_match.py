"""Title: Unit tests for OKF wiki match / extract helpers.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from __future__ import annotations

import json
from pathlib import Path

from thot.okf.models import OkfBundle
from thot.okf.store import OkfBundleStore
from thot.okf.wiki_match import (
    extract_wiki_sections,
    find_closest_wiki,
    jaccard,
    wiki_extract_for_bundle,
)


def test_jaccard_and_extract_sections() -> None:
    assert jaccard("alpha beta", "alpha gamma") > 0
    md = (
        "# Topic\n\n## Answer\n\nHello port.\n\n"
        "## Structured facts\n\n- a: 1\n\n## Evidence\n\n- x\n"
    )
    out = extract_wiki_sections(md)
    assert "Hello port" in out
    assert "Evidence" not in out
    assert "Structured facts" in out


def _seed(root: Path, *, bid: str, space: str, index: str, wiki: str) -> None:
    bundle_dir = root / bid
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "index.md").write_text(index, encoding="utf-8")
    (bundle_dir / "wiki.md").write_text(wiki, encoding="utf-8")
    meta = {
        "bundle": (
            OkfBundle(
                bundle_id=bid,
                user_space=space,
                concept_count=0,
                path=str(bundle_dir),
                query="Latakia Port status",
            ).model_dump(mode="json")
        ),
        "concept_ids": [],
    }
    (bundle_dir / ".tkeir-meta.json").write_text(
        json.dumps(meta), encoding="utf-8"
    )


def test_find_closest_wiki_and_extract(tmp_path: Path) -> None:
    space = "dev@tkeir"
    bid = "latakia-1"
    _seed(
        tmp_path,
        bid=bid,
        space=space,
        index="# Latakia Port\n\nSummary: harbour activity near Latakia.\n",
        wiki=(
            "# Latakia Port\n\n## Answer\n\nHarbour is open.\n\n"
            "## Evidence\n\n- c1\n"
        ),
    )
    store = OkfBundleStore(tmp_path)
    match = find_closest_wiki(
        space, "Latakia harbour", store=store, threshold=0.05
    )
    assert match is not None
    assert match.bundle_id == bid
    payload = wiki_extract_for_bundle(bid, space, store=store)
    assert payload["found"] is True
    assert "Harbour is open" in payload["extract"]
    assert (
        find_closest_wiki(space, "zzzz unrelated", store=store, threshold=0.9)
        is None
    )
