"""Unit tests for generation eval helpers."""

from __future__ import annotations

import json
from pathlib import Path

from thot.tools.eval.generate_eval import (
    GenDatasetRun,
    GenExample,
    GenMetrics,
    dump_llm_prompt,
    load_multihop_rag,
    load_ragbench_split,
    render_report,
    safe_prompt_filename,
)
from thot.tasks.answer_generation.rag_answer import (
    PassageHit,
    RagAnswerResult,
    build_rag_prompts,
    coherent_short_answer,
    normalized_em,
    strip_answer_markup,
    structure_passages,
    token_f1,
)


def test_ontology_clues_sparql_from_query_terms() -> None:
    """Query NER/SVO terms yield SPARQL; merge formats clues."""
    from thot.tasks.answer_generation.ontology_clues import (
        format_clues_for_prompt,
        generate_sparql_from_query_ontology,
        OntologyClueBundle,
    )

    analysis = {
        "ner_entities": [{"text": "Sam Bankman-Fried", "label": "person"}],
        "svo_triples": [
            {"subject": "prosecutors", "verb": "accused", "object": "Bankman-Fried"}
        ],
        "search_terms": ["FTX", "fraud"],
        "keywords": ["FTX"],
        "lemmas": ["accuse", "fraud"],
        "morphosyntax": [
            {"text": "Who", "lemma": "who", "pos": "PRON"},
            {"text": "prosecutors", "lemma": "prosecutor", "pos": "NOUN"},
            {"text": "accused", "lemma": "accuse", "pos": "VERB"},
            {"text": "Bankman-Fried", "lemma": "Bankman-Fried", "pos": "PROPN"},
            {"text": "at", "lemma": "at", "pos": "ADP"},
            {"text": "FTX", "lemma": "FTX", "pos": "PROPN"},
        ],
    }
    queries = generate_sparql_from_query_ontology(
        analysis,
        "Who is Sam Bankman-Fried facing fraud charges at FTX?",
    )
    assert queries
    assert "PREFIX rdfs:" in queries[0]
    joined = "\n".join(queries).lower()
    assert "sam bankman-fried" in joined
    assert 'contains(lcase(str(?sl)), "who")' not in joined
    assert len(queries) >= 2  # label harvest + multihop bridge

    # Morph-only fallback (no NER / search_terms / keywords)
    morph_only = {
        "morphosyntax": [
            {"text": "Qui", "lemma": "qui", "pos": "PRON"},
            {"text": "dirige", "lemma": "diriger", "pos": "VERB"},
            {"text": "Acme", "lemma": "Acme", "pos": "PROPN"},
        ]
    }
    morph_queries = generate_sparql_from_query_ontology(morph_only, "Qui dirige Acme?")
    assert morph_queries
    joined = "\n".join(morph_queries).lower()
    assert "acme" in joined
    assert 'contains(lcase(str(?sl)), "qui")' not in joined

    bundle = OntologyClueBundle(
        ontology_facts="- Sam | accused | fraud",
        sparql_clues="- Sam Bankman-Fried — fraud — FTX",
        reasoner_note="consistency: ok",
        passage_graph_count=2,
        merged_triple_count=10,
    )
    text = format_clues_for_prompt(bundle)
    assert "Merged passage ontology" in text
    assert "graphs merged=2" in text
    # SPARQL stays on the bundle for the dedicated prompt block
    assert bundle.sparql_clues.startswith("- Sam")


def test_token_f1_and_em() -> None:
    """Answer scoring helpers behave sanely."""
    assert normalized_em("Sam Bankman-Fried", "sam bankman fried") == 1.0
    assert token_f1("the quick brown fox", "quick fox") > 0.5
    assert token_f1("", "x") == 0.0


def test_clean_short_answer_markup_and_syntagm() -> None:
    """SHORT_ANSWER uses NLP NER / pattern_syntagm_or_prep_group spans."""
    assert (
        strip_answer_markup("**\nSam Bankman-Fried\n\n**")
        == "Sam Bankman-Fried"
    )
    assert coherent_short_answer("** Yes\n\n**", question_type="yes_no") == "Yes"
    assert (
        coherent_short_answer(
            "Sam Bankman-Fried is facing trial. More details follow.",
            question_type="who",
        )
        == "Sam Bankman-Fried is facing trial."
    )
    morph = [
        {"text": "Sam", "pos": "PROPN", "is_sent_start": True},
        {"text": "Bankman-Fried", "pos": "PROPN", "is_sent_start": False},
        {"text": "is", "pos": "AUX", "is_sent_start": False},
        {"text": "facing", "pos": "VERB", "is_sent_start": False},
        {"text": "trial", "pos": "NOUN", "is_sent_start": False},
        {"text": ".", "pos": "PUNCT", "is_sent_start": False},
    ]
    assert (
        coherent_short_answer(
            "**\nSam Bankman-Fried is facing trial.\n**",
            question_type="who",
            morphosyntax=morph,
            named_entities=["Sam Bankman-Fried"],
            syntagms=["Sam Bankman-Fried"],
        )
        == "Sam Bankman-Fried"
    )

    from thot.tasks.answer_generation.rag_answer import (
        extract_nlp_named_entities,
        extract_nlp_syntagms,
    )

    processed = {
        "content_ner": [
            {"text": "Sam Bankman-Fried", "label": "person", "start": 0, "end": 2}
        ],
        "kg": [
            {
                "subject": {
                    "label": "pattern_syntagm_or_prep_group",
                    "content": ["Sam", "Bankman-Fried"],
                },
                "property": {"label": "pattern_verb_phrase", "content": ["is"]},
                "object": {
                    "label": "pattern_syntagm_or_prep_group",
                    "content": ["former", "CEO"],
                },
            }
        ],
    }
    assert extract_nlp_named_entities(processed) == ["Sam Bankman-Fried"]
    assert "Sam Bankman-Fried" in extract_nlp_syntagms(processed)
    assert "former CEO" in extract_nlp_syntagms(processed)


