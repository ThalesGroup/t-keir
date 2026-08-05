"""Title: Pipeline Configuration

Pipeline configuration loader.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.ConfigurationUtils import (
    load_configuration,
    resolve_config_path,
)
from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.TkeirPaths import (
    configs_dir,
    effective_resources_path,
)
from thot.core.Utils import apply_use_mwe_to_entries
from thot.tasks.chunk_questions.ChunkQuestionGeneratorConfiguration import (
    ChunkQuestionGeneratorConfiguration,
)
from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration
from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
    DocumentOntologyConfiguration,
)
from thot.tasks.golden_chunking.GoldenChunkerConfiguration import (
    GoldenChunkerConfiguration,
)
from thot.tasks.keywords.KeywordsConfiguration import KeywordsConfiguration
from thot.tasks.morphosyntax.MorphoSyntacticTaggerConfiguration import (
    MorphoSyntacticTaggerConfiguration,
)
from thot.tasks.ner.NERTaggerConfiguration import NERTaggerConfiguration
from thot.tasks.pipeline.ResourceSelector import ResourceSelector
from thot.tasks.syntax.SyntacticTaggerConfiguration import (
    SyntacticTaggerConfiguration,
)
from thot.tasks.tokenizer.TokenizerConfiguration import TokenizerConfiguration


class PipelineConfiguration:
    """PipelineConfiguration container.

    Example:
        >>> from thot.tasks.pipeline.PipelineConfiguration import PipelineConfiguration
        >>> callable(PipelineConfiguration)
        True
    """

    TASK_CONFIG_CLASSES = {
        "converter": ConverterConfiguration,
        "tokenizer": TokenizerConfiguration,
        "morphosyntax": MorphoSyntacticTaggerConfiguration,
        "ner": NERTaggerConfiguration,
        "syntax": SyntacticTaggerConfiguration,
        "keywords": KeywordsConfiguration,
        "chunking": GoldenChunkerConfiguration,
        "ontology": DocumentOntologyConfiguration,
        "chunk-questions": ChunkQuestionGeneratorConfiguration,
    }

    def __init__(self):
        """Initialize empty pipeline configuration holders.

        Example:
            >>> cfg = PipelineConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        self.configuration = {}
        self.task_configs = {}

    def load(self, config_f):
        """Load pipeline configuration from a YAML/JSON file handle.

        Args:
            config_f: Open file-like object containing YAML or JSON.

        Example:
            >>> cfg = PipelineConfiguration()
            >>> isinstance(cfg.load, type(cfg.loads))
            True
        """
        self.loads(load_configuration(config_f))

    def loads(self, configuration: dict):
        """Load pipeline configuration from a dictionary.

        Args:
            configuration: Parsed pipeline configuration.

        Example:
            >>> cfg = PipelineConfiguration()
            >>> cfg.loads({"logger": {}, "pipeline": {"default-language": "fr"}})
            >>> cfg.configuration["default-language"]
            'fr'
        """
        self.logger_config.loads(configuration, logger_name="pipeline")
        pipeline = configuration["pipeline"]
        self.configuration = {
            "default-language": pipeline.get("default-language", "en"),
            "configs": pipeline.get("configs", {}),
        }
        self.task_configs = {}
        for task_name, config_path in self.configuration["configs"].items():
            self.task_configs[task_name] = self._load_task_config(
                task_name, config_path
            )

    def _load_task_config(self, task_name: str, config_path: str):
        """Load one task configuration file referenced by the pipeline.

        Args:
            task_name: Pipeline task name.
            config_path: Path to the task YAML/JSON configuration.

        Returns:
            Loaded task configuration object.

        Raises:
            ValueError: When the task name is unsupported.

        Example:
            >>> cfg = PipelineConfiguration()
            >>> try:
            ...     cfg._load_task_config("unknown-task", "missing.json")
            ... except ValueError as exc:
            ...     "Unsupported" in str(exc)
            ... else:
            ...     False
            True
        """
        if task_name not in self.TASK_CONFIG_CLASSES:
            raise ValueError("Unsupported pipeline task: " + task_name)
        resolved = resolve_config_path(config_path, search_dir=configs_dir())
        config = self.TASK_CONFIG_CLASSES[task_name]()
        with open(resolved, encoding="utf-8") as handle:
            config.load(handle)  # type: ignore[attr-defined]
        return config

    def apply_language(
        self,
        language: str,
        resource_path: str | None,
        spacy_language: str | None = None,
    ):
        """Apply language and resource paths to NLP task configurations.

        Args:
            language: Processing language for lexical resources.
            resource_path: Base path to language resources, if any.
            spacy_language: Optional spaCy model language override.

        Example:
            >>> cfg = PipelineConfiguration()
            >>> cfg.task_configs = {
            ...     "tokenizer": type("T", (), {"configuration": {"segmenters": [{}]}})(),
            ...     "morphosyntax": type("M", (), {"configuration": {"taggers": [{}]}})(),
            ...     "ner": type("N", (), {"configuration": {"label": [{}]}})(),
            ...     "syntax": type("S", (), {"configuration": {"taggers": [{}]}})(),
            ...     "keywords": type("K", (), {"configuration": {"extractors": [{}]}})(),
            ... }
            >>> cfg.apply_language("en", None, spacy_language="de")
            >>> cfg.task_configs["tokenizer"].configuration["segmenters"][0]["language"]
            'de'
        """
        model_language = spacy_language or language
        resource_path = effective_resources_path(
            resource_path or ResourceSelector.select(language),
            language,
        )
        if resource_path:
            self._set_language_field(
                self.task_configs["tokenizer"].configuration,
                "segmenters",
                model_language,
                resource_path,
            )
            self._set_language_field(
                self.task_configs["morphosyntax"].configuration,
                "taggers",
                model_language,
                resource_path,
            )
            self._set_language_field(
                self.task_configs["ner"].configuration,
                "label",
                model_language,
                resource_path,
            )
            self._set_language_field(
                self.task_configs["syntax"].configuration,
                "taggers",
                model_language,
                resource_path,
            )
            self._set_language_field(
                self.task_configs["keywords"].configuration,
                "extractors",
                language,
                resource_path,
            )
        else:
            self._set_language_only(
                self.task_configs["tokenizer"].configuration,
                "segmenters",
                model_language,
            )
            self._set_language_only(
                self.task_configs["morphosyntax"].configuration,
                "taggers",
                model_language,
            )
            self._set_language_only(
                self.task_configs["ner"].configuration,
                "label",
                model_language,
            )
            self._set_language_only(
                self.task_configs["syntax"].configuration,
                "taggers",
                model_language,
            )
            self._set_language_only(
                self.task_configs["keywords"].configuration,
                "extractors",
                language,
            )

    def apply_use_mwe(self, use_mwe: bool) -> None:
        """Enable or disable MWE across NLP tasks that support it.

        Args:
            use_mwe: When ``True``, enable multi-word expression handling.

        Example:
            >>> cfg = PipelineConfiguration()
            >>> cfg.task_configs = {
            ...     "tokenizer": type("T", (), {"configuration": {"segmenters": [{}]}})(),
            ...     "morphosyntax": type("M", (), {"configuration": {"taggers": [{}]}})(),
            ...     "ner": type("N", (), {"configuration": {"label": [{}]}})(),
            ...     "syntax": type("S", (), {"configuration": {"taggers": [{}]}})(),
            ... }
            >>> cfg.apply_use_mwe(True)
            >>> cfg.task_configs["tokenizer"].configuration["segmenters"][0]["use-mwe"]
            True
        """
        apply_use_mwe_to_entries(
            self.task_configs["tokenizer"].configuration["segmenters"],
            use_mwe,
        )
        apply_use_mwe_to_entries(
            self.task_configs["morphosyntax"].configuration["taggers"],
            use_mwe,
        )
        apply_use_mwe_to_entries(
            self.task_configs["ner"].configuration["label"],
            use_mwe,
        )
        apply_use_mwe_to_entries(
            self.task_configs["syntax"].configuration["taggers"],
            use_mwe,
        )

    @staticmethod
    def _set_language_field(configuration, key, language, resource_path):
        """Set language and resource path on each configuration entry.

        Args:
            configuration: Task configuration mapping.
            key: Entry list key to update.
            language: Language code to apply.
            resource_path: Resource base path to apply.

        Example:
            >>> cfg = {"segmenters": [{"language": "fr"}]}
            >>> PipelineConfiguration._set_language_field(
            ...     cfg, "segmenters", "en", "/resources/en"
            ... )
            >>> cfg["segmenters"][0]["resources-base-path"]
            '/resources/en'
        """
        for item in configuration[key]:
            item["language"] = language
            item["resources-base-path"] = resource_path

    @staticmethod
    def _set_language_only(configuration, key, language):
        """Set only the language field on each configuration entry.

        Args:
            configuration: Task configuration mapping.
            key: Entry list key to update.
            language: Language code to apply.

        Example:
            >>> cfg = {"taggers": [{"language": "fr"}]}
            >>> PipelineConfiguration._set_language_only(cfg, "taggers", "en")
            >>> cfg["taggers"][0]["language"]
            'en'
        """
        for item in configuration[key]:
            item["language"] = language
