"""Tests for the metrics module."""

import time

from prometheus_client import CollectorRegistry

from mcp_condenser.metrics import NoopRecorder, PrometheusRecorder, timer


class TestNoopRecorder:
    """NoopRecorder should be callable with no side effects."""

    def test_all_methods_callable(self):
        r = NoopRecorder()
        r.record_request("tool", "server", "condense")
        r.record_tokens("tool", "server", 100, 50)
        r.record_compression_ratio("tool", "server", 0.5)
        r.record_processing_seconds("tool", "server", 1.23)
        r.record_truncation("tool", "server")


class TestPrometheusRecorder:
    def _make_recorder(self):
        registry = CollectorRegistry()
        return PrometheusRecorder(registry=registry), registry

    def test_record_request_increments(self):
        rec, registry = self._make_recorder()
        rec.record_request("get_pods", "k8s", "condense")
        rec.record_request("get_pods", "k8s", "condense")
        val = registry.get_sample_value(
            "condenser_requests_total",
            {"tool": "get_pods", "server": "k8s", "mode": "condense"},
        )
        assert val == 2.0

    def test_record_tokens(self):
        rec, registry = self._make_recorder()
        rec.record_tokens("get_pods", "k8s", 1000, 300)
        assert registry.get_sample_value(
            "condenser_input_tokens_total", {"tool": "get_pods", "server": "k8s"}
        ) == 1000.0
        assert registry.get_sample_value(
            "condenser_output_tokens_total", {"tool": "get_pods", "server": "k8s"}
        ) == 300.0
        assert registry.get_sample_value(
            "condenser_saved_tokens_total", {"tool": "get_pods", "server": "k8s"}
        ) == 700.0

    def test_record_tokens_no_negative_saved(self):
        rec, registry = self._make_recorder()
        rec.record_tokens("tool", "srv", 100, 200)
        # saved_tokens should not be incremented when output > input
        assert registry.get_sample_value(
            "condenser_saved_tokens_total", {"tool": "tool", "server": "srv"}
        ) is None  # Counter never initialized for this label set

    def test_record_compression_ratio(self):
        rec, registry = self._make_recorder()
        rec.record_compression_ratio("tool", "srv", 0.3)
        count = registry.get_sample_value(
            "condenser_compression_ratio_count", {"tool": "tool", "server": "srv"}
        )
        assert count == 1.0

    def test_record_processing_seconds(self):
        rec, registry = self._make_recorder()
        rec.record_processing_seconds("tool", "srv", 0.5)
        count = registry.get_sample_value(
            "condenser_processing_seconds_count", {"tool": "tool", "server": "srv"}
        )
        assert count == 1.0

    def test_record_truncation(self):
        rec, registry = self._make_recorder()
        rec.record_truncation("tool", "srv")
        val = registry.get_sample_value(
            "condenser_truncations_total", {"tool": "tool", "server": "srv"}
        )
        assert val == 1.0

    def test_multiple_modes(self):
        rec, registry = self._make_recorder()
        rec.record_request("t", "s", "condense")
        rec.record_request("t", "s", "skipped")
        rec.record_request("t", "s", "passthrough")
        assert registry.get_sample_value(
            "condenser_requests_total", {"tool": "t", "server": "s", "mode": "condense"}
        ) == 1.0
        assert registry.get_sample_value(
            "condenser_requests_total", {"tool": "t", "server": "s", "mode": "skipped"}
        ) == 1.0
        assert registry.get_sample_value(
            "condenser_requests_total", {"tool": "t", "server": "s", "mode": "passthrough"}
        ) == 1.0


class TestTimer:
    def test_timer_returns_elapsed(self):
        with timer() as elapsed:
            time.sleep(0.01)
        assert elapsed() >= 0.01

    def test_timer_stable_after_exit(self):
        with timer() as elapsed:
            time.sleep(0.01)
        val1 = elapsed()
        time.sleep(0.01)
        val2 = elapsed()
        assert val1 == val2
