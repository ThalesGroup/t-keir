"""Title: Chunk Question Generator

Chunk-level synthetic question generation task.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tasks.chunk_questions import (
    __date_chunk_questions__,
    __version_chunk_questions__,
)
from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
    ChunkQuestionGeneratorConfiguration,
)
from thot.tasks.chunk_questions.QuestionBuilder import (
    QuestionGenerationSettings,
    enrich_golden_chunks_with_questions,
)
from thot.tasks.TaskInfo import TaskInfo


class ChunkQuestionGenerator:
    """Generate synthetic retrieval questions for golden chunks.

    Example:
        >>> from thot.tasks.chunk_questions.ChunkQuestionGenerator import ChunkQuestionGenerator
        >>> callable(ChunkQuestionGenerator)
        True
    """

    def __init__(
        self,
        config: ChunkQuestionGeneratorConfiguration | None = None,
        call_context=None,
    ):
        """Initialize the chunk question generator.

        Args:
            config: Chunk question generator configuration.
            call_context: Optional logging context.

        Raises:
            ValueError: If configuration is missing.

        Example:
            >>> from thot.tasks.chunk_questions.ChunkQuestionGenerator import ChunkQuestionGenerator
            >>> from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ...     ChunkQuestionGeneratorConfiguration,
            ... )
            >>> cfg = ChunkQuestionGeneratorConfiguration()
            >>> cfg.loads({'chunk-questions': {'generators': [{}]}})
            >>> isinstance(ChunkQuestionGenerator(cfg), ChunkQuestionGenerator)
            True
        """
        if not config:
            raise ValueError("chunk question configuration is mandatory")
        self._config = config
        generator_cfg = config.configuration["generators"][0]
        self._settings = QuestionGenerationSettings(
            min_questions=int(generator_cfg.get("min-questions", 3)),
            max_questions=int(generator_cfg.get("max-questions", 5)),
            enable_multilingual=bool(
                generator_cfg.get("enable-multilingual", True)
            ),
        )

    def generate(self, tkeir_doc: dict, call_context=None) -> dict:
        """Generate questions and attach them to golden chunks.

        Args:
            tkeir_doc: T-KEIR document with ``golden_chunks``.
            call_context: Optional logging context.

        Returns:
            Document with enriched chunks and task metadata.

        Raises:
            ValueError: If ``golden_chunks`` is missing.

        Example:
            >>> from thot.tasks.chunk_questions.ChunkQuestionGenerator import ChunkQuestionGenerator
            >>> from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ...     ChunkQuestionGeneratorConfiguration,
            ... )
            >>> cfg = ChunkQuestionGeneratorConfiguration()
            >>> cfg.loads({'chunk-questions': {'generators': [{}]}})
            >>> gen = ChunkQuestionGenerator(cfg)
            >>> doc = {
            ...     'golden_chunks': [{
            ...         'text_raw': 'Ada wrote code.',
            ...         'metadata': {'svo_triplets': [['Ada', 'wrote', 'code']], 'primary_entities': {}},
            ...     }],
            ... }
            >>> result = gen.generate(doc)
            >>> result['chunk_questions_ready']
            True
        """
        if "golden_chunks" not in tkeir_doc:
            raise ValueError(
                "Chunk question generation requires golden_chunks from chunking"
            )
        if not tkeir_doc["golden_chunks"]:
            tkeir_doc["chunk_questions_ready"] = True
            return tkeir_doc

        tkeir_doc["golden_chunks"] = enrich_golden_chunks_with_questions(
            tkeir_doc, settings=self._settings
        )
        tkeir_doc["chunk_questions_ready"] = True
        task_info = TaskInfo(
            task_name="chunk-questions",
            task_version=__version_chunk_questions__,
            task_date=__date_chunk_questions__,
        )
        return task_info.addInfo(tkeir_doc)

    def run(self, tkeir_doc: dict, call_context=None):
        """Run question generation on a T-KEIR document.

        Args:
            tkeir_doc: T-KEIR document with golden chunks.
            call_context: Optional logging context.

        Returns:
            Document enriched with synthetic questions.

        Example:
            >>> from thot.tasks.chunk_questions.ChunkQuestionGenerator import ChunkQuestionGenerator
            >>> from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
            ...     ChunkQuestionGeneratorConfiguration,
            ... )
            >>> cfg = ChunkQuestionGeneratorConfiguration()
            >>> cfg.loads({'chunk-questions': {'generators': [{}]}})
            >>> gen = ChunkQuestionGenerator(cfg)
            >>> callable(gen.run)
            True
        """
        return self.generate(tkeir_doc, call_context=call_context)
