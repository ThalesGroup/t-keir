"""Common configuration

Common configuration function

Description:
This file contains the constant string of T-KEIR and
the function to generation error/trace string

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.

"""

SERVICE_HEALTH_OK = "ok"
SERVICE_LOADED = "Service is not loaded"
SERVICE_NOT_LOADED = "Service is not loaded"
SERVICE_INTERNAL_ERROR = "[internal error]"
SERVICE_PAGE_NOT_FOUND = "Page not found"


def exception_error_and_trace(ex: str, tr: str) -> str:
    """Format an exception message with its traceback for logging.

    Args:
        ex: Exception message text.
        tr: Traceback text.

    Returns:
        Combined error string.

    Example:
        >>> exception_error_and_trace("boom", "line 1")
        'Exception:boom - Trace:line 1'
    """
    return "Exception:" + ex + " - Trace:" + tr
