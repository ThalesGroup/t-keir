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
    build_wiki_upsert_pass,
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
    # Without keys: preserve order, only truncate.
    plain = compact_information_for_prompt(blob, max_chars=80)
    assert plain.startswith("- **noise_field:**")
    assert "information truncated" in plain
    # With persona keys: rank matching lines first.
    out = compact_information_for_prompt(
        blob,
        max_chars=200,
        priority_keys=["evaluation", "location"],
    )
    assert out.startswith("- **evaluation:**")
    assert "location" in out
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


def test_build_wiki_upsert_pass_single_call():
    llm = _FakeLlm()
    wiki = asyncio.run(
        build_wiki_upsert_pass(
            llm=llm,
            query="MT RED SEA EAGLE",
            chunks=[
                {
                    "chunk_id": "c1",
                    "parent_doc_id": "d1",
                    "text_raw": "AIS disabled near Beirut.",
                }
            ],
            current_wiki="# Prior\n\n## Answer\n\nOld.\n",
            max_chunks=4,
        )
    )
    assert llm.calls == 1
    assert "Answer" in wiki or "AIS" in wiki


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


def test_estimate_and_pack_clusters_fit_budget():
    from thot.okf.iterative_wiki import (
        estimate_chars_to_tokens,
        estimate_fold_prompt_chars,
        pack_clusters_for_llm_budget,
    )

    assert estimate_chars_to_tokens(4000) == 1000
    est = estimate_fold_prompt_chars(
        wiki_chars=500, chunk_count=4, max_chunk_chars=1000
    )
    assert 2000 < est < 20000
    clusters = [
        [{"chunk_id": f"c{i}", "text_raw": "x" * 200}] for i in range(5)
    ]
    packs = pack_clusters_for_llm_budget(
        clusters,
        wiki_chars=400,
        max_chunk_chars=800,
        prompt_char_budget=14000,
        max_fold_calls=2,
    )
    assert 1 <= len(packs) <= 2
    assert sum(len(p) for p in packs) == 5

    # Overflow / max_fold_calls: every chunk is kept (folded into last pack).
    big = [[{"chunk_id": f"b{i}", "text_raw": "y" * 2500}] for i in range(6)]
    packed = pack_clusters_for_llm_budget(
        big,
        wiki_chars=2000,
        max_chunk_chars=2200,
        prompt_char_budget=8000,
        max_fold_calls=1,
    )
    assert 1 <= len(packed) <= 2
    assert sum(len(p) for p in packed) == 6
    assert (
        pack_clusters_for_llm_budget([], wiki_chars=100, max_chunk_chars=800)
        == []
    )

    # Force pack split then leftover merge into the last pack.
    many = [[{"chunk_id": f"m{i}", "text_raw": "z" * 1800}] for i in range(8)]
    forced = pack_clusters_for_llm_budget(
        many,
        wiki_chars=5000,
        max_chunk_chars=2000,
        prompt_char_budget=7000,
        max_fold_calls=2,
    )
    assert len(forced) == 2
    assert sum(len(p) for p in forced) == 8


def test_ensure_osiris_panel_sections_injects_missing():
    from thot.okf.iterative_wiki import ensure_osiris_panel_sections

    assert ensure_osiris_panel_sections("") == ""
    md = "## Answer\n\nHello\n\n## Sources\n\n- a\n"
    out = ensure_osiris_panel_sections(md)
    assert "## Timeline" in out
    assert "## Cross-source synthesis" in out
    assert "## Conjectures" in out
    assert out.index("## Answer") < out.index("## Timeline")
    assert out.index("## Timeline") < out.index("## Sources")

    # Events alias skips Timeline inject; Gaps anchors when Sources missing.
    with_events = (
        "## Answer\n\nx\n\n## Events\n\n- e\n\n"
        "## Cross-source synthesis\n\n- c\n\n"
        "## Conjectures\n\n- n\n\n## Gaps\n\n- g\n"
    )
    kept = ensure_osiris_panel_sections(with_events)
    assert kept.count("## Timeline") == 0
    assert "## Gaps" in kept
    no_anchor = ensure_osiris_panel_sections("## Answer\n\nOnly answer\n")
    assert "## Timeline" in no_anchor
    assert "## Conjectures" in no_anchor


def test_merge_timeline_preserves_answer():
    from thot.okf.iterative_wiki import (
        _section_body,
        _wiki_context_for_fold,
        merge_timeline_into_wiki,
    )

    prior = (
        "## Answer\n\nSituation is tense.\n\n"
        "## Timeline\n\n- old\n\n"
        "## Sources\n\n- s1\n"
    )
    timeline_only = (
        "## Timeline\n\n"
        "- event_id=E1 | when=2024-01-01 | where=Izmir | what=quake\n"
        "- E1 --> E2 | kind=sequence\n"
    )
    merged = merge_timeline_into_wiki(prior, timeline_only)
    assert "Situation is tense" in merged
    assert "event_id=E1" in merged
    assert "## Sources" in merged
    assert merge_timeline_into_wiki(prior, "") == prior.strip()
    assert merge_timeline_into_wiki("", timeline_only) == timeline_only.strip()
    assert _section_body(prior, "Missing") is None

    long_prior = (
        "## Answer\n\n"
        + ("Long narrative sentence. " * 40)
        + "\n\n## Timeline\n\n- old\n\n## Sources\n\n- s\n"
    )
    short_updated = "## Answer\n\nShort.\n\n## Timeline\n\n- new event\n\n## Sources\n\n- s\n"
    prefer_prior = merge_timeline_into_wiki(long_prior, short_updated)
    assert "Long narrative" in prefer_prior
    assert "new event" in prefer_prior

    empty_ctx = _wiki_context_for_fold("", max_chars=1000)
    assert "empty wiki" in empty_ctx
    long_wiki = "## Answer\n\n" + ("para " * 2000) + "\n\n## Sources\n\n- z\n"
    truncated = _wiki_context_for_fold(long_wiki, max_chars=3000)
    assert "omitted for prompt budget" in truncated


