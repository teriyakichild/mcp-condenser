"""
condenser.py — JSON/YAML → compact TOON text for LLM consumption.

Two-layer design:
  1. Preprocessing: flatten, detect homogeneous arrays, elide zero/null/constant
     columns, cluster timestamps, extract nested arrays as sub-tables.
  2. Serialization: encode cleaned data with toon-python; prepend annotation lines.

Usage:
    python condenser.py input.json               # stdout
    python condenser.py input.yaml               # YAML too
    python condenser.py -                        # read stdin
    cat input.json | python condenser.py         # read stdin (no args)
    python condenser.py input.json -o out.txt -q
"""

import json, sys, re, argparse
import yaml
from dataclasses import dataclass
from typing import Any
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone

import toon_format


@dataclass
class Heuristics:
    """Toggle individual preprocessing heuristics on/off."""
    elide_all_zero: bool = True
    elide_all_null: bool = True
    elide_timestamps: bool = True
    elide_constants: bool = True
    group_tuples: bool = True
    max_tuple_size: int = 4
    max_table_columns: int = 0       # 0 = no limit
    elide_mostly_zero_pct: float = 0.0  # 0.0 = disabled

try:
    import tiktoken
    _enc = tiktoken.get_encoding("cl100k_base")
    def count_tokens(text: str) -> int:
        return len(_enc.encode(text))
    TOKEN_METHOD = "tiktoken/cl100k_base"
except Exception:
    def count_tokens(text: str) -> int:
        return len(text) // 4
    TOKEN_METHOD = "len/4 estimate"


# ── input parsing ─────────────────────────────────────────────────────────

def parse_input(text: str) -> tuple[Any, str]:
    """Parse text as JSON or YAML.

    Returns (parsed_data, format_name).
    Raises ValueError if neither format parses successfully.
    """
    # Try JSON first — it's stricter and faster
    try:
        return json.loads(text), "json"
    except (json.JSONDecodeError, TypeError):
        pass

    # Fall back to YAML
    try:
        data = yaml.safe_load(text)
        # yaml.safe_load returns str for plain scalars and None for empty —
        # only accept dicts/lists as meaningful structured data
        if isinstance(data, (dict, list)):
            return data, "yaml"
    except yaml.YAMLError:
        pass

    raise ValueError("Input is not valid JSON or YAML")


# ── helpers ──────────────────────────────────────────────────────────────────

def classify(val: Any) -> str:
    if val is None:   return "null"
    if isinstance(val, bool):  return "bool"
    if isinstance(val, (int, float)):  return "number"
    if isinstance(val, str):   return "string"
    if isinstance(val, list):  return "array"
    if isinstance(val, dict):  return "object"
    return "unknown"


def flatten(obj: dict, pfx: str = "") -> OrderedDict:
    """Flatten nested dict into dot-notation keys. Arrays kept as-is."""
    out = OrderedDict()
    for k, v in obj.items():
        key = f"{pfx}.{k}" if pfx else k
        if isinstance(v, dict):
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


def fmt(val: Any) -> str:
    if val is None: return ""
    if isinstance(val, bool): return str(val).lower()
    if isinstance(val, float) and val == int(val): return str(int(val))
    return str(val)


def is_iso_ts(s: str) -> bool:
    return isinstance(s, str) and re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", s) is not None


def parse_ts(s: str) -> datetime | None:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


def is_homogeneous_array(arr: list) -> bool:
    """Check if array is a uniform list of dicts suitable for tabular rendering."""
    if not arr or not all(isinstance(x, dict) for x in arr):
        return False
    if len(arr) < 2:
        return False  # single-item arrays render as objects
    union = set()
    for item in arr:
        union.update(k for k, v in flatten(item).items() if not isinstance(v, list))
    if len(union) < 2:
        return False  # need at least 2 common scalar keys
    common = set(union)
    for item in arr:
        common &= set(k for k, v in flatten(item).items() if not isinstance(v, list))
    return len(common) >= len(union) * 0.6


def union_columns(arr: list) -> list[str]:
    """Get all scalar (non-array) columns across all items."""
    keys = OrderedDict()
    for item in arr:
        for k, v in flatten(item).items():
            if not isinstance(v, list):
                keys[k] = True
    return list(keys)