def test_load_ragbench_oracle_documents(tmp_path: Path) -> None:
    """RAGBench loader uses provided documents as evidence."""
    rows = [
        {
            "id": "q1",
            "question": "What causes fever?",
            "response": "Infection can cause fever.",
            "documents": [
                "Title: Doc A\nPassage: fever from infection",
                "Title: Doc B\nPassage: unrelated",
            ],
            "all_relevant_sentence_keys": ["0a"],
        }
    ]
    (tmp_path / "test.json").write_text(json.dumps(rows), encoding="utf-8")
    examples = load_ragbench_split(tmp_path)
    assert len(examples) == 1
    assert examples[0].query.startswith("What causes")
    assert examples[0].gold.startswith("Infection")
    assert len(examples[0].passages) == 2
    assert "fever from infection" in examples[0].passages[0].text


def test_load_multihop_evidence_list(tmp_path: Path) -> None:
    """MultiHop loader uses evidence_list facts (no corpus.json)."""
    (tmp_path / "MultiHopRAG.json").write_text(
        json.dumps(
            [
                {
                    "query": "Who?",
                    "answer": "Alice",
                    "question_type": "inference_query",
                    "evidence_list": [
                        {
                            "title": "Alpha Story",
                            "source": "News",
                            "fact": "Alice founded Acme.",
                        }
                    ],
                }
            ]
        ),
        encoding="utf-8",
    )
    examples = load_multihop_rag(tmp_path)
    assert len(examples) == 1
    assert examples[0].gold == "Alice"
    assert examples[0].query == "Who?"
    assert examples[0].passages[0].text == "Alice founded Acme."
    assert "Alpha Story" in examples[0].passages[0].title


def test_structure_passages_without_runner() -> None:
    """Passage structuring works without NLP runner."""
    focus, facts, note, docs = structure_passages(
        "Who is Alice?",
        [
            PassageHit(
                "d1",
                "Alice bio",
                "Alice founded Acme in 2020 and lives in Paris.",
                1.0,
            )
        ],
        analysis={"raw_query": "Who is Alice?"},
        runner=None,
        use_reasoner=False,
    )
    assert "Alice" in focus or "Alice" in facts
    assert "Source excerpts" in facts
    assert note == ""
    assert docs == []


def test_build_rag_prompts_svo_mode() -> None:
    """Unique prompt combines passages, NER/SVO, and optional ontology clues."""
    system, user = build_rag_prompts(
        query="Who is Alice?",
        analysis={
            "raw_query": "Who is Alice?",
            "ner_entities": [{"text": "Alice", "label": "PERSON"}],
            "svo_triples": [
                {"subject": "Who", "verb": "is", "object": "Alice"}
            ],
            "morphosyntax": [{"text": "Who", "pos": "PRON"}],
        },
        focus_passages="Alice founded Acme.",
        structured_facts=(
            "SVO facts from retrieved passages:\n"
            "- Alice — founded — Acme\n"
            "Source excerpts:\n[bio]\nAlice founded Acme."
        ),
        ontology_facts=(
            "Merged passage ontology (document_ontology):\n"
            "- Alice | founded | Acme\n"
            "- Alice | type | Entity\n"
            "(graphs merged=1, triples=2)"
        ),
        sparql_clues="(no SPARQL hits)",
        language="en",
        question_type="who",
    )
    assert "SHORT_ANSWER" in user
    assert "QUESTION TYPE: who" in user
    assert "QUERY NER:" in user
    assert "Alice (PERSON)" in user
    assert "PASSAGE SVO:" in user
    assert "KEY PASSAGES (primary evidence)" in user
    assert "SOURCE EXCERPTS" in user
    assert "ONTOLOGY CLUES" in user
    assert "Alice | founded | Acme" in user
    # Empty SPARQL must not appear as a hard gate
    assert "SPARQL CLUES" not in user
    assert "passages" in system.lower()
    assert "optional" in system.lower()


