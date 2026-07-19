"""Tests that exercise documented examples in public tool APIs."""

import json
import os
import tempfile

from thot.core.LlmWrapper import Provider, WrapperConfig
from thot.core.TkeirPaths import (
    configs_dir,
    effective_resources_path,
    package_root,
    rag_prompts_path,
    repo_root,
    resolve_path,
    resolve_tkeir_paths,
    resources_dir,
    vespa_dir,
)
from thot.tools.pipeline import _collect_inputs, _is_tkeir_document
from thot.tools.search.app import (
    _format_chunk_excerpts,
    _no_chunks_message,
    _parse_hits,
    _unavailable_answer,
)
from thot.tools.search.ontology_utils import (
    build_hmi_ontology,
    extract_relevant_triples,
    merge_turtle_graphs,
    summarize_graph_for_prompt,
)
from thot.tools.search.vespa_client import (
    build_chunk_tensor,
    build_questions_tensor,
    chunk_embedding_text,
    chunk_vespa_id,
    document_vespa_id,
    escape_yql_literal,
    sanitize_vespa_string,
    sanitize_vespa_strings,
    stable_document_key,
    strip_search_vector_payload,
)


class TestTkeirPathsDocExamples:
    def test_package_root_example(self):
        assert os.path.isdir(os.path.join(package_root(), "thot"))

    def test_configs_dir_example(self):
        assert os.path.isfile(os.path.join(configs_dir(), "pipeline.yaml"))

    def test_resources_dir_example(self):
        assert os.path.isdir(resources_dir("en"))

    def test_vespa_dir_example(self):
        assert os.path.isdir(vespa_dir())
        assert vespa_dir().startswith(repo_root())

    def test_rag_prompts_path_example(self):
        assert os.path.isfile(rag_prompts_path())

    def test_resolve_path_example(self):
        assert resolve_path("configs/pipeline.yaml").endswith(
            "configs/pipeline.yaml"
        )

    def test_resolve_tkeir_paths_example(self):
        cfg = {
            "segmenters": [
                {"resources-base-path": "resources/modeling/tokenizer/en"}
            ]
        }
        resolve_tkeir_paths(cfg)
        assert cfg["segmenters"][0]["resources-base-path"].endswith(
            "tokenizer/en"
        )

    def test_effective_resources_path_example(self):
        assert effective_resources_path(None, "en") == resources_dir("en")


class TestVespaClientDocExamples:
    def test_sanitize_vespa_string_example(self):
        assert sanitize_vespa_string("hello\fworld") == "hello world"

    def test_sanitize_vespa_strings_example(self):
        assert sanitize_vespa_strings(["ok", "bad\f", ""]) == ["ok", "bad", ""]

    def test_strip_search_vector_payload_example(self):
        assert (
            strip_search_vector_payload(
                "[CONTEXT_BEFORE] intro Core text [CONTEXT_AFTER] outro"
            )
            == "intro Core text outro"
        )

    def test_chunk_embedding_text_example(self):
        assert (
            chunk_embedding_text(
                {
                    "text_raw": "Core",
                    "search_vector_payload": (
                        "[CONTEXT_BEFORE] ctx Core [CONTEXT_AFTER]"
                    ),
                }
            )
            == "ctx Core"
        )

    def test_stable_document_key_example(self):
        assert (
            len(stable_document_key("file://tests/indexing/input/doc.pdf"))
            == 32
        )

    def test_document_vespa_id_example(self):
        assert document_vespa_id(
            "file://doc.pdf", user_space="demo"
        ).startswith("id:default:tkeir_document:g=demo:")

    def test_chunk_vespa_id_example(self):
        assert chunk_vespa_id("doc.pdf#chunk-0", user_space="demo").startswith(
            "id:default:chunk:g=demo:"
        )

    def test_build_questions_tensor_example(self):
        assert build_questions_tensor([[0.1, 0.2]], embedding_dim=2) == {
            "0": [0.1, 0.2]
        }

    def test_build_chunk_tensor_example(self):
        assert build_chunk_tensor([1.0, 2.0, 3.0], embedding_dim=2) == [
            1.0,
            2.0,
        ]

    def test_escape_yql_literal_example(self):
        assert escape_yql_literal('say "hello"') == 'say \\"hello\\"'


class TestOntologyUtilsDocExamples:
    def test_merge_turtle_graphs_example(self):
        graph = merge_turtle_graphs(
            ["@prefix ex: <http://example.org/> .\nex:Alice a ex:Person ."]
        )
        assert len(graph) == 1

    def test_build_hmi_ontology_empty_example(self):
        assert build_hmi_ontology([], []) == {
            "entities": [],
            "keywords": [],
            "json_ld": "[]",
        }

    def test_summarize_graph_for_prompt_empty_example(self):
        from rdflib import Graph

        assert (
            summarize_graph_for_prompt(Graph(), "anything")
            == "No structured facts available."
        )

    def test_extract_relevant_triples_example(self):
        from rdflib import Graph, Literal, URIRef

        graph = Graph()
        alice = URIRef("http://example.org/Alice")
        graph.add(
            (alice, URIRef("http://example.org/type"), Literal("Person"))
        )
        lines = extract_relevant_triples(graph, "Alice")
        assert any("Alice" in line for line in lines)


class TestRagAppDocExamples:
    def test_unavailable_answer_example(self):
        assert (
            _unavailable_answer({"unavailable_answer": "N/A"}, "en") == "N/A"
        )

    def test_no_chunks_message_example(self):
        assert _no_chunks_message({}) == "No relevant chunks retrieved."

    def test_format_chunk_excerpts_empty_example(self):
        assert _format_chunk_excerpts([], empty_message="none") == "none"

    def test_parse_hits_example(self):
        parsed = _parse_hits(
            {
                "root": {
                    "children": [
                        {"fields": {"chunk_id": "c1"}, "relevance": 0.9}
                    ]
                }
            }
        )
        assert parsed == [({"chunk_id": "c1"}, 0.9)]


class TestLlmWrapperDocExamples:
    def test_wrapper_config_from_env_example(self, monkeypatch):
        monkeypatch.setenv("PROVIDER", "ollama")
        cfg = WrapperConfig.from_env(file_models={})
        assert cfg.provider is Provider.OLLAMA


class TestPipelineDocExamples:
    def test_is_tkeir_document_example(self):
        with tempfile.NamedTemporaryFile(
            "w", suffix=".json", delete=False
        ) as handle:
            json.dump({"content": ["hello"]}, handle)
            path = handle.name
        try:
            assert _is_tkeir_document(path)
        finally:
            os.unlink(path)

    def test_collect_inputs_example(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            open(
                os.path.join(temp_dir, "b.txt"), "w", encoding="utf-8"
            ).close()
            open(
                os.path.join(temp_dir, "a.txt"), "w", encoding="utf-8"
            ).close()
            paths = _collect_inputs(temp_dir)
            assert [os.path.basename(path) for path in paths] == [
                "a.txt",
                "b.txt",
            ]
