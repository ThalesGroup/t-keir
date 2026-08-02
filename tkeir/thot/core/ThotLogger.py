"""Title: Logger of library

Core T-KEIR libraries (logging, config, paths, utilities).

Author: Eric Blaudez

Copyright (c) 2026 Thales
Licensed under the MIT License.
"""

import logging
import sys
from time import gmtime, strftime

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.StructuredLogging import CorrelationIdFilter, TkeirTextFormatter
from thot.core.ThotMetrics import ThotMetrics

try:
    from thot.action.correlation import current_correlation_id
except Exception:  # noqa: BLE001 — keep logger usable before action package

    def current_correlation_id() -> str | None:
        return None


class LogUserContext(dict):
    """Dictionary-backed logging context for a single user request."""

    def __init__(self, correlation_id: str):
        """Initialize logger context with a correlation id.

        Args:
            correlation_id: Identifier used to correlate log lines.

        Example:
            >>> from thot.core.ThotLogger import LogUserContext
            >>> ctx = LogUserContext("req-1")
            >>> ctx["correlation-id"]
            'req-1'
            >>> ctx["status"]
            200
        """
        self["correlation-id"] = correlation_id
        self["initial-call-date"] = strftime(
            "%a, %d %b %Y %H:%M:%S +0000", gmtime()
        )
        self["call-date"] = self["initial-call-date"]
        self["context-log-chunk"] = 0
        self["status"] = 200
        self["context-info"] = ""


class ThotLoggerLevel:
    """Expose standard logging levels and string mappings."""

    NOTSET = logging.NOTSET
    CRITICAL = logging.CRITICAL
    ERROR = logging.ERROR
    WARNING = logging.WARNING
    INFO = logging.INFO
    DEBUG = logging.DEBUG
    log_levels_map = {
        "notset": logging.NOTSET,
        "critical": logging.CRITICAL,
        "error": logging.ERROR,
        "warning": logging.WARNING,
        "info": logging.INFO,
        "debug": logging.DEBUG,
    }


