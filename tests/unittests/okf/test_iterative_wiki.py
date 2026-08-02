"""Unit tests for iterative chunk-by-chunk LLM Wiki helpers."""

from __future__ import annotations

import asyncio
import json

from thot.okf.iterative_wiki import (
    _chunk_narrative_budget,
    _format_chunk_block,
    build_merge_prompt,
    build_wiki_iteratively,
    build_wiki_single_pass,
    chunks_from_params,
    compact_information_for_prompt,
    create_evidence_bundle,
    enrich_chunks_with_sibling_information,
    ensure_sources_section,
    extract_wiki_markdown,
    load_evidence_chunks,
    normalize_evidence_chunk,
    seed_iterative_wiki,
    split_narrative_and_information,
    write_evidence_chunks,
)


def test_seed_has_answer_evidence_sources():
    wiki = seed_iterative_wiki(query="MT RED SEA EAGLE")
    assert "## Answer" in wiki
    assert "## Evidence" in wiki
    assert "## Sources" in wiki
    assert "MT RED SEA EAGLE" in wiki
    # Generic OKF seed has no form-specific checklist.
    assert "INTSUM checklist" not in wiki


def test_seed_truncates_long_title_and_defaults():
    long_q = "X" * 100
    wiki = seed_iterative_wiki(query=long_q)
    assert "…" in wiki
    assert "Knowledge wiki" in seed_iterative_wiki(query="   ")


def test_seed_accepts_persona_structured_facts():
    facts = "## Structured facts (INTSUM checklist)\n\n- maritime: _unknown_\n"
    wiki = seed_iterative_wiki(
        query="MT RED SEA EAGLE", structured_facts_seed=facts
    )
    assert "## Structured facts (INTSUM checklist)" in wiki
    assert "maritime:" in wiki
    # Order: Answer then Structured facts then Evidence
    assert wiki.index("## Answer") < wiki.index("Structured facts")
    assert wiki.index("Structured facts") < wiki.index("## Evidence")


def test_normalize_and_persist_chunks(tmp_path):
    rows = [
        {
            "chunk_id": "c1",
            "parent_doc_id": "doc-a",
            "text_raw": "AIS off near Beirut.",
        },
        {"chunk_id": "c1", "text_raw": "duplicate ignored"},
        {"chunk_id": "", "text_raw": ""},  # dropped
    ]
    path = write_evidence_chunks(tmp_path, rows)
    assert path.is_file()
    loaded = load_evidence_chunks(tmp_path)
    assert len(loaded) == 1
    assert loaded[0]["chunk_id"] == "c1"
    assert "Beirut" in loaded[0]["text_raw"]


def test_load_evidence_chunks_edges(tmp_path):
    assert load_evidence_chunks(tmp_path) == []
    bad = tmp_path / "evidence_chunks.json"
    bad.write_text("{not-json", encoding="utf-8")
    assert load_evidence_chunks(tmp_path) == []
    bad.write_text('{"not": "a list"}', encoding="utf-8")
    assert load_evidence_chunks(tmp_path) == []


def test_chunks_from_params():
    params = {
        "chunks": [
            {
                "chunk_id": "g1",
                "parent_doc_id": "p1",
                "text_raw": "SAR confirmed dark activity.",
            }
        ]
    }
    out = chunks_from_params(params)
    assert out[0]["chunk_id"] == "g1"
    assert chunks_from_params(None) == []
    assert chunks_from_params({"chunks": "not-json{"}) == []
    as_json = chunks_from_params(
        {
            "grab_chunks": json.dumps(
                [{"chunk_id": "j1", "text_raw": "from json string"}]
            )
        }
    )
    assert as_json[0]["chunk_id"] == "j1"
    assert chunks_from_params({"chunks": {"bad": True}}) == []
    assert (
        chunks_from_params({"chunks": [{"chunk_id": "x", "text_raw": ""}]})
        == []
    )


def test_extract_wiki_markdown_from_fence():
    raw = "```markdown\n# Title\n## Answer\nFact.\n```"
    out = extract_wiki_markdown(raw, fallback="OLD")
    assert out.startswith("# Title")
    assert "## Answer" in out


def test_extract_wiki_markdown_fallbacks():
    assert extract_wiki_markdown("", fallback="KEEP") == "KEEP"
    assert "Evidence" in extract_wiki_markdown(
        "## Evidence\n- claim\n", fallback="KEEP"
    )
    assert extract_wiki_markdown("just prose", fallback="KEEP") == "KEEP"


