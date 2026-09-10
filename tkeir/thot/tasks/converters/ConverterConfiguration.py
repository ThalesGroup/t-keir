"""Title: Converter Configuration

Converter configuration.

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

from thot.core.ConfigurationUtils import load_configuration
from thot.core.LoggerConfiguration import LoggerConfiguration


class ConverterConfiguration:
    """ConverterConfiguration container.

    Example:
        >>> from thot.tasks.converters.ConverterConfiguration import ConverterConfiguration
        >>> callable(ConverterConfiguration)
        True
    """

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
            True
            >>> cfg.configuration["settings"]["ocr"]["captions"]
            True
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
                "enabled": ocr.get("enabled", True),
                "mode": ocr.get("mode", "tesseract"),
                "analyze-images": ocr.get("analyze-images", True),
                "captions": ocr.get("captions", ocr.get("blip", True)),
                "min-image-pixels": ocr.get("min-image-pixels", 256 * 256),
                "min-page-text-chars": ocr.get("min-page-text-chars", 40),
                "render-dpi": ocr.get("render-dpi", 200),
                "llm-model": ocr.get("llm-model"),
                "llm-base-url": ocr.get("llm-base-url"),
                "llm-api-key": ocr.get("llm-api-key"),
                "llm-prompt": ocr.get("llm-prompt"),
                "languages": ocr.get(
                    "languages",
                    "eng+fra+deu+spa+ita+nld+por+pol+ara",
                ),
                "max-embedded-images": ocr.get(
                    "max-embedded-images", 256
                ),
                "max-pdf-images-per-page": ocr.get(
                    "max-pdf-images-per-page", 32
                ),
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
