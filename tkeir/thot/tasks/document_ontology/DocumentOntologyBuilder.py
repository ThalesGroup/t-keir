# -*- coding: utf-8 -*-
"""Document ontology pipeline task."""

from thot.core.KeywordRules import DEFAULT_MIN_KEYWORD_LENGTH
from thot.core.ThotLogger import ThotLogger
from thot.tasks.document_ontology import (
    __date_document_ontology__,
    __version_document_ontology__,
)
from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
    DocumentOntologyConfiguration,
)
from thot.tasks.document_ontology.OntologyAlignment import (
    AlignmentSettings,
    align_document_graph,
    build_document_vocabulary,
    merge_alignment_reports,
)
from thot.tasks.document_ontology.OntologyBuilder import (
    OntologyBuildSettings,
    build_document_graph,
    compute_ontology_text_coverage,
)
from thot.tasks.document_ontology.SelfHealingLoop import (
    SelfHealingSettings,
    run_self_healing_validation,
)
from thot.tasks.document_ontology.ShaclInductor import (
    induce_document_shacl_shapes,
)
from thot.tasks.TaskInfo import TaskInfo
from thot.tools.search.ontology_utils import serialize_graph_json_ld


class DocumentOntologyBuilder:
    """Build and validate RDF document ontologies from T-KEIR analysis."""

    def __init__(
        self,
        config: DocumentOntologyConfiguration | None = None,
        call_context=None,
    ):
        """Initialize the document ontology builder.

        Args:
            config: Document ontology configuration.
            call_context: Optional logging context.

        Raises:
            ValueError: If configuration is missing.

        Example:
            >>> from thot.tasks.document_ontology.DocumentOntologyBuilder import DocumentOntologyBuilder
            >>> from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            ...     DocumentOntologyConfiguration,
            ... )
            >>> cfg = DocumentOntologyConfiguration()
            >>> cfg.loads({'document-ontology': {'builders': [{}]}})
            >>> isinstance(DocumentOntologyBuilder(cfg), DocumentOntologyBuilder)
            True
        """
        if not config:
            raise ValueError("document ontology configuration is mandatory")
        self._config = config
        builder_cfg = config.configuration["builders"][0]
        self._settings = OntologyBuildSettings(
            include_title_triples=bool(
                builder_cfg.get("include-title-triples", True)
            ),
            include_content_triples=bool(
                builder_cfg.get("include-content-triples", True)
            ),
            min_keyword_length=max(
                1,
                int(
                    builder_cfg.get(
                        "min-keyword-length",
                        DEFAULT_MIN_KEYWORD_LENGTH,
                    )
                ),
            ),
        )
        self._healing_settings = SelfHealingSettings(
            max_repair_attempts=int(builder_cfg.get("max-repair-attempts", 2)),
        )
        alignment_cfg = builder_cfg.get("alignment") or {}
        if not isinstance(alignment_cfg, dict):
            alignment_cfg = {}
        self._alignment_settings = AlignmentSettings(
            enabled=bool(alignment_cfg.get("enabled", True)),
            similarity_threshold=float(
                alignment_cfg.get(
                    "similarity-threshold",
                    alignment_cfg.get("similarity_threshold", 0.85),
                )
            ),
            min_cluster_size=max(
                2,
                int(
                    alignment_cfg.get(
                        "min-cluster-size",
                        alignment_cfg.get("min_cluster_size", 2),
                    )
                ),
            ),
        )
        self._save_alignment = bool(
            builder_cfg.get(
                "save-alignment",
                builder_cfg.get("save_alignment", False),
            )
        )

    def build(self, tkeir_doc: dict, call_context=None) -> dict:
        """Build, validate, and serialize the document ontology.

        Args:
            tkeir_doc: Analyzed T-KEIR document with ``kg``.
            call_context: Optional logging context.

        Returns:
            Document with ``document_ontology`` metadata.

        Raises:
            ValueError: If required analyzed fields are missing.

        Example:
            >>> from thot.tasks.document_ontology.DocumentOntologyBuilder import DocumentOntologyBuilder
            >>> from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            ...     DocumentOntologyConfiguration,
            ... )
            >>> cfg = DocumentOntologyConfiguration()
            >>> cfg.loads({'document-ontology': {'builders': [{}]}})
            >>> builder = DocumentOntologyBuilder(cfg)
            >>> doc = {
            ...     'kg': [],
            ...     'content_morphosyntax': [],
            ...     'content_ner': [],
            ...     'content_deps': [],
            ... }
            >>> result = builder.build(doc)
            >>> 'document_ontology' in result
            True
        """
        required = ("kg",)
        missing = [field for field in required if field not in tkeir_doc]
        if missing:
            raise ValueError(
                "Document ontology requires analyzed document fields: "
                + ", ".join(missing)
            )

        vocabulary, vocabulary_report = build_document_vocabulary(
            tkeir_doc,
            settings=self._alignment_settings,
            call_context=call_context,
        )
        graph = build_document_graph(
            tkeir_doc,
            settings=self._settings,
            vocabulary=vocabulary,
        )
        graph, graph_alignment_report = align_document_graph(
            graph,
            settings=self._alignment_settings,
            call_context=call_context,
        )
        alignment_report = merge_alignment_reports(
            vocabulary_report,
            graph_alignment_report,
        )
        shapes_ttl = induce_document_shacl_shapes(graph, alignment_report)
        text_coverage = compute_ontology_text_coverage(
            tkeir_doc,
            settings=self._settings,
        )
        graph, shacl_status, correction_attempts, incoherence_summary = (
            run_self_healing_validation(
                graph,
                settings=self._healing_settings,
                shapes_ttl=shapes_ttl,
                call_context=call_context,
            )
        )

        if shacl_status == "FAILED_WITH_INCOHERENCES":
            ThotLogger.info(
                "Document ontology SHACL validation still failing after "
                + str(correction_attempts)
                + " repair attempt(s); "
                + str(incoherence_summary.get("unresolved", 0))
                + " unresolved incoherence(s).",
                context=call_context,
            )
        elif shacl_status == "PASSED_AFTER_REPAIR":
            ThotLogger.info(
                "Document ontology SHACL validation passed after "
                + str(correction_attempts)
                + " repair attempt(s).",
                context=call_context,
            )

        document_ontology: dict[str, object] = {
            "json_ld": serialize_graph_json_ld(graph),
            "shacl_status": shacl_status,
            "correction_attempts": correction_attempts,
            "incoherences": incoherence_summary,
            **text_coverage,
        }
        if self._save_alignment:
            document_ontology["alignment"] = alignment_report
        tkeir_doc["document_ontology"] = document_ontology
        task_info = TaskInfo(
            task_name="document-ontology",
            task_version=__version_document_ontology__,
            task_date=__date_document_ontology__,
        )
        return task_info.addInfo(tkeir_doc)

    def run(self, tkeir_doc: dict, call_context=None):
        """Run ontology building on a T-KEIR document.

        Args:
            tkeir_doc: Analyzed T-KEIR document.
            call_context: Optional logging context.

        Returns:
            Document enriched with ontology metadata.

        Example:
            >>> from thot.tasks.document_ontology.DocumentOntologyBuilder import DocumentOntologyBuilder
            >>> from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            ...     DocumentOntologyConfiguration,
            ... )
            >>> cfg = DocumentOntologyConfiguration()
            >>> cfg.loads({'document-ontology': {'builders': [{}]}})
            >>> builder = DocumentOntologyBuilder(cfg)
            >>> callable(builder.run)
            True
        """
        return self.build(tkeir_doc, call_context=call_context)