class ThotLogger:
    """Logging wrapper configured from JSON logger settings.

    JSON format:

    "logger": {
        "logging-level":"notset | critical" | "error" | "warning" | "info" | "debug"
    }

    Display format includes filename, function, line number, and correlation-id.
    """

    logger = None
    logger_config = LoggerConfiguration()
    count_logs = 0

    @staticmethod
    def _default_load():
        """Create the default logger and metrics counter.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger._default_load()  # doctest: +SKIP
        """
        if not ThotLogger.logger_config.configuration:
            ThotLogger.logger_config._default_load()

        ThotMetrics.create_counter(
            short_name="logger_errors",
            function_name="logger_errors",
            counter_description="Count error coming from logs",
        )

        ThotLogger.logger = logging.getLogger(
            ThotLogger.logger_config.logger_name
        )

        ThotLogger.logger.setLevel(
            ThotLoggerLevel.log_levels_map[
                ThotLogger.logger_config.configuration["logger"][
                    "logging-level"
                ]
            ]
        )
        ThotLogger.logger.handlers.clear()
        screen_handler = logging.StreamHandler(sys.stdout)
        screen_handler.addFilter(CorrelationIdFilter())
        screen_handler.setFormatter(TkeirTextFormatter())
        ThotLogger.logger.addHandler(screen_handler)

    @staticmethod
    def _aggregate_context(trace: str = None, context: dict = None) -> str:
        """Aggregate context fields into a log prefix string.

        Args:
            trace: Optional trace string.
            context: Optional context dictionary.

        Returns:
            Formatted context prefix.

        Example:
            >>> from thot.core.ThotLogger import LogUserContext, ThotLogger
            >>> ThotLogger.shutdown()
            >>> ctx = LogUserContext("req-1")
            >>> prefix = ThotLogger._aggregate_context(context=ctx)
            >>> "[correlation-id:req-1]" in prefix
            True
        """
        if not ThotLogger.logger:
            ThotLogger._default_load()
        ThotLogger.count_logs = ThotLogger.count_logs + 1
        log_ctx = "[global-log-count:" + str(ThotLogger.count_logs) + "]"
        if context:
            context["context-log-chunk"] = context["context-log-chunk"] + 1
            context["call-date"] = strftime(
                "%a, %d %b %Y %H:%M:%S +0000", gmtime()
            )
            for ctx_i in context:
                log_ctx = (
                    log_ctx
                    + "["
                    + str(ctx_i)
                    + ":"
                    + str(context[ctx_i])
                    + "]"
                )
        if trace:
            log_ctx = log_ctx + "[trace:" + trace + "]"
        return log_ctx

    @staticmethod
    def _correlation_extra(context: dict | None = None) -> dict[str, str]:
        """Build ``extra`` so formatters can print correlation-id."""
        if context and context.get("correlation-id"):
            return {"correlation_id": str(context["correlation-id"])}
        bound = current_correlation_id()
        return {"correlation_id": bound if bound else "-"}

    @staticmethod
    def _emit(
        level: str,
        text: str,
        *,
        trace=None,
        context=None,
        count_error: bool = False,
    ) -> None:
        if not ThotLogger.logger:
            ThotLogger._default_load()
        assert ThotLogger.logger is not None
        msg = (
            ThotLogger._aggregate_context(trace=trace, context=context)
            + " "
            + text
        )
        if count_error:
            ThotMetrics.increment_counter(
                short_name="logger_errors", path="/", method="error"
            )
        log_fn = getattr(ThotLogger.logger, level)
        # stacklevel=3 → real caller (info/error → _emit → logging).
        log_fn(msg, extra=ThotLogger._correlation_extra(context), stacklevel=3)

    @staticmethod
    def load(config_f, logger_name: str = "default", path: list = []):
        """Load logger configuration from a JSON file.

        Args:
            config_f: File-like object containing configuration JSON.
            logger_name: Logger name displayed in log lines.
            path: Optional configuration path prefix.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.load(open("/dev/null"))  # doctest: +SKIP
        """
        ThotLogger.logger_config.load(
            config_f, logger_name=logger_name, path=path
        )
        ThotLogger._default_load()

    @staticmethod
    def loads(configuration: dict = None, logger_name: str = "default"):
        """Load logger configuration from a dictionary.

        Args:
            configuration: Logger configuration dictionary.
            logger_name: Logger name displayed in log lines.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.loads({"logger": {"logging-level": "debug"}})  # doctest: +SKIP
        """
        ThotLogger.logger_config.loads(
            configuration=configuration, logger_name=logger_name
        )
        ThotLogger._default_load()

    @staticmethod
    def critical(text: str, trace=None, context=None):
        """Log a critical message.

        Args:
            text: Message to display.
            trace: Optional trace string.
            context: Optional logging context.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.critical("failure")  # doctest: +SKIP
        """
        ThotLogger._emit(
            "critical", text, trace=trace, context=context, count_error=True
        )

    @staticmethod
    def error(text: str, trace=None, context=None):
        """Log an error message.

        Args:
            text: Message to display.
            trace: Optional trace string.
            context: Optional logging context.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.error("failure")  # doctest: +SKIP
        """
        ThotLogger._emit(
            "error", text, trace=trace, context=context, count_error=True
        )

    @staticmethod
    def warning(text: str, trace=None, context=None):
        """Log a warning message.

        Args:
            text: Message to display.
            trace: Optional trace string.
            context: Optional logging context.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.warning("careful")  # doctest: +SKIP
        """
        ThotLogger._emit("warning", text, trace=trace, context=context)

    @staticmethod
    def info(text: str, trace=None, context=None):
        """Log an informational message.

        Args:
            text: Message to display.
            trace: Optional trace string.
            context: Optional logging context.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.info("started")  # doctest: +SKIP
        """
        ThotLogger._emit("info", text, trace=trace, context=context)

    @staticmethod
    def debug(text: str, trace=None, context=None):
        """Log a debug message.

        Args:
            text: Message to display.
            trace: Optional trace string.
            context: Optional logging context.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.debug("details")  # doctest: +SKIP
        """
        ThotLogger._emit("debug", text, trace=trace, context=context)

    @staticmethod
    def shutdown():
        """Shut down logging and clear the cached logger.

        Example:
            >>> from thot.core.ThotLogger import ThotLogger
            >>> ThotLogger.shutdown()
            >>> ThotLogger.logger is None
            True
        """
        logging.shutdown()
        ThotLogger.logger = None
        ThotLogger.logger_config.clear()
