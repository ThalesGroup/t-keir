"""Title: Golden Chunker

Golden chunking task for hierarchical indexing.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.tasks.golden_chunking import (
    __date_golden_chunking__,
    __version_golden_chunking__,
)
from thot.tasks.golden_chunking.ChunkBuilder import (
    ChunkSettings,
    build_golden_chunks,
)
from thot.tasks.golden_chunking.GoldenChunkerConfiguration import (
    GoldenChunkerConfiguration,
)
from thot.tasks.TaskInfo import TaskInfo


class GoldenChunker:
    """GoldenChunker container.

    Example:
        >>> from thot.tasks.golden_chunking.GoldenChunker import GoldenChunker
        >>> callable(GoldenChunker)
        True
    """

    def __init__(
        self,
        config: GoldenChunkerConfiguration | None = None,
        call_context=None,
    ):
        """Initialize the instance.

        Example:
            >>> callable(GoldenChunker)
            True
        """
        if not config:
            raise ValueError("golden chunking configuration is mandatory")
        self._config = config
        chunker_cfg = config.configuration["chunkers"][0]
        self._settings = ChunkSettings(
            target_min_tokens=int(chunker_cfg.get("target-min-tokens", 300)),
            target_max_tokens=int(chunker_cfg.get("target-max-tokens", 500)),
            high_ner_density_max_tokens=int(
                chunker_cfg.get("high-ner-density-max-tokens", 250)
            ),
            ner_density_threshold=int(
                chunker_cfg.get("ner-density-threshold", 3)
            ),
        )

    def chunk(self, tkeir_doc: dict) -> dict:
        """Run the chunk task step on a T-KEIR document.

        Example:
            >>> callable(GoldenChunker.chunk)
            True
        """
        required = (
            "content_morphosyntax",
            "content_ner",
            "content_deps",
        )
        missing = [field for field in required if field not in tkeir_doc]
        if missing:
            raise ValueError(
                "Golden chunking requires analyzed document fields: "
                + ", ".join(missing)
            )

        tkeir_doc["golden_chunks"] = build_golden_chunks(
            tkeir_doc, settings=self._settings
        )
        task_info = TaskInfo(
            task_name="golden-chunking",
            task_version=__version_golden_chunking__,
            task_date=__date_golden_chunking__,
        )
        return task_info.addInfo(tkeir_doc)

    def run(self, tkeir_doc: dict, call_context=None):
        """Run the run task step on a T-KEIR document.

        Example:
            >>> callable(GoldenChunker.run)
            True
        """
        return self.chunk(tkeir_doc)
