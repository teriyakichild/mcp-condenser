"""mcp-condenser — compress verbose structured text tool responses into compact TOON text."""

from mcp_condenser.condenser import (
    condense_json,  # deprecated
    condense_text,
    count_tokens,
    stats,
    toon_encode,
    toon_encode_json,  # deprecated
    truncate_to_token_limit,
)
from mcp_condenser.parsers import (
    PARSER_REGISTRY,
    Parser,
    parse_input,
    register_parser,
)

__all__ = [
    "condense_text",
    "toon_encode",
    "condense_json",  # deprecated
    "toon_encode_json",  # deprecated
    "parse_input",
    "count_tokens",
    "stats",
    "truncate_to_token_limit",
    "Parser",
    "PARSER_REGISTRY",
    "register_parser",
]
