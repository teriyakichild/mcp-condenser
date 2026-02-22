"""Tests for individually toggling condensing heuristics."""

import json

import pytest

from mcp_condenser.condenser import Heuristics, condense_json, preprocess_table, render_table
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
        assert h.max_tuple_size == 4
        assert h.max_table_columns == 0
        assert h.elide_mostly_zero_pct == 0.0
        assert h.pivot_key_value is True

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


class TestMaxTupleSizeToggle:
    def _make_wide_rows(self):
        """Rows with a 6-member numeric group (memory.*) and a 3-member group (vec.*)."""
        return [
            {
                "name": "a",
                "memory": {"availableBytes": 1, "majorPageFaults": 2, "pageFaults": 3,
                           "rssBytes": 4, "usageBytes": 5, "workingSetBytes": 6},
                "vec": {"x": 10, "y": 20, "z": 30},
            },
            {
                "name": "b",
                "memory": {"availableBytes": 7, "majorPageFaults": 8, "pageFaults": 9,
                           "rssBytes": 10, "usageBytes": 11, "workingSetBytes": 12},
                "vec": {"x": 40, "y": 50, "z": 60},
            },
            {
                "name": "c",
                "memory": {"availableBytes": 13, "majorPageFaults": 14, "pageFaults": 15,
                           "rssBytes": 16, "usageBytes": 17, "workingSetBytes": 18},
                "vec": {"x": 70, "y": 80, "z": 90},
            },
        ]

    def test_default_max_skips_large_groups(self):
        """6-member group should NOT be grouped at default max_tuple_size=4."""
        rows = self._make_wide_rows()
        _, _, final = preprocess_table("t", rows, Heuristics())
        headers = [h for h, _ in final]
        # memory group (6 members) should NOT be grouped
        assert not any("memory(" in h for h in headers)
        # individual memory columns should be preserved
        assert "memory.availableBytes" in headers
        assert "memory.workingSetBytes" in headers

    def test_small_group_still_grouped(self):
        """3-member group should still be grouped at default max_tuple_size=4."""
        rows = self._make_wide_rows()
        _, _, final = preprocess_table("t", rows, Heuristics())
        headers = [h for h, _ in final]
        assert any("vec(" in h for h in headers)

    def test_custom_max_allows_larger(self):
        """max_tuple_size=6 should allow the 6-member group."""
        rows = self._make_wide_rows()
        _, _, final = preprocess_table("t", rows, Heuristics(max_tuple_size=6))
        headers = [h for h, _ in final]
        assert any("memory(" in h for h in headers)