def find_identity_column(cols: list[str], arr: list | None = None) -> str | None:
    """Find the best identity column for back-references.

    When *arr* is provided and multiple columns match the same keyword,
    the column with the highest cardinality (distinct non-empty values)
    wins.  Falls back to first-match when arr is None.
    """
    id_kw = ["name", "id", "uid"]
    for kw in id_kw:
        matches = [c for c in cols if c.split(".")[-1].lower() == kw]
        if not matches:
            continue
        if len(matches) == 1 or arr is None:
            return matches[0]
        # Pick the column with the most distinct non-empty values
        def _cardinality(col: str) -> int:
            vals = {fmt(flatten(item).get(col)) for item in arr}
            vals.discard("")
            return len(vals)
        return max(matches, key=_cardinality)
    return cols[0] if cols else None


# ── column analysis ──────────────────────────────────────────────────────────

def analyze_columns(arr: list, cols: list[str]) -> dict:
    info = {}
    for col in cols:
        fmted = [fmt(flatten(item).get(col)) for item in arr]
        unique = set(fmted)
        raw_vals = [flatten(item).get(col) for item in arr]

        all_ts = all(is_iso_ts(str(v)) for v in raw_vals if v is not None)
        ts_cluster = False
        ts_center = None
        if all_ts:
            parsed = [parse_ts(str(v)) for v in raw_vals if v is not None]
            parsed = [p for p in parsed if p is not None]
            if parsed:
                span = (max(parsed) - min(parsed)).total_seconds()
                ts_cluster = span <= 60
                if ts_cluster:
                    mid_idx = len(parsed) // 2
                    ts_center = sorted(parsed)[mid_idx].isoformat().replace("+00:00", "Z")

        info[col] = {
            "fmted": fmted,
            "unique": unique,
            "is_all_zero": unique <= {"0", "", "0.0"},
            "is_all_null": unique <= {""},
            "is_constant": len(unique) == 1,
            "const_val": fmted[0] if len(unique) == 1 else None,
            "is_timestamp": all_ts,
            "ts_clustered": ts_cluster,
            "ts_center": ts_center,
            "raw": raw_vals,
        }
    return info


# ── tuple grouping (type-aware) ─────────────────────────────────────────────

def detect_numeric_tuples(cols: list[str], col_info: dict) -> dict[str, list[str]]:
    """Group columns with shared prefix where ALL leaves are numeric."""
    groups = defaultdict(list)
    for col in cols:
        parts = col.rsplit(".", 1)
        if len(parts) == 2:
            prefix, leaf = parts
            groups[prefix].append(col)

    tuples = {}
    for prefix, members in groups.items():
        if len(members) < 3:
            continue
        if all(
            not col_info[m]["is_timestamp"]
            and col_info[m]["unique"] - {""} == set()
            or all(
                re.match(r"^-?\d+\.?\d*$", v) or v == ""
                for v in col_info[m]["fmted"]
            )
            for m in members
        ):
            tuples[prefix] = members
    return tuples


# ── smart column ordering ───────────────────────────────────────────────────

def order_columns(cols: list[str]) -> list[str]:
    id_kw = {"name", "id", "ref", "uid", "namespace", "label", "nodename"}
    ids, rest = [], []
    for c in cols:
        if c.split(".")[-1].lower() in id_kw:
            ids.append(c)
        else:
            rest.append(c)
    return ids + rest


# ── preprocessing + TOON rendering ──────────────────────────────────────────

def extract_array_fields(arr: list, cols: list[str]) -> tuple[list[str], dict]:
    """Find array-valued fields in items, return (remaining_cols, extracted).
    extracted maps field_name -> list of (parent_id, sub_items)."""
    array_cols = set()
    for item in arr:
        fl = flatten(item)
        for k, v in fl.items():
            if isinstance(v, list):
                array_cols.add(k)

    # also check non-flattened arrays at top level of each item
    for item in arr:
        for k, v in item.items():
            if isinstance(v, list):
                # flatten won't nest into arrays, but we may have top-level arrays
                pass  # already caught by flatten

    remaining = [c for c in cols if c not in array_cols]
    return remaining, array_cols