def test_fold_cluster_timeout_retries_leaner(monkeypatch):
    from thot.okf import iterative_wiki as iw

    calls: list[str] = []

    class _Flaky:
        async def generate(self, prompt, system=None, temperature=0.1):
            calls.append(prompt)
            if len(calls) == 1:
                raise TimeoutError("slow ollama")
            return (
                "## Answer\n\nRecovered after lean retry.\n\n"
                "## Sources\n\n- c1\n"
            )

    out = asyncio.run(
        iw.fold_cluster_into_wiki(
            llm=_Flaky(),
            query="quake",
            cluster=[
                {"chunk_id": "c1", "text_raw": "Magnitude 5.8 near Izmir"}
            ],
            current_wiki="## Answer\n\nSeed.\n\n## Sources\n\n",
            index=1,
            total=1,
            max_chunk_chars=1200,
            max_wiki_chars=5000,
        )
    )
    assert len(calls) == 2
    assert "Recovered after lean retry" in out


def test_build_wiki_iteratively_cluster_packs_with_fake_llm(monkeypatch):
    from thot.okf import iterative_wiki as iw

    class _FakeLlm:
        async def generate(self, prompt, system=None, temperature=0.1):
            return (
                "## Answer\n\nFolded situation.\n\n"
                "## Structured facts\n\n- ok\n\n"
                "## Evidence\n\n- claim\n\n"
                "## Timeline\n\n- event_id=E1 | when=unknown | where=x | what=y\n\n"
                "## Cross-source synthesis\n\n- link\n\n"
                "## Conjectures\n\n- _none grounded_\n\n"
                "## Sources\n\n"
            )

    def _fake_cluster(chunks, **_kwargs):
        mid = max(1, len(chunks) // 2)
        return [list(chunks[:mid]), list(chunks[mid:]) or list(chunks[:1])]

    monkeypatch.setattr(
        "thot.okf.chunk_cluster.cluster_chunks_agglomerative",
        _fake_cluster,
    )

    chunks = [
        {
            "chunk_id": f"c{i}",
            "parent_doc_id": f"d{i}",
            "title": f"t{i}",
            "text_raw": (
                ("earthquake Izmir " if i < 3 else "malware botnet ")
                + ("word " * 40)
            ),
        }
        for i in range(6)
    ]
    wiki = asyncio.run(
        build_wiki_iteratively(
            llm=_FakeLlm(),
            query="osiris live",
            chunks=chunks,
            cluster=True,
            max_clusters=4,
            per_cluster_for_llm=2,
            max_chunk_chars=600,
            max_wiki_chars=4000,
            prompt_char_budget=12000,
            max_fold_calls=2,
        )
    )
    assert "## Answer" in wiki
    assert "Folded situation" in wiki or "## Sources" in wiki

    # Pack timeout keeps prior wiki + panel sections.
    class _TimeoutLlm:
        async def generate(self, prompt, system=None, temperature=0.1):
            raise TimeoutError("fold pack stalled")

    timed = asyncio.run(
        build_wiki_iteratively(
            llm=_TimeoutLlm(),
            query="q",
            chunks=chunks[:3],
            cluster=True,
            max_fold_calls=1,
            prompt_char_budget=14000,
        )
    )
    assert "## Answer" in timed
    assert "timed out" in timed.lower() or "## Timeline" in timed

    # Sequential fold path (no agglomerative).
    seq = asyncio.run(
        build_wiki_iteratively(
            llm=_FakeLlm(),
            query="seq",
            chunks=chunks[:2],
            cluster=False,
            sequential=True,
            max_chunk_chars=500,
        )
    )
    assert "## Answer" in seq

    # Prebuilt clusters path.
    def _fake_centroids(full, per_cluster=3):
        return [g[:per_cluster] for g in full if g]

    monkeypatch.setattr(
        "thot.okf.chunk_cluster.select_near_centroids",
        _fake_centroids,
    )
    prebuilt = asyncio.run(
        build_wiki_iteratively(
            llm=_FakeLlm(),
            query="pre",
            chunks=chunks[:2],
            cluster=True,
            prebuilt_clusters=[chunks[:2], chunks[2:4]],
            max_fold_calls=2,
        )
    )
    assert "## Answer" in prebuilt
    assert callable(iw.fold_cluster_into_wiki)
