"""mcp-condenser — compress verbose structured text tool responses into compact TOON text."""

from mcp_condenser.condenser import (
    condense_json,
    count_tokens,
    stats,
    toon_encode_json,
    truncate_to_token_limit,
)
from mcp_condenser.parsers import (
    PARSER_REGISTRY,
    Parser,
    parse_input,
    register_parser,
)

__all__ = [
    "condense_json",
    "toon_encode_json",
    "parse_input",
    "count_tokens",
    "stats",
    "truncate_to_token_limit",
    "Parser",
    "PARSER_REGISTRY",
    "register_parser",
]