def test_ensure_sources_adds_missing_chunk_ids():
    wiki = seed_iterative_wiki(query="q")
    updated = ensure_sources_section(
        wiki,
        [{"chunk_id": "abc", "parent_doc_id": "doc1", "text_raw": "x"}],
    )
    assert "chunk_id=`abc`" in updated
    assert "parent=`doc1`" in updated
    # Already listed → no duplicate; no parent → bare id
    bare = ensure_sources_section(
        "## Answer\n\n## Sources\n",
        [{"chunk_id": "z9", "parent_doc_id": "", "text_raw": "x"}],
    )
    assert "chunk_id=`z9`" in bare
    assert "parent=" not in bare
    # No Sources heading, no Gaps
    no_src = ensure_sources_section(
        "# Only title",
        [{"chunk_id": "n1", "parent_doc_id": "p", "text_raw": "x"}],
    )
    assert "## Sources" in no_src
    assert (
        ensure_sources_section("## Sources\n- chunk_id=`n1`\n", [])[-1] == "\n"
    )


def test_merge_prompt_includes_chunk_and_wiki():
    prompt = build_merge_prompt(
        query="Tell me about the vessel",
        current_wiki=seed_iterative_wiki(query="vessel"),
        chunk={
            "chunk_id": "c9",
            "parent_doc_id": "doc9",
            "title": "",
            "text_raw": "Vessel disabled AIS for 18 hours.",
            "information": "- **evaluation:** B1\n",
        },
        index=1,
        total=3,
    )
    assert "c9" in prompt
    assert "disabled AIS" in prompt
    assert "WIKI START" in prompt
    assert "Information" in prompt


def test_merge_prompt_truncates_long_inputs():
    prompt = build_merge_prompt(
        query="q",
        current_wiki="W" * 25000,
        chunk={
            "chunk_id": "c",
            "parent_doc_id": "d",
            "title": "t",
            "text_raw": "N" * 7000,
            "information": "",
        },
        index=1,
        total=1,
    )
    assert "chunk truncated" in prompt
    assert "wiki truncated" in prompt


def test_normalize_rejects_empty():
    assert normalize_evidence_chunk({}) is None
    assert normalize_evidence_chunk("bad") is None
    assert normalize_evidence_chunk({"chunk_id": "x"}) is not None
    anon = normalize_evidence_chunk({"text_raw": "anonymous body only"})
    assert anon is not None
    assert anon["chunk_id"].startswith("anon:")
    meta_only = normalize_evidence_chunk(
        {
            "chunk_id": "m1",
            "text_raw": "",
            "information": "- **evaluation:** A1",
        }
    )
    assert meta_only is not None
    assert "metadata-only" in meta_only["text_raw"]


def test_split_information_clean_markdown():
    text = (
        "# Title\n\nNarrative about AIS gap.\n\n## Information\n\n"
        "- **evaluation:**\n  - **code:** B1\n"
        "- **location:**\n  - **name:** Beirut\n"
        "\n## Other\n\nIgnore me.\n"
    )
    narrative, info = split_narrative_and_information(text)
    assert "AIS gap" in narrative
    assert "B1" in info
    assert "Beirut" in info
    assert "Ignore me" not in info
    row = normalize_evidence_chunk(
        {"chunk_id": "c1", "parent_doc_id": "d1", "text_raw": text}
    )
    assert row is not None
    assert "AIS gap" in row["text_raw"]
    assert "B1" in row["information"]
    assert "## Information" not in row["text_raw"]


def test_split_information_mangled_and_collapsed():
    text = "Body facts here.\n# # Information\n- * * evaluation :* * B1"
    narrative, info = split_narrative_and_information(text)
    assert "Body facts" in narrative
    assert "evaluation" in info.casefold()
    collapsed = "Lead ## Information - **source:** SIGINT"
    narr2, info2 = split_narrative_and_information(collapsed)
    assert "Lead" in narr2
    assert "SIGINT" in info2
    assert split_narrative_and_information("") == ("", "")


def test_compact_information_priority_and_truncate():
    blob = "\n".join(
        [
            "- **noise_field:** aaa",
            "- **evaluation:** B1",
            "- **location:** Beirut",
            "- **other:** " + ("z" * 2000),
        ]
    )
    out = compact_information_for_prompt(blob, max_chars=200)
    assert "evaluation" in out
    assert "information truncated" in out
    assert compact_information_for_prompt("") == ""
    assert compact_information_for_prompt("   \n  ") == ""


def test_format_chunk_block_and_budget():
    assert _chunk_narrative_budget(1) <= 2800
    assert _chunk_narrative_budget(20) >= 1000
    block = _format_chunk_block(
        {
            "chunk_id": "c1",
            "parent_doc_id": "d1",
            "title": "t",
            "text_raw": "N" * 5000,
            "information": "- **evaluation:** A1",
        },
        1,
        8,
        max_chars=100,
    )
    assert "chunk truncated" in block
    assert "Information" in block


