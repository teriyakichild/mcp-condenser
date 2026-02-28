"""Basic tests for condenser core functions."""

import warnings
from collections import OrderedDict

import pytest

from mcp_condenser.condenser import classify, flatten, fmt, find_identity_column, is_homogeneous_array, is_kv_array, pivot_kv_fields, condense_text, toon_encode, condense_json, toon_encode_json, truncate_to_token_limit, count_tokens
from mcp_condenser.parsers import parse_input


class TestClassify:
    def test_primitives(self):
        assert classify(None) == "null"
        assert classify(True) == "bool"
        assert classify(False) == "bool"
        assert classify(42) == "number"
        assert classify(3.14) == "number"
        assert classify("hello") == "string"

    def test_containers(self):
        assert classify([]) == "array"
        assert classify({}) == "object"

    def test_unknown(self):
        assert classify(object()) == "unknown"


class TestFmt:
    def test_none(self):
        assert fmt(None) == ""

    def test_bool(self):
        assert fmt(True) == "true"
        assert fmt(False) == "false"

    def test_int(self):
        assert fmt(42) == "42"

    def test_string(self):
        assert fmt("hello") == "hello"

    def test_float_whole_number(self):
        assert fmt(3.0) == "3"

    def test_float_fractional(self):
        assert fmt(3.14) == "3.14"

    def test_float_at_safe_boundary(self):
        """2**53 is the largest exactly-representable integer in float64."""
        assert fmt(float(2**53)) == str(2**53)

    def test_float_above_safe_boundary(self):
        """Above 2**53, float-to-int conversion can lose precision."""
        large = float(2**54)
        # Should NOT convert to int — fall through to str(val)
        assert fmt(large) == str(large)

    def test_float_inf(self):
        assert fmt(float("inf")) == "inf"
        assert fmt(float("-inf")) == "-inf"

    def test_float_nan(self):
        assert fmt(float("nan")) == "nan"


class TestFlatten:
    def test_flat_dict(self):
        result = flatten({"a": 1, "b": 2})
        assert result == OrderedDict([("a", 1), ("b", 2)])

    def test_nested_dict(self):
        result = flatten({"a": {"b": {"c": 1}}})
        assert result == OrderedDict([("a.b.c", 1)])

    def test_mixed_nesting(self):
        result = flatten({"x": 1, "y": {"z": 2, "w": 3}})
        assert result == OrderedDict([("x", 1), ("y.z", 2), ("y.w", 3)])

    def test_arrays_kept_as_is(self):
        result = flatten({"a": [1, 2, 3]})
        assert result == OrderedDict([("a", [1, 2, 3])])

    def test_empty_dict(self):
        result = flatten({})
        assert result == OrderedDict()


