"""Run the full T-KEIR NLP pipeline in process."""

import copy
import time
from datetime import UTC, datetime

from thot.core.ThotLogger import ThotLogger
from thot.tasks.chunk_questions.ChunkQuestionGenerator import (
    ChunkQuestionGenerator,
)
from thot.tasks.converters.Converter import Converter
from thot.tasks.document_ontology.DocumentOntologyBuilder import (
    DocumentOntologyBuilder,
)
from thot.tasks.golden_chunking.GoldenChunker import GoldenChunker
from thot.tasks.keywords.KeywordsExtractor import KeywordsExtractor
from thot.tasks.language_detection.LanguageDetector import LanguageDetector
from thot.tasks.morphosyntax.MorphoSyntacticTagger import MorphoSyntacticTagger
from thot.tasks.ner.NERTagger import NERTagger
from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
from thot.tasks.pipeline.PipelineSummary import annotate_pipeline_summary
from thot.tasks.pipeline.PipelineTasks import (
    expand_tasks,
    needs_language_setup,
    task_output_present,
)
from thot.tasks.pipeline.ResourceSelector import ResourceSelector
from thot.tasks.syntax.SyntacticTagger import SyntacticTagger
from thot.tasks.tokenizer.Tokenizer import Tokenizer


class PipelineRunner:
    def __init__(self, config: PipelineConfiguration):
        """Create a pipeline runner bound to a configuration.

        Args:
            config: Loaded ``PipelineConfiguration`` instance.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._converter is None
            True
        """
        self.config = config
        self._converter = None
        self._tokenizer = None
        self._morphosyntax = None
        self._ner = None
        self._syntax = None
        self._keywords = None
        self._chunking = None
        self._ontology = None
        self._chunk_questions = None
        self._active_language_key: tuple[str, str] | None = None

    def _reset_tasks(self):
        """Clear lazily initialized NLP task instances.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._tokenizer = object()
            >>> runner._reset_tasks()
            >>> runner._tokenizer is None
            True
        """
        self._tokenizer = None
        self._morphosyntax = None
        self._ner = None
        self._syntax = None
        self._keywords = None
        self._chunking = None
        self._ontology = None
        self._chunk_questions = None

    def _get_converter(self):
        """Return the lazily initialized converter task.

        Returns:
            Shared ``Converter`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._converter is None
            True
        """
        if not self._converter:
            self._converter = Converter(self.config.task_configs["converter"])
        return self._converter

    def _get_tokenizer(self, call_context=None):
        """Return the lazily initialized tokenizer task.

        Args:
            call_context: Optional logger context.

        Returns:
            Shared ``Tokenizer`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._tokenizer is None
            True
        """
        if not self._tokenizer:
            self._tokenizer = Tokenizer(
                config=self.config.task_configs["tokenizer"],
                call_context=call_context,
            )
        return self._tokenizer

    def _get_morphosyntax(self, call_context=None):
        """Return the lazily initialized morphosyntax task.

        Args:
            call_context: Optional logger context.

        Returns:
            Shared ``MorphoSyntacticTagger`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._morphosyntax is None
            True
        """
        if not self._morphosyntax:
            self._morphosyntax = MorphoSyntacticTagger(
                config=self.config.task_configs["morphosyntax"],
                call_context=call_context,
            )
        return self._morphosyntax

    def _get_ner(self, call_context=None):
        """Return the lazily initialized NER task.

        Args:
            call_context: Optional logger context.

        Returns:
            Shared ``NERTagger`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._ner is None
            True
        """
        if not self._ner:
            self._ner = NERTagger(
                config=self.config.task_configs["ner"],
                call_context=call_context,
            )
        return self._ner

    def _get_syntax(self):
        """Return the lazily initialized syntactic tagger task.

        Returns:
            Shared ``SyntacticTagger`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._syntax is None
            True
        """
        if not self._syntax:
            self._syntax = SyntacticTagger(
                config=self.config.task_configs["syntax"],
            )
        return self._syntax

    def _get_keywords(self, call_context=None):
        """Return the lazily initialized keywords extractor task.

        Args:
            call_context: Optional logger context.

        Returns:
            Shared ``KeywordsExtractor`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._keywords is None
            True
        """
        if not self._keywords:
            self._keywords = KeywordsExtractor(
                config=self.config.task_configs["keywords"],
                call_context=call_context,
            )
        return self._keywords

    def _get_chunking(self, call_context=None):
        """Return the lazily initialized golden chunker task.

        Args:
            call_context: Optional logger context.

        Returns:
            Shared ``GoldenChunker`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._chunking is None
            True
        """
        if not self._chunking:
            self._chunking = GoldenChunker(
                config=self.config.task_configs["chunking"],
                call_context=call_context,
            )
        return self._chunking

    def _get_ontology(self, call_context=None):
        """Return the lazily initialized document ontology task.

        Args:
            call_context: Optional logger context.

        Returns:
            Shared ``DocumentOntologyBuilder`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._ontology is None
            True
        """
        if not self._ontology:
            self._ontology = DocumentOntologyBuilder(
                config=self.config.task_configs["ontology"],
                call_context=call_context,
            )
        return self._ontology

    def _get_chunk_questions(self, call_context=None):
        """Return the lazily initialized chunk-questions task.

        Args:
            call_context: Optional logger context.

        Returns:
            Shared ``ChunkQuestionGenerator`` instance for this runner.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> runner._chunk_questions is None
            True
        """
        if not self._chunk_questions:
            self._chunk_questions = ChunkQuestionGenerator(
                config=self.config.task_configs["chunk-questions"],
                call_context=call_context,
            )
        return self._chunk_questions

    @staticmethod
    def _input_file_label(document: dict, call_context=None) -> str:
        """Resolve a human-readable input file label for logging.

        Args:
            document: Pipeline document dictionary.
            call_context: Optional call context with ``input-file``.

        Returns:
            Input file path or fallback label.

        Example:
            >>> PipelineRunner._input_file_label({"source": "file:///tmp/a.txt"})
            '/tmp/a.txt'
        """
        if call_context and call_context.get("input-file"):
            return call_context["input-file"]
        source = document.get("source") or document.get("source_doc_id") or ""
        if isinstance(source, str) and source.startswith("file://"):
            return source[len("file://") :]
        return source or "unknown"

    def _run_timed_step(
        self,
        step_name: str,
        input_file: str,
        call_context,
        action,
        step_timings: dict[str, float],
    ):
        """Execute one pipeline step and record elapsed time.

        Args:
            step_name: Task name used in logs and timings.
            input_file: Input file label for logs.
            call_context: Optional logger context.
            action: Callable that performs the step.
            step_timings: Mutable timing map updated in place.

        Returns:
            Value returned by ``action``.

        Example:
            >>> PipelineRunner._run_timed_step.__name__
            '_run_timed_step'
        """
        started_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        start = time.perf_counter()
        ThotLogger.info(
            "Pipeline task '"
            + step_name
            + "' started for "
            + input_file
            + " at "
            + started_at,
            context=call_context,
        )
        try:
            return action()
        finally:
            elapsed = time.perf_counter() - start
            step_timings[step_name] = elapsed
            ThotLogger.info(
                "Pipeline task '"
                + step_name
                + "' finished for "
                + input_file
                + " elapsed="
                + f"{elapsed:.3f}s",
                context=call_context,
            )

    def _run_if_missing(
        self,
        result: dict,
        tasks_to_run: list[str],
        task_name: str,
        input_file: str,
        call_context,
        step_timings: dict[str, float],
        action,
    ) -> dict:
        """Run a task when scheduled and its output is not already present.

        Args:
            result: Current pipeline document.
            tasks_to_run: Scheduled task names.
            task_name: Task to conditionally execute.
            input_file: Input file label for logs.
            call_context: Optional logger context.
            step_timings: Mutable timing map updated in place.
            action: Callable that performs the task.

        Returns:
            Updated pipeline document.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> doc = {"content_tokens": []}
            >>> runner._run_if_missing(
            ...     doc, ["tokenizer"], "tokenizer", "a.txt", None, {}, lambda: doc
            ... ) is doc
            True
        """
        if task_name not in tasks_to_run or task_output_present(
            result, task_name
        ):
            return result
        return self._run_timed_step(
            task_name, input_file, call_context, action, step_timings
        )

    def _apply_language_setup(
        self,
        result: dict,
        tasks_to_run: list[str],
        input_file: str,
        call_context,
        step_timings: dict[str, float],
    ) -> dict:
        """Detect language and apply resource selection when NLP tasks run.

        Args:
            result: Current pipeline document.
            tasks_to_run: Scheduled task names.
            input_file: Input file label for logs.
            call_context: Optional logger context.
            step_timings: Mutable timing map updated in place.

        Returns:
            Document annotated with language and resource metadata.

        Example:
            >>> runner = PipelineRunner(PipelineConfiguration())
            >>> doc = {"content": ["sample text"]}
            >>> out = runner._apply_language_setup(
            ...     doc, ["converter"], "a.txt", None, {}
            ... )
            >>> out is doc
            True
        """
        if not needs_language_setup(tasks_to_run):
            return result

        if "language-detection" not in result:
            result = self._run_timed_step(
                "language-detection",
                input_file,
                call_context,
                lambda: LanguageDetector.detect_document(
                    result, call_context=call_context
                ),
                step_timings,
            )

        detected_language = result["language-detection"]["language"]
        if "resource-selection" not in result:
            result = self._run_timed_step(
                "resource-selection",
                input_file,
                call_context,
                lambda: ResourceSelector.annotate_document(
                    result,
                    detected_language,
                    default_language=self.config.configuration[
                        "default-language"
                    ],
                    call_context=call_context,
                ),
                step_timings,
            )

        selection = result["resource-selection"]
        detected_language = result["language-detection"]["language"]
        model_language = selection.get("spacy-language", detected_language)
        language_key = (
            selection["processing-language"],
            model_language,
        )
        if language_key != self._active_language_key:
            self._reset_tasks()
            self._active_language_key = language_key
        self.config.apply_language(
            selection["processing-language"],
            selection["resources-base-path"],
            spacy_language=model_language,
        )
        return result

    def run(
        self,
        document: dict,
        call_context=None,
        skip_converter: bool = False,
        tasks: list[str] | None = None,
    ) -> dict:
        """Run pipeline tasks on a document in dependency order.

        Args:
            document: Input or partially processed pipeline document.
            call_context: Optional logger context.
            skip_converter: When ``True``, omit the converter step.
            tasks: Optional explicit task subset.

        Returns:
            Document enriched with requested task outputs and summary metadata.

        Raises:
            ValueError: When converter input fields are missing.

        Example:
            >>> doc = {"content": ["already converted text"]}
            >>> out = PipelineRunner(PipelineConfiguration()).run(
            ...     doc, skip_converter=True, tasks=[]
            ... )
            >>> out["content"]
            ['already converted text']
        """
        result = copy.deepcopy(document)
        tasks_to_run = expand_tasks(tasks, skip_converter=skip_converter)
        input_file = self._input_file_label(result, call_context)
        step_timings: dict[str, float] = {}

        if "converter" in tasks_to_run and not task_output_present(
            result, "converter"
        ):
            if not all(
                key in result for key in ("datatype", "data", "source")
            ):
                raise ValueError(
                    "converter input requires datatype, data and source"
                )

            def _convert():
                return self._get_converter().convert(
                    data_type=result["datatype"],
                    data=result["data"],
                    source=result["source"],
                    call_context=call_context,
                )

            result = self._run_timed_step(
                "converter", input_file, call_context, _convert, step_timings
            )

        result = self._apply_language_setup(
            result, tasks_to_run, input_file, call_context, step_timings
        )

        result = self._run_if_missing(
            result,
            tasks_to_run,
            "tokenizer",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_tokenizer(call_context).run(
                result, call_context=call_context
            ),
        )
        result = self._run_if_missing(
            result,
            tasks_to_run,
            "morphosyntax",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_morphosyntax(call_context).run(result),
        )
        result = self._run_if_missing(
            result,
            tasks_to_run,
            "ner",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_ner(call_context).run(result),
        )
        result = self._run_if_missing(
            result,
            tasks_to_run,
            "syntax",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_syntax().run(result),
        )
        result = self._run_if_missing(
            result,
            tasks_to_run,
            "keywords",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_keywords(call_context).run(result),
        )
        result = self._run_if_missing(
            result,
            tasks_to_run,
            "chunking",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_chunking(call_context).run(result),
        )
        result = self._run_if_missing(
            result,
            tasks_to_run,
            "ontology",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_ontology(call_context).run(result),
        )
        result = self._run_if_missing(
            result,
            tasks_to_run,
            "chunk-questions",
            input_file,
            call_context,
            step_timings,
            lambda: self._get_chunk_questions(call_context).run(result),
        )
        return annotate_pipeline_summary(result, call_context, step_timings)

    def run_converted(
        self,
        document: dict,
        call_context=None,
        tasks: list[str] | None = None,
    ) -> dict:
        """Run the pipeline on an already converted document.

        Args:
            document: Converted pipeline document.
            call_context: Optional logger context.
            tasks: Optional explicit task subset.

        Returns:
            Document enriched with requested task outputs and summary metadata.

        Example:
            >>> doc = {"content": ["converted text"]}
            >>> out = PipelineRunner(PipelineConfiguration()).run_converted(
            ...     doc, tasks=[]
            ... )
            >>> out["content"]
            ['converted text']
        """
        return self.run(
            document,
            call_context=call_context,
            skip_converter=True,
            tasks=tasks,
        )
