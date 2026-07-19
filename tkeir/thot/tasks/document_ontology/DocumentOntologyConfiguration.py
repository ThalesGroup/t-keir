"""Document ontology configuration."""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class DocumentOntologyConfiguration:
    """Load document ontology configuration."""

    def __init__(self):
        """Initialize an empty configuration holder.

        Example:
            >>> from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            ...     DocumentOntologyConfiguration,
            ... )
            >>> cfg = DocumentOntologyConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        self.configuration = dict()

    def load(self, config_f=None, path: list = []):
        """Load configuration from a JSON file path.

        Args:
            config_f: Path to the configuration file.
            path: Unused legacy parameter.

        Example:
            >>> from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            ...     DocumentOntologyConfiguration,
            ... )
            >>> callable(DocumentOntologyConfiguration().load)
            True
        """
        self.loads(load_configuration(config_f))

    def loads(self, configuration: dict | None = None):
        """Load configuration from a parsed dictionary.

        Args:
            configuration: Parsed JSON configuration.

        Raises:
            ValueError: If builders are missing.

        Example:
            >>> from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            ...     DocumentOntologyConfiguration,
            ... )
            >>> cfg = DocumentOntologyConfiguration()
            >>> cfg.loads({'document-ontology': {'builders': [{}]}})
            >>> 'builders' in cfg.configuration
            True
        """
        if configuration is None:
            raise ValueError("configuration is required")
        self.logger_config.loads(configuration, logger_name="ontology")
        if "builders" in configuration["document-ontology"]:
            self.configuration["builders"] = configuration[
                "document-ontology"
            ]["builders"]
        else:
            raise ValueError(
                "builders are mandatory in document-ontology configuration"
            )

    def clear(self):
        """Reset logger and task configuration.

        Example:
            >>> from thot.tasks.document_ontology.DocumentOntologyConfiguration import (
            ...     DocumentOntologyConfiguration,
            ... )
            >>> cfg = DocumentOntologyConfiguration()
            >>> cfg.loads({'document-ontology': {'builders': [{}]}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = dict()
