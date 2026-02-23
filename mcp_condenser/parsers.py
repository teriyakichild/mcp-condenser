"""Extensible parser registry for structured text formats.

Ships with JSON and YAML parsers. Additional formats (CSV, XML, TOML, etc.)
can be registered via ``register_parser()``.
"""

import json
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


# ── registry ─────────────────────────────────────────────────────────────

PARSER_REGISTRY: list[Parser] = [
    Parser(name="json", try_parse=_try_json),
    Parser(name="yaml", try_parse=_try_yaml),
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
