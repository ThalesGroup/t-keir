# -*- coding: utf-8 -*-
"""Observability Metrics

Author: Eric Blaudez (Eric Blaudez)

Copyright (c) 2022 THALES
All Rights Reserved.
"""

from __future__ import annotations

from opentelemetry import metrics
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.metrics import Counter, Meter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource

_PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"


class ThotMetrics:
    """OpenTelemetry counters for T-KEIR service observability."""

    call_counter: dict[str, Counter] = {}
    METRIC_MIME_TYPE = _PROMETHEUS_CONTENT_TYPE
    APP_NAME = "T-KEIR"

    _reader: PrometheusMetricReader | None = None
    _meter: Meter | None = None

    @classmethod
    def _ensure_provider(cls) -> None:
        """Initialize the OpenTelemetry meter provider once.

        Example:
            >>> from thot.core.ThotMetrics import ThotMetrics
            >>> ThotMetrics._ensure_provider()
            >>> ThotMetrics._meter is not None
            True
        """
        if cls._meter is not None:
            return
        cls._reader = PrometheusMetricReader()
        provider = MeterProvider(
            resource=Resource.create({"service.name": cls.APP_NAME}),
            metric_readers=[cls._reader],
        )
        metrics.set_meter_provider(provider)
        cls._meter = metrics.get_meter("thot.metrics")

    @staticmethod
    def create_counter(
        short_name: str = "default",
        function_name: str = "empty",
        counter_description: str = "empty",
    ):
        """Create an OpenTelemetry counter when it does not already exist.

        Args:
            short_name: Internal counter key.
            function_name: OpenTelemetry metric name.
            counter_description: Human-readable metric description.

        Example:
            >>> from thot.core.ThotMetrics import ThotMetrics
            >>> ThotMetrics.create_counter(
            ...     short_name="demo",
            ...     function_name="demo_counter",
            ...     counter_description="Demo counter",
            ... )
            >>> "demo" in ThotMetrics.call_counter
            True
        """
        ThotMetrics._ensure_provider()
        assert ThotMetrics._meter is not None
        if short_name not in ThotMetrics.call_counter:
            ThotMetrics.call_counter[short_name] = (
                ThotMetrics._meter.create_counter(
                    function_name,
                    description=counter_description,
                )
            )

    @staticmethod
    def increment_counter(
        short_name: str = "default",
        method: str = "default",
        path: str = "default",
        status: int = 200,
    ):
        """Increment an existing OpenTelemetry counter.

        Args:
            short_name: Internal counter key.
            method: HTTP method label.
            path: Endpoint path label.
            status: HTTP status label.

        Example:
            >>> from thot.core.ThotMetrics import ThotMetrics
            >>> ThotMetrics.create_counter(
            ...     short_name="hits",
            ...     function_name="hits_total",
            ...     counter_description="Hit counter",
            ... )
            >>> ThotMetrics.increment_counter(
            ...     short_name="hits", method="GET", path="/", status=200
            ... )
            >>> "hits" in ThotMetrics.call_counter
            True
        """
        ThotMetrics._ensure_provider()
        ThotMetrics.call_counter[short_name].add(
            1,
            {
                "app_name": ThotMetrics.APP_NAME,
                "method": method,
                "endpoint": path,
                "http_status": str(status),
            },
        )

    @staticmethod
    def generateMetricsResponse():
        """Generate the latest Prometheus exposition payload from OTel metrics.

        Returns:
            Bytes containing the Prometheus exposition format.

        Example:
            >>> from thot.core.ThotMetrics import ThotMetrics
            >>> ThotMetrics.create_counter(
            ...     short_name="expose",
            ...     function_name="expose_total",
            ...     counter_description="Expose counter",
            ... )
            >>> payload = ThotMetrics.generateMetricsResponse()
            >>> isinstance(payload, (bytes, bytearray))
            True
        """
        from prometheus_client import REGISTRY, generate_latest

        ThotMetrics._ensure_provider()
        return generate_latest(REGISTRY)