class TestIsHomogeneousArray:
    def test_uniform_dicts(self):
        arr = [{"a": 1, "b": 2}, {"a": 3, "b": 4}, {"a": 5, "b": 6}]
        assert is_homogeneous_array(arr) is True

    def test_single_item(self):
        assert is_homogeneous_array([{"a": 1}]) is False

    def test_empty(self):
        assert is_homogeneous_array([]) is False

    def test_non_dicts(self):
        assert is_homogeneous_array([1, 2, 3]) is False

    def test_sparse_keys(self):
        # Only 1 out of 3 keys shared — below 60% threshold
        arr = [{"a": 1, "b": 2, "c": 3}, {"a": 1, "d": 4, "e": 5}]
        assert is_homogeneous_array(arr) is False

    def test_mostly_shared_keys(self):
        arr = [{"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 2, "d": 4}]
        # 2 out of 4 union keys shared = 50%, below threshold
        assert is_homogeneous_array(arr) is False


class TestCondenseText:
    def test_simple_object(self):
        data = {"name": "test", "value": 42}
        result = condense_text(data)
        assert "name" in result
        assert "test" in result
        assert "42" in result

    def test_homogeneous_array(self):
        data = [
            {"id": 1, "name": "alice"},
            {"id": 2, "name": "bob"},
            {"id": 3, "name": "carol"},
        ]
        result = condense_text(data)
        assert "alice" in result
        assert "bob" in result
        assert "carol" in result
        # Should mention row count
        assert "3 rows" in result

    def test_nested_object(self):
        data = {"outer": {"inner": {"deep": "value"}}}
        result = condense_text(data)
        assert "deep" in result
        assert "value" in result

    def test_scalar_value(self):
        assert "hello" in condense_text("hello")
        assert "42" in condense_text(42)

    def test_round_trip_preserves_data(self):
        """All scalar values from the input should appear in the output."""
        data = {"items": [
            {"name": "x", "count": 10},
            {"name": "y", "count": 20},
        ]}
        result = condense_text(data)
        for val in ("x", "y", "10", "20"):
            assert val in result


class TestToonEncode:
    def test_basic_array(self):
        """Direct TOON encoding of a homogeneous array without elision."""
        data = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        result = toon_encode(data)
        # All values preserved — no elision
        for val in ("1", "2", "3", "4"):
            assert val in result
        # Column headers present
        assert "a" in result
        assert "b" in result

    def test_simple_object(self):
        data = {"name": "test", "value": 42}
        result = toon_encode(data)
        assert "name" in result
        assert "test" in result
        assert "42" in result

    def test_preserves_all_values(self):
        """Verify no data is lost — toon_encode should not elide anything."""
        data = [
            {"id": 1, "status": "ok", "count": 0},
            {"id": 2, "status": "ok", "count": 0},
            {"id": 3, "status": "ok", "count": 0},
        ]
        result = toon_encode(data)
        # condense_text would elide constant "status" and all-zero "count",
        # but toon_encode should preserve them
        for val in ("1", "2", "3", "ok", "0"):
            assert val in result

    def test_scalar(self):
        assert "hello" in toon_encode("hello")
        assert "42" in toon_encode(42)


class TestParseInput:
    def test_json_object(self):
        data, fmt = parse_input('{"a": 1}')
        assert data == {"a": 1}
        assert fmt == "json"

    def test_json_array(self):
        data, fmt = parse_input('[1, 2, 3]')
        assert data == [1, 2, 3]
        assert fmt == "json"

    def test_yaml_object(self):
        data, fmt = parse_input("name: alice\nage: 30\n")
        assert data == {"name": "alice", "age": 30}
        assert fmt == "yaml"

    def test_yaml_list(self):
        text = "- name: alice\n  age: 30\n- name: bob\n  age: 25\n"
        data, fmt = parse_input(text)
        assert len(data) == 2
        assert fmt == "yaml"

    def test_yaml_nested(self):
        text = "metadata:\n  name: nginx\n  namespace: default\n"
        data, fmt = parse_input(text)
        assert data == {"metadata": {"name": "nginx", "namespace": "default"}}
        assert fmt == "yaml"

    def test_json_preferred_over_yaml(self):
        """JSON-valid input should parse as JSON, not YAML."""
        data, fmt = parse_input('{"a": 1}')
        assert fmt == "json"

    def test_plain_scalar_rejected(self):
        """Bare scalars are valid YAML but not useful structured data."""
        with pytest.raises(ValueError):
            parse_input("just a string")

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            parse_input("")

    def test_invalid_both(self):
        with pytest.raises(ValueError):
            parse_input("{{not valid::")


class TestCondenseYaml:
    """Verify the full pipeline works with YAML-sourced data."""

    def test_yaml_object_condenses(self):
        text = "name: test\nvalue: 42\n"
        data, _ = parse_input(text)
        result = condense_text(data)
        assert "test" in result
        assert "42" in result

    def test_yaml_homogeneous_array(self):
        text = (
            "- id: 1\n  name: alice\n"
            "- id: 2\n  name: bob\n"
            "- id: 3\n  name: carol\n"
        )
        data, _ = parse_input(text)
        result = condense_text(data)
        assert "3 rows" in result
        assert "alice" in result

    def test_yaml_nested_k8s_style(self):
        text = (
            "metadata:\n"
            "  name: nginx\n"
            "  namespace: default\n"
            "spec:\n"
            "  replicas: 3\n"
        )
        data, _ = parse_input(text)
        result = condense_text(data)
        assert "nginx" in result
        assert "default" in result


class TestCondenseCsv:
    """Integration: CSV text → parse_input → condense_text → TOON table."""

    def test_csv_to_toon_table(self):
        csv_text = "name,age,city\nalice,30,nyc\nbob,25,sf\ncarol,40,la\n"
        data, fmt = parse_input(csv_text)
        assert fmt == "csv"
        result = condense_text(data)
        assert "3 rows" in result
        assert "alice" in result
        assert "bob" in result
        assert "carol" in result

    def test_csv_type_inference_in_toon(self):
        csv_text = "item,price,qty\nwidget,9.99,100\ngadget,24.50,50\n"
        data, _ = parse_input(csv_text)
        result = condense_text(data)
        assert "9.99" in result
        assert "100" in result


class TestCondenseXml:
    """Integration: XML text → parse_input → condense_text → TOON output."""

    def test_xml_repeated_children_to_toon_table(self):
        xml_text = (
            "<users>"
            "<user><name>alice</name><age>30</age><city>nyc</city></user>"
            "<user><name>bob</name><age>25</age><city>sf</city></user>"
            "<user><name>carol</name><age>40</age><city>la</city></user>"
            "</users>"
        )
        data, fmt = parse_input(xml_text)
        assert fmt == "xml"
        result = condense_text(data)
        assert "3 rows" in result
        assert "alice" in result
        assert "bob" in result
        assert "carol" in result

    def test_xml_nested_structure(self):
        xml_text = (
            "<server>"
            "<host>10.0.0.1</host>"
            "<ports><http>80</http><https>443</https></ports>"
            "</server>"
        )
        data, _ = parse_input(xml_text)
        result = condense_text(data)
        assert "10.0.0.1" in result
        assert "80" in result
        assert "443" in result


class TestTruncateToTokenLimit:
    def test_no_op_when_under_limit(self):
        """Text within the token limit is returned unchanged."""
        text = "hello world"
        result = truncate_to_token_limit(text, 1000)
        assert result == text

    def test_no_op_when_limit_zero(self):
        """Limit of 0 means no truncation (feature off)."""
        text = "hello world"
        result = truncate_to_token_limit(text, 0)
        assert result == text

    def test_truncation_when_over_limit(self):
        """Text over the limit gets truncated to fewer tokens."""
        text = "word " * 500  # ~500 tokens
        result = truncate_to_token_limit(text, 50)
        result_tokens = count_tokens(result)
        # The result (including the notice) should be roughly within the limit
        # Allow some slack for the notice overhead estimation
        assert result_tokens <= 60  # 50 + reasonable slack
        assert len(result) < len(text)

    def test_truncation_message_present(self):
        """Truncated output includes the truncation notice."""
        text = "word " * 500
        result = truncate_to_token_limit(text, 50)
        assert "[truncated:" in result
        assert "token limit" in result

    def test_empty_text(self):
        """Empty text is returned unchanged."""
        result = truncate_to_token_limit("", 100)
        assert result == ""

    def test_exact_at_limit(self):
        """Text exactly at the limit is returned unchanged."""
        text = "hello"
        tokens = count_tokens(text)
        result = truncate_to_token_limit(text, tokens)
        assert result == text


class TestFindIdentityColumn:
    def test_prefers_higher_cardinality_name(self):
        """podRef.name (unique) should beat network.name (constant 'eth0')."""
        cols = ["network.name", "podRef.name", "cpu.usageNanoCores"]
        arr = [
            {"network": {"name": "eth0"}, "podRef": {"name": "pod-a"}, "cpu": {"usageNanoCores": 100}},
            {"network": {"name": "eth0"}, "podRef": {"name": "pod-b"}, "cpu": {"usageNanoCores": 200}},
            {"network": {"name": "eth0"}, "podRef": {"name": "pod-c"}, "cpu": {"usageNanoCores": 300}},
        ]
        assert find_identity_column(cols, arr) == "podRef.name"

    def test_empty_vs_unique_name(self):
        """Empty-valued column loses to unique-valued column."""
        cols = ["network.name", "podRef.name"]
        arr = [
            {"network": {"name": ""}, "podRef": {"name": "pod-a"}},
            {"network": {"name": ""}, "podRef": {"name": "pod-b"}},
        ]
        assert find_identity_column(cols, arr) == "podRef.name"

    def test_no_arr_falls_back_to_first_match(self):
        """Without arr, first column matching keyword wins (backwards compat)."""
        cols = ["network.name", "podRef.name"]
        assert find_identity_column(cols) == "network.name"

    def test_fallback_to_first_col(self):
        """No keyword match returns first column."""
        cols = ["cpu.usageNanoCores", "memory.rssBytes"]
        assert find_identity_column(cols) == "cpu.usageNanoCores"


class TestIsKvArray:
    def test_valid_kv_array(self):
        arr = [{"Key": "Name", "Value": "web"}, {"Key": "Env", "Value": "prod"}]
        assert is_kv_array(arr) is True

    def test_empty_array(self):
        assert is_kv_array([]) is False

    def test_non_dict_elements(self):
        assert is_kv_array(["a", "b"]) is False

    def test_extra_keys(self):
        arr = [{"Key": "Name", "Value": "web", "Extra": "x"}]
        assert is_kv_array(arr) is False

    def test_wrong_key_names(self):
        arr = [{"key": "Name", "value": "web"}]
        assert is_kv_array(arr) is False

    def test_numeric_value(self):
        arr = [{"Key": "Port", "Value": 8080}]
        assert is_kv_array(arr) is True

    def test_non_string_key(self):
        arr = [{"Key": 123, "Value": "web"}]
        assert is_kv_array(arr) is False

    def test_single_element(self):
        arr = [{"Key": "Name", "Value": "web"}]
        assert is_kv_array(arr) is True

    def test_not_a_list(self):
        assert is_kv_array("not a list") is False


class TestPivotKvFields:
    def test_basic_pivot(self):
        items = [
            {"id": "i-1", "Tags": [{"Key": "Name", "Value": "web"}, {"Key": "Env", "Value": "prod"}]},
            {"id": "i-2", "Tags": [{"Key": "Name", "Value": "api"}, {"Key": "Env", "Value": "staging"}]},
        ]
        result = pivot_kv_fields(items)
        assert result[0]["Tags.Env"] == "prod"
        assert result[0]["Tags.Name"] == "web"
        assert result[1]["Tags.Env"] == "staging"
        assert result[1]["Tags.Name"] == "api"
        # Original Tags list should be gone
        assert "Tags" not in result[0]

    def test_missing_keys_filled(self):
        items = [
            {"id": "i-1", "Tags": [{"Key": "Name", "Value": "web"}]},
            {"id": "i-2", "Tags": [{"Key": "Name", "Value": "api"}, {"Key": "Env", "Value": "prod"}]},
        ]
        result = pivot_kv_fields(items)
        assert result[0]["Tags.Env"] == ""
        assert result[0]["Tags.Name"] == "web"
        assert result[1]["Tags.Env"] == "prod"

    def test_noop_passthrough(self):
        items = [
            {"id": "i-1", "status": "running"},
            {"id": "i-2", "status": "stopped"},
        ]
        result = pivot_kv_fields(items)
        assert result == items

    def test_mixed_kv_and_non_kv(self):
        items = [
            {"id": "i-1", "Tags": [{"Key": "Name", "Value": "web"}], "ports": [80, 443]},
            {"id": "i-2", "Tags": [{"Key": "Name", "Value": "api"}], "ports": [8080]},
        ]
        result = pivot_kv_fields(items)
        assert result[0]["Tags.Name"] == "web"
        assert result[0]["ports"] == [80, 443]  # non-KV list left untouched

    def test_empty_input(self):
        assert pivot_kv_fields([]) == []


class TestEc2TagsPivot:
    """Integration test with EC2-like nested data."""

    def test_tags_become_columns(self):
        data = {
            "Reservations": [
                {
                    "ReservationId": "r-001",
                    "Instances": [
                        {
                            "InstanceId": "i-aaa",
                            "State": {"Name": "running"},
                            "Tags": [
                                {"Key": "Name", "Value": "web-1"},
                                {"Key": "Environment", "Value": "production"},
                            ],
                        },
                        {
                            "InstanceId": "i-bbb",
                            "State": {"Name": "stopped"},
                            "Tags": [
                                {"Key": "Name", "Value": "web-2"},
                                {"Key": "Environment", "Value": "staging"},
                            ],
                        },
                    ],
                },
                {
                    "ReservationId": "r-002",
                    "Instances": [
                        {
                            "InstanceId": "i-ccc",
                            "State": {"Name": "running"},
                            "Tags": [
                                {"Key": "Name", "Value": "api-1"},
                                {"Key": "Environment", "Value": "production"},
                                {"Key": "Team", "Value": "backend"},
                            ],
                        },
                    ],
                },
            ],
        }
        result = condense_text(data)
        # Pivoted tag columns should appear
        assert "Tags.Name" in result
        assert "Tags.Environment" in result
        assert "web-1" in result
        assert "production" in result
        assert "api-1" in result
        # Should NOT have a separate sub-table for Tags
        assert "Instances.Tags" not in result


class TestDeprecatedAliases:
    def test_condense_json_warns(self):
        with pytest.warns(DeprecationWarning, match="condense_json.*deprecated"):
            result = condense_json({"a": 1})
        assert "a" in result

    def test_toon_encode_json_warns(self):
        with pytest.warns(DeprecationWarning, match="toon_encode_json.*deprecated"):
            result = toon_encode_json({"a": 1})
        assert "a" in result

    def test_condense_json_delegates(self):
        """Deprecated alias produces same output as condense_text."""
        data = [{"id": 1, "name": "alice"}, {"id": 2, "name": "bob"}]
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            old = condense_json(data)
        new = condense_text(data)
        assert old == new

    def test_toon_encode_json_delegates(self):
        """Deprecated alias produces same output as toon_encode."""
        data = {"x": 1}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            old = toon_encode_json(data)
        new = toon_encode(data)
        assert old == new