class TestMaxTableColumns:
    def _make_wide_rows(self):
        """Build a 24-column table mimicking pods data."""
        cols = [f"col{i}" for i in range(22)]
        rows = []
        for name in ["pod-a", "pod-b", "pod-c"]:
            row = {"podRef.name": name, "podRef.namespace": "default"}
            for c in cols:
                row[c] = name.count("a") + 1  # some non-zero value
            rows.append(row)
        return rows

    def test_wide_table_capped(self):
        """24-col table with max_table_columns=10 results in <=10 columns."""
        rows = self._make_wide_rows()
        h = Heuristics(max_table_columns=10, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        _, cleaned, final = preprocess_table("t", rows, h)
        assert len(final) <= 10
        for row in cleaned:
            assert len(row) <= 10

    def test_identity_columns_survive_cap(self):
        """podRef.name and podRef.namespace survive even at a tight cap."""
        rows = self._make_wide_rows()
        h = Heuristics(max_table_columns=4, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        _, cleaned, final = preprocess_table("t", rows, h)
        headers = [hdr for hdr, _ in final]
        assert "podRef.name" in headers
        assert "podRef.namespace" in headers

    def test_overflow_annotated(self):
        """Annotation lists dropped columns."""
        rows = self._make_wide_rows()
        h = Heuristics(max_table_columns=4, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        annotations, _, _ = preprocess_table("t", rows, h)
        overflow_annotations = [a for a in annotations if "overflow" in a]
        assert len(overflow_annotations) == 1
        assert "columns exceed limit" in overflow_annotations[0]

    def test_zero_means_no_limit(self):
        """max_table_columns=0 keeps all columns (default behavior)."""
        rows = self._make_wide_rows()
        h = Heuristics(max_table_columns=0, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        _, _, final = preprocess_table("t", rows, h)
        # Should have all 24 columns (2 identity + 22 data)
        assert len(final) == 24


class TestElideMostlyZero:
    def _make_rows(self):
        """5 rows where mostly_zero_col is zero for 4/5 (80%)."""
        return [
            {"name": "a", "data_col": 100, "mostly_zero_col": 0, "mixed_col": 10},
            {"name": "b", "data_col": 200, "mostly_zero_col": 0, "mixed_col": 0},
            {"name": "c", "data_col": 300, "mostly_zero_col": 0, "mixed_col": 20},
            {"name": "d", "data_col": 400, "mostly_zero_col": 42, "mixed_col": 0},
            {"name": "e", "data_col": 500, "mostly_zero_col": 0, "mixed_col": 30},
        ]

    def test_mostly_zero_elided(self):
        """Column with 80% zeros is elided at threshold 0.8."""
        rows = self._make_rows()
        h = Heuristics(elide_mostly_zero_pct=0.8, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        annotations, cleaned, _ = preprocess_table("t", rows, h)
        assert any("mostly_zero" in a and "mostly_zero_col" in a for a in annotations)
        for row in cleaned:
            assert "mostly_zero_col" not in row

    def test_outlier_values_in_annotation(self):
        """Annotation includes non-zero values with row identity labels."""
        rows = self._make_rows()
        h = Heuristics(elide_mostly_zero_pct=0.8, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        annotations, _, _ = preprocess_table("t", rows, h)
        mz_ann = [a for a in annotations if "mostly_zero" in a and "mostly_zero_col" in a]
        assert len(mz_ann) == 1
        assert "d=42" in mz_ann[0]

    def test_not_quite_mostly_zero_kept(self):
        """Column with 60% zeros kept at threshold 0.8."""
        rows = self._make_rows()
        # mixed_col has 2/5 zeros (40%), should NOT be elided at 0.8 threshold
        h = Heuristics(elide_mostly_zero_pct=0.8, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        _, cleaned, _ = preprocess_table("t", rows, h)
        assert any("mixed_col" in row for row in cleaned)

    def test_disabled_by_default(self):
        """elide_mostly_zero_pct=0.0 keeps all columns."""
        rows = self._make_rows()
        h = Heuristics(elide_mostly_zero_pct=0.0, elide_all_zero=False, elide_all_null=False,
                        elide_timestamps=False, elide_constants=False, group_tuples=False)
        annotations, cleaned, _ = preprocess_table("t", rows, h)
        assert not any("mostly_zero" in a for a in annotations)
        assert any("mostly_zero_col" in row for row in cleaned)



class TestPivotKeyValueToggle:
    def _make_tagged_rows(self):
        return [
            {"InstanceId": "i-aaa", "Tags": [{"Key": "Name", "Value": "web"}, {"Key": "Env", "Value": "prod"}]},
            {"InstanceId": "i-bbb", "Tags": [{"Key": "Name", "Value": "api"}, {"Key": "Env", "Value": "staging"}]},
        ]

    def test_enabled_pivots_into_columns(self):
        rows = self._make_tagged_rows()
        blocks = render_table("Instances", rows, Heuristics(pivot_key_value=True))
        text = "\n".join(blocks)
        assert "Tags.Name" in text
        assert "Tags.Env" in text
        assert "web" in text
        # No sub-table for Tags
        assert "Instances.Tags" not in text

    def test_disabled_extracts_as_subtable(self):
        rows = self._make_tagged_rows()
        blocks = render_table("Instances", rows, Heuristics(pivot_key_value=False))
        text = "\n".join(blocks)
        # Should have a sub-table for Tags
        assert "Instances.Tags" in text
        # Pivoted columns should NOT appear
        assert "Tags.Name" not in text
        assert "Tags.Env" not in text

    def test_default_is_enabled(self):
        h = Heuristics()
        assert h.pivot_key_value is True


    def test_typo_raises_helpful_error(self):
        cfg = ServerConfig(
            url="http://localhost/mcp",
            heuristics={"elide_timestaps": False},  # typo
        )
        mw = CondenserMiddleware(server_configs={"default": cfg})
        data = json.dumps([{"a": 1, "b": 2}, {"a": 3, "b": 4}])
        with pytest.raises(TypeError, match="Valid heuristic names are"):
            mw._condense_item(data, "some_tool", cfg)