def preprocess_table(name: str, arr: list, heuristics: Heuristics | None = None) -> tuple[list[str], list[dict], list[tuple[str, list[str]]]]:
    """Analyze and clean a homogeneous array.

    Returns:
        (annotations, cleaned_rows_as_list_of_ordered_values, final_columns)
        where final_columns is list of (header, [source_cols])
    """
    if heuristics is None:
        heuristics = Heuristics()

    cols = order_columns(union_columns(arr))
    info = analyze_columns(arr, cols)

    annotations = []
    elided = set()

    # 1) Elide all-zero
    if heuristics.elide_all_zero:
        zc = [c for c in cols if info[c]["is_all_zero"] and not info[c]["is_all_null"]]
        if zc:
            annotations.append(f"  elided all_zero: {', '.join(zc)}")
            elided.update(zc)

    # 2) Elide all-null
    if heuristics.elide_all_null:
        nc = [c for c in cols if info[c]["is_all_null"] and c not in elided]
        if nc:
            annotations.append(f"  elided all_null: {', '.join(nc)}")
            elided.update(nc)

    # 2.5) Elide mostly-zero columns (threshold-based)
    if heuristics.elide_mostly_zero_pct > 0:
        id_col = find_identity_column(cols, arr)
        for c in cols:
            if c in elided or info[c]["is_all_zero"] or info[c]["is_all_null"]:
                continue
            fmted = info[c]["fmted"]
            n_total = len(fmted)
            if n_total == 0:
                continue
            n_zero = sum(1 for v in fmted if v in ("0", ""))
            if n_zero / n_total >= heuristics.elide_mostly_zero_pct:
                # Build outlier annotation with identity labels
                non_zero = []
                for i, v in enumerate(fmted):
                    if v not in ("0", ""):
                        label = fmt(flatten(arr[i]).get(id_col)) if id_col else str(i)
                        non_zero.append(f"{label}={v}")
                if non_zero:
                    annotations.append(f"  elided mostly_zero: {c} (non-zero: {', '.join(non_zero)})")
                else:
                    annotations.append(f"  elided mostly_zero: {c}")
                elided.add(c)

    # 3) Elide clustered timestamps
    if heuristics.elide_timestamps:
        for c in cols:
            if c in elided:
                continue
            if info[c]["ts_clustered"] and info[c]["is_constant"]:
                annotations.append(f"  elided constant {c}: {info[c]['const_val']}")
                elided.add(c)
            elif info[c]["ts_clustered"]:
                center = info[c]["ts_center"] or info[c]["raw"][0]
                annotations.append(f"  elided timestamp_cluster {c}: ~{center} (within 60s)")
                elided.add(c)

    # 4) Elide other constant columns
    if heuristics.elide_constants:
        for c in cols:
            if c not in elided and info[c]["is_constant"] and not info[c]["is_all_zero"] and not info[c]["is_all_null"]:
                annotations.append(f"  elided constant {c}: {info[c]['const_val']}")
                elided.add(c)

    # 5) Detect numeric tuples from remaining columns
    remaining = [c for c in cols if c not in elided]
    if heuristics.group_tuples:
        tuples = detect_numeric_tuples(remaining, info)
    else:
        tuples = {}

    tuple_members = set()
    tuple_map = OrderedDict()
    for prefix, members in tuples.items():
        live = [m for m in members if m not in elided]
        if len(live) >= 3 and len(live) <= heuristics.max_tuple_size:
            leaves = [m.rsplit(".", 1)[1] for m in live]
            header = f"{prefix}({','.join(leaves)})"
            tuple_map[header] = live
            tuple_members.update(live)

    # 6) Build final column list: (header, [source_cols])
    final = []
    seen = set()
    for c in cols:
        if c in elided or c in seen:
            continue
        if c in tuple_members:
            for h, members in tuple_map.items():
                if c in members and h not in seen:
                    final.append((h, members))
                    seen.add(h)
                    seen.update(members)
                    break
        else:
            final.append((c, [c]))
            seen.add(c)

    # 6.5) Cap table width if max_table_columns is set
    if heuristics.max_table_columns > 0 and len(final) > heuristics.max_table_columns:
        # Identity columns (name, id, namespace, uid) are ordered first by order_columns,
        # so they survive the cap naturally. Just truncate from the right.
        kept = final[:heuristics.max_table_columns]
        overflow = final[heuristics.max_table_columns:]
        overflow_names = [h for h, _ in overflow]
        annotations.append(f"  elided overflow ({len(overflow_names)} columns exceed limit): {', '.join(overflow_names)}")
        final = kept

    # 7) Build cleaned rows as dicts for TOON encoding
    cleaned_rows = []
    for item in arr:
        fl = flatten(item)
        row = OrderedDict()
        for header, srcs in final:
            if len(srcs) == 1:
                val = fl.get(srcs[0])
                if val is None:
                    row[header] = ""
                elif isinstance(val, bool):
                    row[header] = val
                else:
                    row[header] = val
            else:
                # tuple: join as comma-separated string
                row[header] = ",".join(fmt(fl.get(s)) for s in srcs)
        cleaned_rows.append(row)

    return annotations, cleaned_rows, final


