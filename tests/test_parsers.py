"""Tests for the extensible parser registry."""

import pytest

from mcp_condenser.parsers import (
    PARSER_REGISTRY,
    Parser,
    parse_input,
    register_parser,
)


class TestParserRegistry:
    def test_default_registry_order(self):
        names = [p.name for p in PARSER_REGISTRY]
        assert names[0] == "json"
        assert names[1] == "yaml"

    def test_registry_has_at_least_two(self):
        assert len(PARSER_REGISTRY) >= 2


class TestRegisterParser:
    def test_append(self):
        original_len = len(PARSER_REGISTRY)
        dummy = Parser(name="dummy", try_parse=lambda t: None)
        register_parser(dummy)
        try:
            assert PARSER_REGISTRY[-1] is dummy
            assert len(PARSER_REGISTRY) == original_len + 1
        finally:
            PARSER_REGISTRY.pop()

    def test_priority_insert(self):
        original_len = len(PARSER_REGISTRY)
        dummy = Parser(name="dummy_priority", try_parse=lambda t: None)
        register_parser(dummy, priority=0)
        try:
            assert PARSER_REGISTRY[0] is dummy
            assert len(PARSER_REGISTRY) == original_len + 1
        finally:
            PARSER_REGISTRY.pop(0)


class TestParseInputHint:
    def test_hint_json_skips_yaml(self):
        """With hint='json', JSON text is parsed as JSON."""
        data, fmt = parse_input('{"a": 1}', format_hint="json")
        assert fmt == "json"
        assert data == {"a": 1}

    def test_hint_yaml_tries_yaml_first(self):
        """With hint='yaml', YAML text is parsed as YAML."""
        data, fmt = parse_input("name: alice\nage: 30\n", format_hint="yaml")
        assert fmt == "yaml"
        assert data == {"name": "alice", "age": 30}

    def test_hint_falls_through_on_failure(self):
        """If hinted parser fails, other parsers still tried."""
        # This is valid JSON but we hint yaml — yaml parse would return
        # the dict too, but the key point is it shouldn't error
        data, fmt = parse_input('{"a": 1}', format_hint="yaml")
        # YAML can also parse JSON, so it may succeed as yaml or fall through to json
        assert data == {"a": 1}

    def test_hint_unknown_parser_falls_through(self):
        """Hint for non-existent parser name doesn't crash, falls through."""
        data, fmt = parse_input('{"a": 1}', format_hint="nonexistent")
        assert data == {"a": 1}
        assert fmt == "json"

    def test_no_hint_uses_registry_order(self):
        """Without hint, JSON is tried before YAML (registry order)."""
        data, fmt = parse_input('{"a": 1}')
        assert fmt == "json"


class TestParseInputNormalize:
    def test_normalize_runs_on_match(self):
        """When a parser with normalize matches, normalize is called."""
        calls = []

        def _try(text):
            if text.startswith("MAGIC:"):
                return {"raw": text[6:]}, "magic"
            return None

        def _norm(data):
            calls.append(data)
            data["normalized"] = True
            return data

        p = Parser(name="magic", try_parse=_try, normalize=_norm)
        register_parser(p)
        try:
            data, fmt = parse_input("MAGIC:hello")
            assert fmt == "magic"
            assert data["normalized"] is True
            assert len(calls) == 1
        finally:
            PARSER_REGISTRY.pop()

    def test_normalize_not_called_on_skip(self):
        """Normalize is not called when try_parse returns None."""
        calls = []

        def _try(text):
            return None

        def _norm(data):
            calls.append(data)
            return data

        p = Parser(name="never", try_parse=_try, normalize=_norm)
        register_parser(p)
        try:
            data, fmt = parse_input('{"a": 1}')
            assert fmt == "json"
            assert len(calls) == 0
        finally:
            PARSER_REGISTRY.pop()


class TestParseInputError:
    def test_error_lists_format_names(self):
        """ValueError message includes registered format names."""
        with pytest.raises(ValueError, match="json") as exc_info:
            parse_input("not valid at all {{::}")
        assert "yaml" in str(exc_info.value)

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            parse_input("")

    def test_plain_scalar_rejected(self):
        with pytest.raises(ValueError):
            parse_input("just a string")


class TestCsvParser:
    """Tests for the CSV/TSV parser."""

    def test_basic_csv(self):
        text = "name,age,city\nalice,30,nyc\nbob,25,sf\n"
        data, fmt = parse_input(text)
        assert fmt == "csv"
        assert len(data) == 2
        assert data[0]["name"] == "alice"
        assert data[0]["age"] == 30
        assert data[1]["city"] == "sf"

    def test_tsv(self):
        text = "name\tage\tcity\nalice\t30\tnyc\nbob\t25\tsf\n"
        data, fmt = parse_input(text)
        assert fmt == "csv"
        assert data[0]["name"] == "alice"
        assert data[0]["age"] == 30

    def test_type_inference_int_float_none(self):
        text = "a,b,c,d\n1,2.5,,hello\n"
        data, fmt = parse_input(text)
        assert fmt == "csv"
        assert data[0]["a"] == 1
        assert isinstance(data[0]["a"], int)
        assert data[0]["b"] == 2.5
        assert isinstance(data[0]["b"], float)
        assert data[0]["c"] is None
        assert data[0]["d"] == "hello"

    def test_single_line_rejected(self):
        """Header-only CSV (no data rows) should not match."""
        with pytest.raises(ValueError):
            parse_input("name,age,city\n")

    def test_single_column_rejected(self):
        """A single-column CSV is not useful structured data."""
        with pytest.raises(ValueError):
            parse_input("name\nalice\nbob\n")

    def test_json_preferred_over_csv(self):
        """JSON-like text should parse as JSON, not CSV."""
        text = '{"name": "alice", "age": 30}'
        data, fmt = parse_input(text)
        assert fmt == "json"

    def test_yaml_preferred_over_csv(self):
        """YAML-like text should parse as YAML, not CSV."""
        text = "name: alice\nage: 30\n"
        data, fmt = parse_input(text)
        assert fmt == "yaml"

    def test_format_hint_csv(self):
        """With hint='csv', CSV is tried first."""
        text = "name,age,city\nalice,30,nyc\nbob,25,sf\n"
        data, fmt = parse_input(text, format_hint="csv")
        assert fmt == "csv"
        assert len(data) == 2

    def test_registry_order(self):
        names = [p.name for p in PARSER_REGISTRY]
        assert names.index("csv") > names.index("json")
        assert names.index("csv") > names.index("yaml")
