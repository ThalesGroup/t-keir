# -*- coding: utf-8 -*-
"""Observability Metrics

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES 
All Rights Reserved.
"""

import prometheus_client
from prometheus_client import Counter

# https://www.cloudbees.com/blog/monitoring-your-synchronous-python-web-applications-using-prometheus


class ThotMetrics:
    call_counter = dict()
    METRIC_MIME_TYPE = prometheus_client.exposition.CONTENT_TYPE_LATEST
    APP_NAME = "T-KEIR"

    @staticmethod
    def create_counter(short_name:str="default", function_name:str="empty", counter_description:str="empty"):
        """Create prometheus Counter
        The counter contain application name, method (GET,POST,...), endpoint path and REST status
        Args:
            short_name (str): counter short name
            function_name (str) : counter function name
            count_description (str) : counter description
        """
        if short_name not in ThotMetrics.call_counter:
            ThotMetrics.call_counter[short_name] = Counter(
                function_name, counter_description, ["app_name", "method", "endpoint", "http_status"]
            )

    @staticmethod
    def increment_counter(short_name:str="default", method:str="default", path:str="default", status:int=200):
        """Create prometheus Counter

        Args:
            short_name (str): counter short name
            method (str) : method name (GEST POST ...)
            path (str) : call path
            status (int) : REST status
        """

        ThotMetrics.call_counter[short_name].labels(ThotMetrics.APP_NAME, method, path, status).inc()

    @staticmethod
    def generateMetricsResponse():
        """Generate last metric for promotheus"""
        return prometheus_client.generate_latest()
