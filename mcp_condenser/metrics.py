"""Prometheus metrics for mcp-condenser proxy.

Provides a NoopRecorder (zero overhead when disabled) and a PrometheusRecorder
behind a shared interface.  Use create_recorder() to pick the right one.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Protocol


class MetricsRecorder(Protocol):
    """Interface shared by Noop and Prometheus recorders."""

    def record_request(self, tool: str, server: str, mode: str) -> None: ...
    def record_tokens(self, tool: str, server: str, input_tokens: int, output_tokens: int) -> None: ...
    def record_compression_ratio(self, tool: str, server: str, ratio: float) -> None: ...
    def record_processing_seconds(self, tool: str, server: str, duration: float) -> None: ...
    def record_truncation(self, tool: str, server: str) -> None: ...


class NoopRecorder:
    """No-op implementation — all methods are pass-through."""

    def record_request(self, tool: str, server: str, mode: str) -> None:
        pass

    def record_tokens(self, tool: str, server: str, input_tokens: int, output_tokens: int) -> None:
        pass

    def record_compression_ratio(self, tool: str, server: str, ratio: float) -> None:
        pass

    def record_processing_seconds(self, tool: str, server: str, duration: float) -> None:
        pass

    def record_truncation(self, tool: str, server: str) -> None:
        pass


class PrometheusRecorder:
    """Records metrics using prometheus_client."""

    def __init__(self, registry=None):
        from prometheus_client import CollectorRegistry, Counter, Histogram

        if registry is None:
            from prometheus_client import REGISTRY
            registry = REGISTRY

        self._registry = registry

        self.requests_total = Counter(
            "condenser_requests_total",
            "Items processed",
            ["tool", "server", "mode"],
            registry=registry,
        )
        self.input_tokens_total = Counter(
            "condenser_input_tokens_total",
            "Input tokens before condensing",
            ["tool", "server"],
            registry=registry,
        )
        self.output_tokens_total = Counter(
            "condenser_output_tokens_total",
            "Output tokens after condensing",
            ["tool", "server"],
            registry=registry,
        )
        self.saved_tokens_total = Counter(
            "condenser_saved_tokens_total",
            "Tokens saved (input - output, positive only)",
            ["tool", "server"],
            registry=registry,
        )
        self.compression_ratio = Histogram(
            "condenser_compression_ratio",
            "output/input ratio per item (lower = better)",
            ["tool", "server"],
            registry=registry,
        )
        self.processing_seconds = Histogram(
            "condenser_processing_seconds",
            "Wall clock time per _condense_item() call",
            ["tool", "server"],
            registry=registry,
        )
        self.truncations_total = Counter(
            "condenser_truncations_total",
            "Token-limit truncation events",
            ["tool", "server"],
            registry=registry,
        )

    def record_request(self, tool: str, server: str, mode: str) -> None:
        self.requests_total.labels(tool=tool, server=server, mode=mode).inc()

    def record_tokens(self, tool: str, server: str, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens_total.labels(tool=tool, server=server).inc(input_tokens)
        self.output_tokens_total.labels(tool=tool, server=server).inc(output_tokens)
        saved = input_tokens - output_tokens
        if saved > 0:
            self.saved_tokens_total.labels(tool=tool, server=server).inc(saved)

    def record_compression_ratio(self, tool: str, server: str, ratio: float) -> None:
        self.compression_ratio.labels(tool=tool, server=server).observe(ratio)

    def record_processing_seconds(self, tool: str, server: str, duration: float) -> None:
        self.processing_seconds.labels(tool=tool, server=server).observe(duration)

    def record_truncation(self, tool: str, server: str) -> None:
        self.truncations_total.labels(tool=tool, server=server).inc()


@contextmanager
def timer():
    """Context manager that yields a callable returning elapsed seconds."""
    start = time.monotonic()
    elapsed = None

    def get_elapsed() -> float:
        nonlocal elapsed
        if elapsed is None:
            elapsed = time.monotonic() - start
        return elapsed

    yield get_elapsed
    # Finalize if not already read
    if elapsed is None:
        elapsed = time.monotonic() - start


def create_recorder(enabled: bool = False, port: int = 9090) -> NoopRecorder | PrometheusRecorder:
    """Factory: start metrics HTTP server when enabled, return appropriate recorder."""
    if not enabled:
        return NoopRecorder()

    from prometheus_client import start_http_server

    recorder = PrometheusRecorder()
    start_http_server(port)
    return recorder