def render_table(name: str, arr: list, heuristics: Heuristics | None = None) -> list[str]:
    """Render a homogeneous array as TOON table block(s).

    Returns list of text blocks (parent table + any extracted sub-tables).
    """
    if not arr:
        return [f"--- {name} ---\n(empty)"]

    blocks = []

    # Extract nested array fields before column analysis
    all_flat = [flatten(item) for item in arr]
    array_fields = set()
    for fl in all_flat:
        for k, v in fl.items():
            if isinstance(v, list):
                array_fields.add(k)

    # Determine parent identity column for back-references
    scalar_cols = order_columns(union_columns(arr))
    id_col = find_identity_column(scalar_cols, arr)

    # Collect sub-table data for each array field
    sub_tables = {}
    for af in sorted(array_fields):
        sub_items = []
        for item in arr:
            fl = flatten(item)
            parent_id = fmt(fl.get(id_col, "")) if id_col else ""
            arr_val = fl.get(af, [])
            if isinstance(arr_val, list):
                for sub in arr_val:
                    if isinstance(sub, dict):
                        tagged = OrderedDict()
                        tagged[f"_parent.{id_col}"] = parent_id
                        tagged.update(flatten(sub))
                        sub_items.append(tagged)
        if sub_items and len(sub_items) >= 2:
            # Check if these form a homogeneous collection
            sub_keys = set()
            for si in sub_items:
                sub_keys.update(k for k, v in si.items() if not isinstance(v, list))
            common = set(sub_keys)
            for si in sub_items:
                common &= set(k for k, v in si.items() if not isinstance(v, list))
            if len(common) >= 2:
                sub_tables[af] = sub_items

    # Now preprocess the parent table (array fields are excluded by union_columns
    # since flatten keeps arrays as-is and union_columns skips them)
    annotations, cleaned_rows, final_cols = preprocess_table(name, arr, heuristics)

    # Encode with TOON
    toon_text = toon_format.encode(cleaned_rows)

    # Build parent block
    header = f"--- {name} ({len(arr)} rows) ---"
    parts = [header]
    parts.extend(annotations)
    parts.append(toon_text)
    blocks.append("\n".join(parts))

    # Render sub-tables
    for af, sub_items in sorted(sub_tables.items()):
        sub_name = f"{name}.{af}"
        # Wrap sub_items back into dicts for render_table recursion
        # sub_items are already flat dicts, wrap in list
        sub_annotations, sub_cleaned, sub_final = preprocess_table(sub_name, [dict(si) for si in sub_items], heuristics)
        sub_toon = toon_format.encode(sub_cleaned)

        sub_header = f"--- {sub_name} ({len(sub_items)} rows) ---"
        sub_parts = [sub_header]
        sub_parts.extend(sub_annotations)
        sub_parts.append(sub_toon)
        blocks.append("\n".join(sub_parts))

    return blocks


def render_scalars(name: str, flat: OrderedDict) -> str:
    """Encode scalar key-value pairs with TOON."""
    header = f"--- {name} (scalars) ---"
    toon_text = toon_format.encode(dict(flat))
    return f"{header}\n{toon_text}"


# ── recursive condenser ─────────────────────────────────────────────────────

def condense(name: str, obj: Any, heuristics: Heuristics | None = None) -> list[str]:
    blocks = []
    t = classify(obj)

    if t in ("string", "number", "bool", "null"):
        blocks.append(f"{name}: {fmt(obj)}")

    elif t == "object":
        scalars = OrderedDict()
        arrays = OrderedDict()
        fl = flatten(obj)
        for k, v in fl.items():
            if isinstance(v, list):
                arrays[k] = v
            else:
                scalars[k] = v

        if scalars:
            blocks.append(render_scalars(name, scalars))
        for ak, av in arrays.items():
            an = f"{name}.{ak}" if name else ak
            if is_homogeneous_array(av):
                blocks.extend(render_table(an, av, heuristics))
            elif av and isinstance(av[0], dict):
                for i, item in enumerate(av):
                    blocks.extend(condense(f"{an}[{i}]", item, heuristics))
            else:
                blocks.append(f"{an}: {json.dumps(av)}")

    elif t == "array":
        if is_homogeneous_array(obj):
            blocks.extend(render_table(name, obj, heuristics))
        elif obj and isinstance(obj[0], dict):
            for i, item in enumerate(obj):
                blocks.extend(condense(f"{name}[{i}]", item, heuristics))
        else:
            blocks.append(f"{name}: {json.dumps(obj)}")

    return blocks