def test_enrich_siblings_merge_information():
    chunks = [
        {
            "chunk_id": "n1",
            "parent_doc_id": "docA",
            "text_raw": "Narrative only about the vessel.",
            "information": "",
            "title": "",
            "score": "1",
        },
        {
            "chunk_id": "i1",
            "parent_doc_id": "docA",
            "text_raw": "(metadata-only chunk — see Information block)",
            "information": compact_information_for_prompt(
                "- **evaluation:**\n  - **code:** D2\n- **pir_ref:** PIR-01"
            ),
            "title": "",
            "score": "0.5",
        },
    ]
    out = enrich_chunks_with_sibling_information(chunks)
    assert "D2" in out[0]["information"]
    assert "PIR-01" in out[0]["information"]
    assert (
        enrich_chunks_with_sibling_information(
            [
                {
                    "chunk_id": "x",
                    "parent_doc_id": "",
                    "text_raw": "a",
                    "information": "",
                }
            ]
        )[0]["chunk_id"]
        == "x"
    )


def test_create_evidence_bundle(tmp_path, monkeypatch):
    from thot.okf import iterative_wiki as mod

    monkeypatch.setattr(
        mod,
        "user_okf_root",
        lambda user_space, workspace=None: tmp_path / "okf",
        raising=False,
    )
    # Patch import path used inside create_evidence_bundle
    import thot.okf.exporter as exporter

    monkeypatch.setattr(
        exporter,
        "user_okf_root",
        lambda user_space, workspace=None: tmp_path / "okf",
    )
    bid, root = create_evidence_bundle(
        user_space="dev@tkeir",
        query="MT RED SEA EAGLE",
        chunks=[
            {
                "chunk_id": "c1",
                "parent_doc_id": "d1",
                "text_raw": "AIS disabled near Beirut.",
            }
        ],
        structured_facts_seed="## Structured facts\n\n- x: _unknown_\n",
    )
    assert bid
    assert (root / "evidence_chunks.json").is_file()
    assert (root / "wiki.md").is_file()
    assert "Structured facts" in (root / "wiki.md").read_text(encoding="utf-8")
    assert "AIS" in load_evidence_chunks(root)[0]["text_raw"]


class _FakeLlm:
    def __init__(self, payload: str | None = None):
        self.calls = 0
        self.payload = payload

    async def generate(self, prompt, system=None, temperature=0.1):
        self.calls += 1
        if self.payload is not None:
            return self.payload
        return (
            "---\ntype: Wiki\ntitle: t\n---\n# t\n\n## Answer\n"
            "AIS off near Beirut.\n\n## Evidence\n"
            "- AIS disabled (chunk_id=c1)\n\n## Sources\n"
            "- chunk_id=`c1` ← parent=`d1`\n"
        )


def test_build_wiki_iteratively_is_single_llm_call():
    llm = _FakeLlm()
    chunks = [
        {
            "chunk_id": f"c{i}",
            "parent_doc_id": "d1",
            "text_raw": f"Fact number {i} about AIS gap.",
        }
        for i in range(1, 10)
    ]
    progress: list[tuple[int, int]] = []

    def _on_progress(wiki_text: str, index: int, total: int) -> None:
        progress.append((index, total))

    wiki = asyncio.run(
        build_wiki_iteratively(
            llm=llm,
            query="MT RED SEA EAGLE",
            chunks=chunks,
            max_chunks=24,  # caller asks high; builder still one pass / capped
            on_progress=_on_progress,
            system="custom system",
            information_priority_keys=["evaluation"],
        )
    )
    assert llm.calls == 1
    assert "AIS" in wiki or "Answer" in wiki
    assert progress and progress[0][1] <= 12


def test_build_wiki_empty_chunks_and_progress_error():
    llm = _FakeLlm()
    wiki = asyncio.run(
        build_wiki_iteratively(
            llm=llm,
            query="empty",
            chunks=[],
            initial_wiki="# Prior\n\n## Sources\n",
        )
    )
    assert llm.calls == 0
    assert "Prior" in wiki or "Sources" in wiki

    empty_pass = asyncio.run(
        build_wiki_single_pass(llm=llm, query="q", chunks=[])
    )
    assert "## Answer" in empty_pass

    def _boom(*_a, **_k):
        raise RuntimeError("progress boom")

    wiki2 = asyncio.run(
        build_wiki_iteratively(
            llm=_FakeLlm(),
            query="q",
            chunks=[
                {
                    "chunk_id": "c1",
                    "parent_doc_id": "d1",
                    "text_raw": "fact",
                }
            ],
            on_progress=_boom,
        )
    )
    assert (
        "## Answer" in wiki2 or "fact" in wiki2.lower() or "Sources" in wiki2
    )