def test_detect_question_type_prefers_yes_no_over_entity_report() -> None:
    """Yes/no openers beat NER-heavy entity_report heuristics."""
    from thot.tools.search.generation_prompt import detect_question_type

    q = (
        "Does the Sporting News article suggest that streaming services "
        "do not require a subscription?"
    )
    analysis = {
        "morphosyntax": [{"text": "Does", "pos": "AUX"}],
        "ner_entities": [
            {"text": "Sporting News", "label": "ORG"},
            {"text": "Cowboys", "label": "ORG"},
        ],
        "lemmas": ["Does", "Sporting", "News", "article", "suggest"],
    }
    assert detect_question_type(q, analysis) == "yes_no"
    assert (
        detect_question_type(
            "Who founded Acme?",
            {"morphosyntax": [{"text": "Who", "pos": "PRON"}]},
        )
        == "who"
    )
    # Inverted yes/no mid-clause (MultiHop consistency questions)
    inverted = (
        "Between the TechCrunch report on Sam Bankman-Fried's trial and the "
        "subsequent report by the same source on the prosecution's "
        "allegations against him, was there consistency in the portrayal "
        "of the charges he is facing?"
    )
    assert detect_question_type(inverted, {}) == "yes_no"


def test_detect_question_type_and_forge_brief() -> None:
    """Question type + unique ontology prompt surface SVO relations."""
    from thot.tasks.answer_generation.rag_answer import (
        build_query_passage_ontology,
        build_unique_qa_prompt,
    )
    from thot.tools.search.generation_prompt import detect_question_type

    who = detect_question_type(
        "Who founded Acme?",
        {"morphosyntax": [{"text": "Who", "pos": "PRON"}]},
    )
    assert who == "who"
    assert detect_question_type("Is FTX bankrupt?") == "yes_no"

    analysis = {
        "svo_triples": [
            {"subject": "Who", "verb": "founded", "object": "Acme"}
        ],
        "ner_entities": [{"text": "Acme", "label": "ORG"}],
        "morphosyntax": [{"text": "Who", "pos": "PRON"}],
    }
    facts = (
        "SVO facts from retrieved passages:\n"
        "- Alice — founded — Acme\n"
        "Source excerpts:\n"
        "[bio]\nAlice founded Acme."
    )
    ontology, _note = build_query_passage_ontology(
        analysis, facts, use_reasoner=False
    )
    assert "Passage relations:" in ontology
    assert "Alice — founded — Acme" in ontology
    _system, user = build_unique_qa_prompt(
        query="Who founded Acme?",
        analysis=analysis,
        focus_passages="Alice founded Acme in 2020.",
        structured_facts=facts,
        ontology_facts=ontology,
        question_type="who",
    )
    assert "QUESTION TYPE: who" in user
    assert "KEY PASSAGES (primary evidence)" in user
    assert "QUERY NER:" in user or "QUERY SVO:" in user
    assert "OPTIONAL ONTOLOGY" in user


def test_render_report_multihop_gap() -> None:
    """Report compares MultiHop contains-acc to GPT-4 ground-truth."""
    leaderboard = {
        "datasets": {
            "multihop_rag": {
                "generation": {
                    "models": {
                        "GPT-4": {
                            "accuracy_retrieved": 0.56,
                            "accuracy_ground_truth": 0.89,
                        }
                    }
                }
            }
        }
    }
    metrics = GenMetrics(n=2, em=1.0, f1=1.2, contains=1.0, errors=0)
    run = GenDatasetRun(
        name="multihop",
        display="MultiHop-RAG",
        family="multihop_rag",
        evidence_passages=5,
        query_count=2,
        metrics=metrics,
    )
    body = render_report(
        [run], leaderboard=leaderboard, forge_prompt=True
    )
    assert "Summary vs leaderboard" in body
    assert "oracle evidence" in body.lower() or "evidence_list" in body
    assert "0.500" in body  # contains avg
    assert "0.890" in body or "0.89" in body
    assert "ground-truth" in body


def test_safe_prompt_filename() -> None:
    """Query ids are sanitized for dump paths."""
    assert safe_prompt_filename("mh_q_12") == "mh_q_12"
    assert "/" not in safe_prompt_filename("a/b:c")
    assert safe_prompt_filename("") == "query"


def test_dump_llm_prompt(tmp_path: Path) -> None:
    """Prompt dump writes JSON with system/user and progress fields."""
    example = GenExample(
        query_id="mh_q_1",
        query="Who?",
        gold="Alice",
        passages=[PassageHit("e0", "T", "Alice founded Acme.", 1.0)],
    )
    answer = RagAnswerResult(
        query_id="mh_q_1",
        query="Who?",
        short_answer="Alice",
        detailed_report="Alice founded Acme.",
        input_prompt="SYSTEM:\nS\n\nUSER:\nU",
        forged=True,
        system_prompt="S",
        user_prompt="U",
    )
    path = dump_llm_prompt(
        tmp_path,
        dataset="multihop",
        example=example,
        answer=answer,
        index=1,
        total=10,
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["index"] == 1
    assert payload["total"] == 10
    assert payload["system_prompt"] == "S"
    assert payload["user_prompt"] == "U"
    assert payload["gold"] == "Alice"
    assert path.name == "mh_q_1.json"
