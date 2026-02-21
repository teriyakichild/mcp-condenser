"""Tests for individually toggling condensing heuristics."""

import json

import pytest

from mcp_condenser.condenser import Heuristics, condense_json, preprocess_table
from mcp_condenser.config import ServerConfig
from mcp_condenser.proxy import CondenserMiddleware


# Shared fixture: rows with all-zero, all-null, constant, timestamp, and tuple-groupable columns
def _make_rows():
    return [
        {
            "name": "a",
            "zero_col": 0,
            "null_col": None,
            "const_col": "same",
            "ts": "2024-01-01T00:00:00Z",
            "vec.x": 1,
            "vec.y": 2,
            "vec.z": 3,
        },
        {
            "name": "b",
            "zero_col": 0,
            "null_col": None,
            "const_col": "same",
            "ts": "2024-01-01T00:00:05Z",
            "vec.x": 4,
            "vec.y": 5,
            "vec.z": 6,
        },
        {
            "name": "c",
            "zero_col": 0,
            "null_col": None,
            "const_col": "same",
            "ts": "2024-01-01T00:00:10Z",
            "vec.x": 7,
            "vec.y": 8,
            "vec.z": 9,
        },
    ]


class TestHeuristicsDataclass:
    def test_defaults_all_true(self):
        h = Heuristics()
        assert h.elide_all_zero is True
        assert h.elide_all_null is True
        assert h.elide_timestamps is True
        assert h.elide_constants is True
        assert h.group_tuples is True

    def test_override_single(self):
        h = Heuristics(elide_timestamps=False)
        assert h.elide_timestamps is False
        assert h.elide_all_zero is True

    def test_from_dict(self):
        d = {"elide_timestamps": False, "group_tuples": False}
        h = Heuristics(**d)
        assert h.elide_timestamps is False
        assert h.group_tuples is False
        assert h.elide_all_zero is True


class TestElideAllZeroToggle:
    def test_enabled_elides_zero_column(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics())
        assert any("all_zero" in a and "zero_col" in a for a in annotations)
        # zero_col should not appear in cleaned rows
        for row in cleaned:
            assert "zero_col" not in row

    def test_disabled_keeps_zero_column(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics(elide_all_zero=False))
        assert not any("all_zero" in a for a in annotations)
        # zero_col should still be present
        assert any("zero_col" in row for row in cleaned)


class TestElideAllNullToggle:
    def test_enabled_elides_null_column(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics())
        assert any("all_null" in a and "null_col" in a for a in annotations)
        for row in cleaned:
            assert "null_col" not in row

    def test_disabled_keeps_null_column(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics(elide_all_null=False))
        assert not any("all_null" in a for a in annotations)
        assert any("null_col" in row for row in cleaned)


class TestElideTimestampsToggle:
    def test_enabled_elides_clustered_timestamps(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics())
        assert any("timestamp_cluster" in a and "ts" in a for a in annotations)
        for row in cleaned:
            assert "ts" not in row

    def test_disabled_keeps_timestamps(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics(elide_timestamps=False))
        assert not any("timestamp_cluster" in a for a in annotations)
        assert any("ts" in row for row in cleaned)


class TestElideConstantsToggle:
    def test_enabled_elides_constant_column(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics())
        assert any("constant" in a and "const_col" in a for a in annotations)
        for row in cleaned:
            assert "const_col" not in row

    def test_disabled_keeps_constant_column(self):
        rows = _make_rows()
        annotations, cleaned, _ = preprocess_table("t", rows, Heuristics(elide_constants=False))
        # Should not have a "constant const_col" annotation
        assert not any("constant" in a and "const_col" in a for a in annotations)
        assert any("const_col" in row for row in cleaned)


class TestGroupTuplesToggle:
    def test_enabled_groups_tuples(self):
        rows = _make_rows()
        annotations, cleaned, final = preprocess_table("t", rows, Heuristics())
        headers = [h for h, _ in final]
        # vec.x, vec.y, vec.z should be merged into vec(x,y,z)
        assert any("vec(" in h for h in headers)
        assert "vec.x" not in headers

    def test_disabled_keeps_individual_columns(self):
        rows = _make_rows()
        annotations, cleaned, final = preprocess_table("t", rows, Heuristics(group_tuples=False))
        headers = [h for h, _ in final]
        assert not any("vec(" in h for h in headers)
        assert "vec.x" in headers
        assert "vec.y" in headers
        assert "vec.z" in headers


class TestCondenseJsonWithHeuristics:
    def test_default_heuristics_matches_no_arg(self):
        data = {"items": _make_rows()}
        default_result = condense_json(data)
        explicit_result = condense_json(data, heuristics=Heuristics())
        assert default_result == explicit_result

    def test_disabled_timestamp_elision_preserves_ts(self):
        data = {"items": _make_rows()}
        result = condense_json(data, heuristics=Heuristics(elide_timestamps=False))
        # With timestamps not elided, the ts values should appear in the output
        assert "2024-01-01T00:00:00Z" in result

    def test_all_disabled_preserves_everything(self):
        data = {"items": _make_rows()}
        h = Heuristics(
            elide_all_zero=False,
            elide_all_null=False,
            elide_timestamps=False,
            elide_constants=False,
            group_tuples=False,
        )
        result = condense_json(data, heuristics=h)
        # No elision annotations should be present
        assert "elided" not in result
        # All column values should be present
        assert "zero_col" in result
        assert "const_col" in result


class TestInvalidHeuristicKey:
    def test_typo_raises_helpful_error(self):
        cfg = ServerConfig(
            url="http://localhost/mcp",
            heuristics={"elide_timestaps": False},  # typo
        )
        mw = CondenserMiddleware(server_configs={"default": cfg})
        data = json.dumps([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        with pytest.raises(TypeError, match="Valid heuristic names are"):
            mw._condense_item(data, "some_tool", cfg)
