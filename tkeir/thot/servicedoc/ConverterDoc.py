# -*- coding: utf-8 -*-
"""Sanic documentation
Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2021 by THALES
"""
from sanic_openapi import doc


class ListTypesDoc:
    results: doc.String(description="list of possible input document format")
    info: doc.String(description="service uniq id")
    config: doc.String(description="configuration file path")
    version: doc.String(description="version of the service")
    date: doc.String(description="service development date")


class ListTypesErrorDoc:
    error: doc.String(description="error description")
    exception: doc.String(description="exception returned")
    trace: doc.String(description="code trace of the error")
    info: doc.String(description="service uniq id")
    config: doc.String(description="configuration file path")


class RunEntryDoc:
    datatype: doc.String(description="type of data return (available list could be returned by list-type")
    source: doc.String(description="source of the document on host file system")
    data: doc.String(description="base64 encoded document")
