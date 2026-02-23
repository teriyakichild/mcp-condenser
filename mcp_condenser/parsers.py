"""Extensible parser registry for structured text formats.

Ships with JSON and YAML parsers. Additional formats (CSV, XML, TOML, etc.)
can be registered via ``register_parser()``.
"""

import csv
import io
import json
import xml.etree.ElementTree as ET
from collections import Counter
from typing import Any, Callable, NamedTuple

import yaml


class Parser(NamedTuple):
    """A pluggable input parser.

    Attributes:
        name: Short identifier used in format hints and error messages.
        try_parse: ``(text) -> (data, name) | None``.  Return parsed data and
            the parser name on success, or ``None`` to signal "not my format".
        normalize: Optional post-parse transform ``(data) -> data``.
    """
    name: str
    try_parse: Callable[[str], tuple[Any, str] | None]
    normalize: Callable[[Any], Any] | None = None


# ── built-in parsers ─────────────────────────────────────────────────────

def _try_json(text: str) -> tuple[Any, str] | None:
    try:
        return json.loads(text), "json"
    except (json.JSONDecodeError, TypeError):
        return None


def _try_yaml(text: str) -> tuple[Any, str] | None:
    try:
        data = yaml.safe_load(text)
        # yaml.safe_load returns str for plain scalars and None for empty —
        # only accept dicts/lists as meaningful structured data
        if isinstance(data, (dict, list)):
            return data, "yaml"
    except yaml.YAMLError:
        pass
    return None


def _try_csv(text: str) -> tuple[Any, str] | None:
    """Detect and parse CSV/TSV text into a list of dicts.

    Rejects single-line input (header-only, no data rows) and text that
    looks like it has fewer than 2 columns.
    """
    # Need at least a header + one data row
    lines = text.strip().splitlines()
    if len(lines) < 2:
        return None

    try:
        # Sniff dialect from a sample (first 8KB)
        sample = text[:8192]
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t|;")
    except csv.Error:
        return None

    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if reader.fieldnames is None or len(reader.fieldnames) < 2:
        return None

    rows = list(reader)
    if not rows:
        return None

    return rows, "csv"


def _normalize_csv(data: list[dict[str, str]]) -> list[dict[str, Any]]:
    """Infer types for CSV string values: int, float, None for empty."""
    out: list[dict[str, Any]] = []
    for row in data:
        new: dict[str, Any] = {}
        for k, v in row.items():
            if v is None or v == "":
                new[k] = None
            else:
                # Try int, then float, fall back to string
                try:
                    new[k] = int(v)
                except ValueError:
                    try:
                        new[k] = float(v)
                    except ValueError:
                        new[k] = v
        out.append(new)
    return out


def _xml_elem_to_dict(elem: ET.Element) -> dict[str, Any]:
    """Convert an XML element to a nested dict.

    Rules:
    - Attributes become ``@attr`` keys.
    - Repeated child tags are grouped into a list.
    - A leaf element with only text becomes a plain string (after type coercion).
    - Mixed text + children: text stored under ``#text``.
    """
    d: dict[str, Any] = {}

    # Attributes
    for k, v in elem.attrib.items():
        d[f"@{k}"] = _coerce_xml_value(v)

    # Group children by tag
    child_counts: Counter[str] = Counter(c.tag for c in elem)
    child_groups: dict[str, list[Any]] = {}
    for child in elem:
        tag = child.tag
        converted = _xml_elem_to_dict(child)
        child_groups.setdefault(tag, []).append(converted)

    for tag, items in child_groups.items():
        if child_counts[tag] == 1:
            d[tag] = items[0]
        else:
            d[tag] = items

    # Text content
    text = (elem.text or "").strip()
    if text:
        if d:
            d["#text"] = _coerce_xml_value(text)
        else:
            return _coerce_xml_value(text)

    return d


def _coerce_xml_value(v: str) -> Any:
    """Best-effort type coercion for XML text values."""
    if v == "":
        return None
    try:
        return int(v)
    except ValueError:
        pass
    try:
        return float(v)
    except ValueError:
        pass
    if v.lower() == "true":
        return True
    if v.lower() == "false":
        return False
    return v


def _try_xml(text: str) -> tuple[Any, str] | None:
    """Detect and parse XML text into a dict structure."""
    stripped = text.strip()
    if not stripped.startswith("<"):
        return None
    try:
        root = ET.fromstring(stripped)
    except ET.ParseError:
        return None
    return _xml_elem_to_dict(root), "xml"


# ── registry ─────────────────────────────────────────────────────────────

PARSER_REGISTRY: list[Parser] = [
    Parser(name="json", try_parse=_try_json),
    Parser(name="yaml", try_parse=_try_yaml),
    Parser(name="csv", try_parse=_try_csv, normalize=_normalize_csv),
    Parser(name="xml", try_parse=_try_xml),
]


def register_parser(parser: Parser, *, priority: int | None = None) -> None:
    """Add a parser to the registry.

    Args:
        parser: The ``Parser`` to register.
        priority: Insert position (0 = highest priority).  When ``None`` the
            parser is appended (lowest priority, tried last).
    """
    if priority is None:
        PARSER_REGISTRY.append(parser)
    else:
        PARSER_REGISTRY.insert(priority, parser)


# ── public entry point ───────────────────────────────────────────────────

def parse_input(text: str, *, format_hint: str | None = None) -> tuple[Any, str]:
    """Parse *text* using the first matching parser in the registry.

    Args:
        text: Raw input string.
        format_hint: When set, the matching parser is tried first.  If it
            fails, the remaining parsers are tried in registry order.

    Returns:
        ``(parsed_data, format_name)``.

    Raises:
        ValueError: No registered parser could parse the input.
    """
    if format_hint is not None:
        # Try the hinted parser first
        for p in PARSER_REGISTRY:
            if p.name == format_hint:
                result = p.try_parse(text)
                if result is not None:
                    data, name = result
                    if p.normalize is not None:
                        data = p.normalize(data)
                    return data, name
                break  # hint didn't match — fall through to full scan

    # Full registry scan (skip the hinted parser if it already failed)
    for p in PARSER_REGISTRY:
        if format_hint is not None and p.name == format_hint:
            continue
        result = p.try_parse(text)
        if result is not None:
            data, name = result
            if p.normalize is not None:
                data = p.normalize(data)
            return data, name

    names = ", ".join(p.name for p in PARSER_REGISTRY)
    raise ValueError(f"Input is not valid {names}")
