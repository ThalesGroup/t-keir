# -*- coding: utf-8 -*-
"""Logger of library

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import logging
import os
import sys
from time import gmtime, strftime

from thot.core.LoggerConfiguration import LoggerConfiguration
from thot.core.ThotMetrics import ThotMetrics


class LogUserContext(dict):
    def __init__(self, correlation_id:str):
        """Initialiaize logger context with a correlation_id
            Args:
                correlation_id : string representating the correlation_id to follow the logs 
        """
        self["correlation-id"] = correlation_id
        self["initial-call-date"] = strftime("%a, %d %b %Y %H:%M:%S +0000", gmtime())
        self["call-date"] = self["initial-call-date"]
        self["context-log-chunk"] = 0
        self["status"] = 200
        self["context-info"] = ""


class ThotLoggerLevel:
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
    """Logging wrapper
    Load/Create logger with json like configuration :
    JSON format:

    "logger": {
        "logging-level":"notset | critical" | "error" | "warning" | "info" | "debug"
    }
    """

    logger = None
    logger_config = LoggerConfiguration()
    count_logs = 0

    @staticmethod
    def _default_load():
        """create logger"""
        if not ThotLogger.logger_config.configuration:
            ThotLogger.logger_config._default_load()

        ThotMetrics.create_counter(
            short_name="logger_errors", function_name="logger_errors", counter_description="Count error coming from logs"
        )

        ThotLogger.logger = logging.getLogger(ThotLogger.logger_config.logger_name)

        ThotLogger.logger.setLevel(
            ThotLoggerLevel.log_levels_map[ThotLogger.logger_config.configuration["logger"]["logging-level"]]
        )
        screen_handler = logging.StreamHandler(sys.stdout)
        screen_formatter = logging.Formatter(
            "[%(levelname)s][%(name)s][%(asctime)s][%(filename)s:%(lineno)s - %(funcName)20s()][PID(%(process)d)] %(message)s"
        )
        screen_handler.setFormatter(screen_formatter)
        ThotLogger.logger.addHandler(screen_handler)

    @staticmethod
    def _aggregate_context(trace:str=None, context:dict=None)->str:
        """Aggregate context to generate string

        Args:
            trace (str): trace (if it is generated).
            context (dict) : dictionary containing log context
        Return:
            str : string containing context and trace
        """
        if not ThotLogger.logger:
            ThotLogger._default_load()
        ThotLogger.count_logs = ThotLogger.count_logs + 1
        log_ctx = "[global-log-count:" + str(ThotLogger.count_logs) + "]"
        if context:
            context["context-log-chunk"] = context["context-log-chunk"] + 1
            context["call-date"] = strftime("%a, %d %b %Y %H:%M:%S +0000", gmtime())
            for ctx_i in context:
                log_ctx = log_ctx + "[" + str(ctx_i) + ":" + str(context[ctx_i]) + "]"
        if trace:
            log_ctx = log_ctx + "[trace:" + trace + "]"
        return log_ctx

    @staticmethod
    def load(config_f, logger_name: str = "default", path: list = []):
        """Load logger configuration from file

        Args:
            config_f (mandatory): configruation with file handler.
            logger_name (str,optional) : name of the logger (display in log line). Defaults to default
            path (list,option): access to a part of the configuration
        """
        ThotLogger.logger_config.load(config_f, logger_name=logger_name, path=path)
        ThotLogger._default_load()

    @staticmethod
    def loads(configuration: dict = None, logger_name: str = "default"):
        """Load logger configuration from dict (json)

        Args:
            configuration (dict, optional): load logger configruation with dict. Defaults to None.
        """
        ThotLogger.logger_config.loads(configuration=configuration, logger_name=logger_name)
        ThotLogger._default_load()

    @staticmethod
    def critical(text: str, trace=None, context=None):
        """Logger Helper on error
        Args:
            text (str): string to display on error level
        """
        if not ThotLogger.logger:
            ThotLogger._default_load()
        msg = ThotLogger._aggregate_context(trace=trace, context=context) + " " + text
        ThotMetrics.increment_counter(short_name="logger_errors", path="/", method="error")
        ThotLogger.logger.critical(msg)

    @staticmethod
    def error(text: str, trace=None, context=None):
        """Logger Helper on error
        Args:
            text (str): string to display on error level
        """
        if not ThotLogger.logger:
            ThotLogger._default_load()
        msg = ThotLogger._aggregate_context(trace=trace, context=context) + " " + text
        ThotMetrics.increment_counter(short_name="logger_errors", path="/", method="error")
        ThotLogger.logger.error(msg)

    @staticmethod
    def warning(text: str, trace=None, context=None):
        """Logger Helper on warning
        Args:
            text (str): string to display on warning level
        """
        if not ThotLogger.logger:
            ThotLogger._default_load()
        msg = ThotLogger._aggregate_context(trace=trace, context=context) + " " + text
        ThotLogger.logger.warning(msg)

    @staticmethod
    def info(text: str, trace=None, context=None):
        """Logger Helper on info
        Args:
            text (str): string to display on info level
        """
        if not ThotLogger.logger:
            ThotLogger._default_load()
        msg = ThotLogger._aggregate_context(trace=trace, context=context) + " " + text
        ThotLogger.logger.info(msg)

    @staticmethod
    def debug(text: str, trace=None, context=None):
        """Logger Helper on debug
        Args:
            text (str): string to display on debug level
        """
        if not ThotLogger.logger:
            ThotLogger._default_load()
        msg = ThotLogger._aggregate_context(trace=trace, context=context) + " " + text
        ThotLogger.logger.debug(msg)

    @staticmethod
    def shutdown():
        """shutdown help to logging and clear ThotLogger"""
        logging.shutdown()
        ThotLogger.logger = None
        ThotLogger.logger_config.clear()
