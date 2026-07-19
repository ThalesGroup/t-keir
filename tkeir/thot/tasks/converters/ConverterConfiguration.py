"""Converter configuration."""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class ConverterConfiguration:
    def __init__(self):
        """Initialize empty converter configuration holders.

        Example:
            >>> cfg = ConverterConfiguration()
            >>> cfg.configuration
            {}
        """
        self.logger_config = LoggerConfiguration()
        self.configuration = {}

    def load(self, config_f=None, path: list = []):
        """Load converter configuration from a YAML/JSON file handle.

        Args:
            config_f: Open file-like object containing YAML or JSON.
            path: Unused legacy parameter kept for API compatibility.

        Example:
            >>> cfg = ConverterConfiguration()
            >>> isinstance(cfg.load, type(cfg.loads))
            True
        """
        self.loads(load_configuration(config_f))

    def loads(self, configuration: dict | None = None):
        """Load converter configuration from a dictionary.

        Args:
            configuration: Parsed converter JSON configuration.

        Raises:
            ValueError: When configuration is missing.

        Example:
            >>> cfg = ConverterConfiguration()
            >>> cfg.loads({"logger": {}, "converter": {"settings": {}}})
            >>> cfg.configuration["settings"]["ocr"]["enabled"]
            False
        """
        if not configuration:
            raise ValueError("Converter configuration is mandatory")
        self.logger_config.loads(configuration, logger_name="converter")
        settings = configuration["converter"].get("settings", {})
        output = settings.get("output", {})
        ocr = settings.get("ocr", {})
        configuration["converter"]["settings"] = {
            "output": {"zip": output.get("zip", False)},
            "ocr": {
                "enabled": ocr.get("enabled", False),
                "mode": ocr.get("mode", "tesseract"),
                "min-image-pixels": ocr.get("min-image-pixels", 10000),
                "min-page-text-chars": ocr.get("min-page-text-chars", 40),
                "render-dpi": ocr.get("render-dpi", 200),
                "llm-model": ocr.get("llm-model"),
                "llm-base-url": ocr.get("llm-base-url"),
                "llm-api-key": ocr.get("llm-api-key"),
                "llm-prompt": ocr.get("llm-prompt"),
            },
        }
        self.configuration = configuration["converter"]

    def clear(self):
        """Reset logger and converter configuration state.

        Example:
            >>> cfg = ConverterConfiguration()
            >>> cfg.loads({"logger": {}, "converter": {"settings": {}}})
            >>> cfg.clear()
            >>> cfg.configuration
            {}
        """
        self.logger_config.clear()
        self.configuration = {}
