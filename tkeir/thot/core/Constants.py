# -*- coding: utf-8 -*-
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
    return "Exception:" + ex + " - Trace:" + tr