def _is_scalar_line(block: str) -> bool:
    """True if block is a single key: value line (no header/section)."""
    return "\n" not in block and not block.startswith("---")


def _join_blocks(blocks: list[str]) -> str:
    """Join blocks, grouping consecutive scalar lines with single newlines."""
    if not blocks:
        return ""
    parts = []
    scalar_group: list[str] = []
    for block in blocks:
        if _is_scalar_line(block):
            scalar_group.append(block)
        else:
            if scalar_group:
                parts.append("\n".join(scalar_group))
                scalar_group = []
            parts.append(block)
    if scalar_group:
        parts.append("\n".join(scalar_group))
    return "\n\n".join(parts)


def condense_json(data: Any, heuristics: Heuristics | None = None) -> str:
    if isinstance(data, dict):
        blocks = []
        for k in data:
            blocks.extend(condense(k, data[k], heuristics))
        return _join_blocks(blocks)
    return _join_blocks(condense("root", data, heuristics))


def toon_encode_json(data: Any) -> str:
    """Convert JSON data directly to TOON format without semantic preprocessing."""
    return toon_format.encode(data)


# ── truncation ────────────────────────────────────────────────────────────────

def truncate_to_token_limit(text: str, max_tokens: int) -> str:
    """Truncate text to fit within a token limit.

    If the text is within the limit, returns it unchanged.
    If over, binary-searches for the longest character prefix that fits
    within max_tokens (minus overhead for the truncation notice), then
    appends a truncation message.
    """
    if max_tokens <= 0:
        return text

    orig_tokens = count_tokens(text)
    if orig_tokens <= max_tokens:
        return text

    # Build the truncation notice template (with placeholder counts)
    # to measure its overhead; actual message is built at the end.
    sample_notice = (
        f"\n\n[truncated: output exceeded {max_tokens} token limit"
        f" — {orig_tokens} tokens reduced to ~{max_tokens}]"
    )
    notice_overhead = count_tokens(sample_notice)
    target = max_tokens - notice_overhead
    if target <= 0:
        target = 1

    # Binary search for longest prefix that fits within target tokens
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if count_tokens(text[:mid]) <= target:
            lo = mid
        else:
            hi = mid - 1

    truncated = text[:lo]
    final_tokens = count_tokens(truncated) + notice_overhead
    notice = (
        f"\n\n[truncated: output exceeded {max_tokens} token limit"
        f" — {orig_tokens} tokens reduced to ~{final_tokens}]"
    )
    return truncated + notice


# ── stats ────────────────────────────────────────────────────────────────────

def stats(orig: str, cond: str, orig_tok: int | None = None) -> dict:
    oc, cc = len(orig), len(cond)
    ot = orig_tok if orig_tok is not None else count_tokens(orig)
    ct = count_tokens(cond)
    return {
        "orig_chars": oc, "cond_chars": cc,
        "orig_tok": ot, "cond_tok": ct,
        "char_pct": round((1 - cc/oc)*100, 1) if oc else 0,
        "tok_pct": round((1 - ct/ot)*100, 1) if ot else 0,
        "method": TOKEN_METHOD,
    }


# ── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Condense JSON into compact TOON text for LLM consumption."
    )
    parser.add_argument(
        "input", nargs="?", default="-",
        help="Input JSON file (default: stdin, or use '-' explicitly)"
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="Output file (default: stdout)"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true",
        help="Suppress compression stats on stderr"
    )
    args = parser.parse_args()

    if args.input == "-":
        raw = sys.stdin.read()
    else:
        with open(args.input) as f:
            raw = f.read()
    data, input_fmt = parse_input(raw)

    orig = raw
    result = condense_json(data)

    if not args.quiet:
        s = stats(orig, result)
        print(f"=== Compression Stats ({s['method']}) ===", file=sys.stderr)
        print(f"Original:  {s['orig_chars']:>8,} chars  ({s['orig_tok']:,} tokens)", file=sys.stderr)
        print(f"Condensed: {s['cond_chars']:>8,} chars  ({s['cond_tok']:,} tokens)", file=sys.stderr)
        print(f"Reduction: {s['char_pct']}% chars, {s['tok_pct']}% tokens", file=sys.stderr)
        print(f"{'=' * 42}", file=sys.stderr)

    if args.output:
        with open(args.output, "w") as f:
            f.write(result)
        if not args.quiet:
            print(f"→ {args.output}", file=sys.stderr)
    else:
        print(result)


if __name__ == "__main__":
    main()
