"""
condenser.py — structured text → compact TOON text for LLM consumption.

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

import json, logging, math, sys, re, argparse, warnings
from dataclasses import dataclass
from typing import Any
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone

import toon_format

logger = logging.getLogger("mcp_condenser")

from mcp_condenser.parsers import parse_input  # noqa: F401 — re-export


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
    pivot_key_value: bool = True
    wide_table_threshold: int = 0       # 0 = disabled; tables wider switch format
    wide_table_format: str = "vertical" # "vertical" or "split"


PROFILES: dict[str, dict] = {
    "balanced": {"wide_table_threshold": 20, "wide_table_format": "split"},
    "compact": {"wide_table_threshold": 0, "elide_mostly_zero_pct": 0.8},
    "precise": {"wide_table_threshold": 15, "wide_table_format": "split"},
}


def resolve_profile(name: str = "balanced", **overrides) -> Heuristics:
    """Build a Heuristics instance from a named profile with optional overrides.

    Args:
        name: Profile name ("balanced", "compact", "precise").
              Unknown names fall back to Heuristics defaults.
        **overrides: Individual heuristic values that override the profile.
    """
    base = dict(PROFILES.get(name, {}))
    base.update(overrides)
    return Heuristics(**base)


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
    if isinstance(val, float) and math.isfinite(val) and val.is_integer() and abs(val) <= 2**53: return str(int(val))
    return str(val)


_ISO_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")


def is_iso_ts(s: str) -> bool:
    return isinstance(s, str) and _ISO_TS_RE.match(s) is not None


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


def is_kv_array(arr: list) -> bool:
    """Check if array is a list of {Key: str, Value: any} dicts (AWS tag convention)."""
    if not arr or not isinstance(arr, list):
        return False
    for item in arr:
        if not isinstance(item, dict):
            return False
        if set(item.keys()) != {"Key", "Value"}:
            return False
        if not isinstance(item["Key"], str):
            return False
    return True


def pivot_kv_fields(items: list[dict]) -> list[dict]:
    """Pivot Key-Value array fields into scalar columns on each item.

    For each field that is a KV array (every element is {Key: str, Value: any})
    across all items, replace it with scalar columns named ``field.key_name``.
    Missing keys get empty string. Non-KV list fields are left untouched.
    """
    if not items:
        return items

    # Find fields that are KV arrays across all items that have them
    kv_fields: dict[str, set[str]] = {}
    for item in items:
        for k, v in item.items():
            if isinstance(v, list) and is_kv_array(v):
                if k not in kv_fields:
                    kv_fields[k] = set()
                kv_fields[k].update(entry["Key"] for entry in v)

    if not kv_fields:
        return items

    result = []
    for item in items:
        new_item = OrderedDict()
        for k, v in item.items():
            if k in kv_fields and isinstance(v, list) and is_kv_array(v):
                lookup = {entry["Key"]: entry["Value"] for entry in v}
                for tag_key in sorted(kv_fields[k]):
                    new_item[f"{k}.{tag_key}"] = lookup.get(tag_key, "")
            else:
                new_item[k] = v
        # Fill in missing pivoted keys (item had no array for this field at all)
        for field, keys in kv_fields.items():
            if field not in item or not isinstance(item.get(field), list):
                for tag_key in sorted(keys):
                    col = f"{field}.{tag_key}"
                    if col not in new_item:
                        new_item[col] = ""
        result.append(new_item)
    return result


def union_columns(arr: list) -> list[str]:
    """Get all scalar (non-array) columns across all items."""
    keys = OrderedDict()
    for item in arr:
        for k, v in flatten(item).items():
            if not isinstance(v, list):
                keys[k] = True
    return list(keys)


def _col_matches_keyword(col: str, kw: str) -> bool:
    """Check if a column's last dot-segment matches the given keyword.

    Exact leaf matches (case-insensitive) always succeed.  For short
    identity keywords (``id``, ``uid``, ``name``) a tighter heuristic
    avoids false positives like ``valid`` matching ``id``:

    - separator before keyword: ``user_id``, ``node-name``
    - CamelCase boundary: ``InstanceId``, ``NodeName``, ``UserUID``
    """
    leaf_full = col.split(".")[-1]
    leaf = leaf_full.lower()
    kw = kw.lower()

    if leaf == kw:
        return True

    if kw in ("id", "uid", "name"):
        # Separator-based suffix: user_id, node-name
        for sep in ("_", "-"):
            if leaf.endswith(sep + kw):
                return True
        # CamelCase / acronym boundary: InstanceId, NodeName, UserUID
        for suffix in (kw.capitalize(), kw.upper()):
            if leaf_full.endswith(suffix):
                pos = len(leaf_full) - len(suffix)
                # Boundary = start of leaf, or CamelCase transition (lower→upper),
                # or non-alpha separator before the suffix.
                if pos == 0 or leaf_full[pos - 1].islower() or not leaf_full[pos - 1].isalnum():
                    return True
        return False

    return leaf.endswith(kw)


def _identity_score(col: str, values: set[str]) -> tuple[int, float, int]:
    """Score a column as an identity candidate.

    Returns (cardinality, -avg_value_length, -depth) so that ``max()``
    picks the column with the most distinct non-empty values, then the
    shortest average value (concise identifiers preferred), then the
    shallowest nesting depth (fewest dots).
    """
    avg_len = sum(len(v) for v in values) / max(len(values), 1)
    return (len(values), -avg_len, -col.count("."))


def _col_distinct_values(col: str, rows: list[dict], use_flatten: bool = False) -> set[str]:
    """Collect distinct non-empty formatted values for *col* across *rows*."""
    if use_flatten:
        vals = {fmt(flatten(item).get(col)) for item in rows}
    else:
        vals = {fmt(row.get(col)) for row in rows}
    vals.discard("")
    return vals


def find_identity_column(cols: list[str], arr: list | None = None) -> str | None:
    """Find the best identity column for back-references.

    When *arr* is provided and multiple columns match the same keyword,
    the column with the highest cardinality wins; ties are broken by
    shortest average value length (concise identifiers preferred), then
    shallowest depth (fewest dots).  Falls back to first-match when arr
    is None.
    """
    id_kw = ["name", "id", "uid"]
    for kw in id_kw:
        matches = [c for c in cols if _col_matches_keyword(c, kw)]
        if not matches:
            continue
        if len(matches) == 1 or arr is None:
            return matches[0]
        return max(matches, key=lambda c: _identity_score(c, _col_distinct_values(c, arr, use_flatten=True)))
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
    _order_kw = ("name", "id", "ref", "uid", "namespace", "label", "nodename")
    ids, rest = [], []
    for c in cols:
        if any(_col_matches_keyword(c, kw) for kw in _order_kw):
            ids.append(c)
        else:
            rest.append(c)
    return ids + rest


# ── preprocessing + TOON rendering ──────────────────────────────────────────

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
                row[header] = "" if val is None else val
            else:
                # tuple: join as comma-separated string
                row[header] = ",".join(fmt(fl.get(s)) for s in srcs)
        cleaned_rows.append(row)

    return annotations, cleaned_rows, final


def _find_identity_from_cleaned(headers: list[str], cleaned_rows: list[dict]) -> str | None:
    """Find best identity column from cleaned rows (post-preprocessing headers).

    Among columns whose names match common identity keywords ("name", "id",
    "uid"), prefer the one with highest cardinality; if tied, choose the
    column with the shortest average non-empty value length; if still tied,
    prefer the column with the shallowest nesting depth (fewest dots).
    """
    id_kw = ["name", "id", "uid"]
    for kw in id_kw:
        matches = [h for h in headers if _col_matches_keyword(h, kw)]
        if not matches:
            continue
        if len(matches) == 1:
            return matches[0]
        return max(matches, key=lambda c: _identity_score(c, _col_distinct_values(c, cleaned_rows)))
    return None


def render_vertical(name: str, arr: list, annotations: list[str], cleaned_rows: list[dict], final_cols: list[tuple[str, list[str]]]) -> str:
    """Render a wide table as vertical key-value blocks per row.

    Each row becomes a named section with indented key: value lines.
    """
    headers = [h for h, _ in final_cols]
    id_col = _find_identity_from_cleaned(headers, cleaned_rows)

    parts = [f"--- {name} ({len(arr)} rows) ---"]
    parts.extend(annotations)

    for i, row in enumerate(cleaned_rows):
        # Determine section label
        if id_col and id_col in row:
            label = fmt(row[id_col])
            if not label:
                label = f"row {i}"
        else:
            label = f"row {i}"
        parts.append("")
        parts.append(f"  [{label}]")
        for h in headers:
            if h == id_col:
                continue
            val = fmt(row.get(h))
            parts.append(f"  {h}: {val}")

    return "\n".join(parts)


def render_split(name: str, arr: list, annotations: list[str], cleaned_rows: list[dict], final_cols: list[tuple[str, list[str]]], heuristics: Heuristics) -> str:
    """Render a wide table as multiple narrow sub-tables grouped by column prefix.

    Columns are grouped by their first dotted segment. Identity columns are
    repeated in every sub-table for context.
    """
    headers = [h for h, _ in final_cols]

    # Pick the best identity columns to repeat in each sub-table.
    # Compute distinct values lazily, only for columns that match a keyword.
    _split_kw = ("name", "id", "ref", "uid", "namespace", "label", "nodename")
    _col_vals_cache: dict[str, set[str]] = {}
    identity_cols = []
    for kw in _split_kw:
        matches = [h for h in headers if _col_matches_keyword(h, kw)]
        if not matches:
            continue
        if len(matches) == 1:
            best = matches[0]
        else:
            for m in matches:
                if m not in _col_vals_cache:
                    _col_vals_cache[m] = _col_distinct_values(m, cleaned_rows)
            best = max(matches, key=lambda c: _identity_score(c, _col_vals_cache[c]))
        if best not in identity_cols:
            identity_cols.append(best)
        if len(identity_cols) >= 3:
            break

    # Group columns by top-level prefix
    groups: dict[str, list[str]] = OrderedDict()
    for h in headers:
        if h in identity_cols:
            continue
        if "." in h:
            prefix = h.split(".")[0]
        else:
            prefix = "_misc"
        groups.setdefault(prefix, []).append(h)

    # Merge single-column groups into _misc
    merged: dict[str, list[str]] = OrderedDict()
    for prefix, cols in groups.items():
        non_identity = [c for c in cols if c not in identity_cols]
        if len(non_identity) <= 1 and prefix != "_misc":
            merged.setdefault("_misc", []).extend(cols)
        else:
            merged[prefix] = cols
    groups = merged

    # Build output
    parts = [f"--- {name} ({len(arr)} rows) ---"]
    parts.extend(annotations)

    for prefix, cols in groups.items():
        sub_cols = identity_cols + cols
        # Build sub-rows
        sub_rows = []
        for row in cleaned_rows:
            sub_row = OrderedDict()
            for c in sub_cols:
                sub_row[c] = row.get(c, "")
            sub_rows.append(sub_row)

        sub_name = f"{name}.{prefix}" if prefix != "_misc" else f"{name}._misc"
        sub_toon = toon_format.encode(sub_rows)
        parts.append("")
        parts.append(f"--- {sub_name} ({len(arr)} rows) ---")
        parts.append(sub_toon)

    return "\n".join(parts)


def _inline_nested_array(arr_val: list) -> str | None:
    """Try to render a small nested array as a compact inline string.

    Returns a compact string like ``name:val name:val`` for small arrays of
    simple dicts, or ``name(v1,v2)`` when multiple value columns exist.
    Returns None if the array is too complex to inline.
    """
    MAX_INLINE_ITEMS = 10
    if not arr_val or not isinstance(arr_val, list):
        return None
    if len(arr_val) > MAX_INLINE_ITEMS:
        return None
    # All items must be simple dicts (no nested dicts/lists)
    for item in arr_val:
        if not isinstance(item, dict):
            return None
        for v in item.values():
            if isinstance(v, (dict, list)):
                return None
    # All items must share the same keys — bail if heterogeneous
    first_keys = set(arr_val[0].keys())
    for item in arr_val[1:]:
        if set(item.keys()) != first_keys:
            return None
    sample_keys = list(arr_val[0].keys())
    if len(sample_keys) < 2 or len(sample_keys) > 4:
        return None
    key_col = None
    for kw in ("name", "key", "label", "id"):
        for k in sample_keys:
            if k.lower() == kw:
                key_col = k
                break
        if key_col:
            break
    if not key_col:
        return None
    val_cols = sorted([k for k in sample_keys if k != key_col])
    parts = []
    for item in arr_val:
        k = fmt(item.get(key_col, ""))
        if len(val_cols) == 1:
            parts.append(f"{k}:{fmt(item.get(val_cols[0], ''))}")
        else:
            vals = ",".join(fmt(item.get(vc, "")) for vc in val_cols)
            parts.append(f"{k}({vals})")
    return " ".join(parts)


def _classify_array_shape(arr_val: list) -> str:
    """Classify an array's shape for residual diagnostics."""
    if not arr_val:
        return "empty"
    if all(isinstance(x, dict) for x in arr_val):
        if any(isinstance(v, (dict, list)) for x in arr_val for v in x.values()):
            return "complex-dicts"
        return "simple-dicts"
    if all(isinstance(x, list) for x in arr_val):
        return "array-of-arrays"
    if all(isinstance(x, (str, int, float, bool, type(None))) for x in arr_val):
        return "primitive-list"
    return "mixed"


def _log_residual(table_name: str, field: str, all_flat: list, id_col: str | None) -> None:
    """Log diagnostic info for a residual (fallback-rendered) array field."""
    rows_with_data = sum(
        1 for fl in all_flat
        if isinstance(fl.get(field), list) and fl[field]
    )
    # Classify shape from first non-empty value
    shape = "unknown"
    for fl in all_flat:
        v = fl.get(field)
        if isinstance(v, list) and v:
            shape = _classify_array_shape(v)
            break
    logger.debug(
        "residual field: %s.%s shape=%s rows=%d",
        table_name, field, shape, rows_with_data,
    )


def render_table(name: str, arr: list, heuristics: Heuristics | None = None) -> list[str]:
    """Render a homogeneous array as TOON table block(s).

    Returns list of text blocks (parent table + any extracted sub-tables).
    """
    if heuristics is None:
        heuristics = Heuristics()

    if not arr:
        return [f"--- {name} ---\n(empty)"]

    blocks = []

    # Flatten and optionally pivot KV arrays into scalar columns
    all_flat = [flatten(item) for item in arr]
    if heuristics.pivot_key_value:
        all_flat = pivot_kv_fields(all_flat)

    # Extract nested array fields before column analysis
    array_fields = set()
    for fl in all_flat:
        for k, v in fl.items():
            if isinstance(v, list):
                array_fields.add(k)

    # Try to inline small nested arrays into parent rows as compact strings
    inlined_fields = set()
    for af in sorted(array_fields):
        cached: list[tuple[int, str]] = []  # (row_index, rendered_string)
        can_inline = True
        for i, fl in enumerate(all_flat):
            arr_val = fl.get(af)
            if not isinstance(arr_val, list):
                continue  # leave non-list values untouched
            if not arr_val:
                continue  # empty list → skip
            rendered = _inline_nested_array(arr_val)
            if rendered is None:
                can_inline = False
                break
            cached.append((i, rendered))
        if can_inline and cached:
            for i, rendered in cached:
                all_flat[i][af] = rendered
            # Normalize any remaining empty lists to "" so they don't
            # serialize as [] in the parent table.
            for fl in all_flat:
                if isinstance(fl.get(af), list) and not fl[af]:
                    fl[af] = ""
            inlined_fields.add(af)
    array_fields -= inlined_fields

    # Determine parent identity column for back-references
    scalar_cols = order_columns(union_columns(all_flat))
    id_col = find_identity_column(scalar_cols, all_flat)

    # Collect sub-table data for each array field
    sub_tables = {}
    for af in sorted(array_fields):
        sub_items = []
        for fl in all_flat:
            parent_id = fmt(fl.get(id_col, "")) if id_col else ""
            arr_val = fl.get(af, [])
            if isinstance(arr_val, list):
                for sub in arr_val:
                    if isinstance(sub, dict):
                        tagged = OrderedDict()
                        tagged[f"_parent.{id_col}"] = parent_id
                        tagged.update(flatten(sub))
                        sub_items.append(tagged)
        if heuristics.pivot_key_value:
            sub_items = pivot_kv_fields(sub_items)
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

    # Identify residual array fields not handled by inlining or sub-table extraction
    residual_fields = array_fields - set(sub_tables.keys())

    # Now preprocess the parent table using pivoted flat dicts
    # (array fields are excluded by union_columns since they skip list values)
    annotations, cleaned_rows, final_cols = preprocess_table(name, all_flat, heuristics)

    # Check wide table threshold — switch rendering format if exceeded
    if heuristics.wide_table_threshold > 0 and len(final_cols) > heuristics.wide_table_threshold:
        if heuristics.wide_table_format == "split":
            block = render_split(name, arr, annotations, cleaned_rows, final_cols, heuristics)
        else:
            block = render_vertical(name, arr, annotations, cleaned_rows, final_cols)
        blocks.append(block)
    else:
        # Standard tabular path
        toon_text = toon_format.encode(cleaned_rows)
        header = f"--- {name} ({len(arr)} rows) ---"
        parts = [header]
        parts.extend(annotations)
        parts.append(toon_text)
        blocks.append("\n".join(parts))

    # Render sub-tables — recurse through render_table so nested arrays
    # within sub-table items also get residual fallback treatment.
    for af, sub_items in sorted(sub_tables.items()):
        sub_name = f"{name}.{af}"
        blocks.extend(render_table(sub_name, [dict(si) for si in sub_items], heuristics))

    # Render residual array fields — fallback for data that couldn't be
    # inlined or extracted as sub-tables.  Uses recursive condense() for
    # arrays of dicts, json.dumps() for everything else.
    for af in sorted(residual_fields):
        _log_residual(name, af, all_flat, id_col)
        for fl in all_flat:
            arr_val = fl.get(af, [])
            if not isinstance(arr_val, list) or not arr_val:
                continue
            parent_id = fmt(fl.get(id_col, "")) if id_col else ""
            label = f"{name}.{af}"
            if parent_id:
                label += f"[{parent_id}]"
            if all(isinstance(item, dict) for item in arr_val):
                # Array of dicts — recurse for full semantic processing
                for i, item in enumerate(arr_val):
                    blocks.extend(condense(f"{label}[{i}]", item, heuristics))
            else:
                # Primitives, arrays-of-arrays, mixed — lossless JSON
                blocks.append(f"{label}: {json.dumps(arr_val)}")

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


def condense_text(data: Any, heuristics: Heuristics | None = None) -> str:
    """Condense parsed structured data into compact TOON text."""
    if isinstance(data, dict):
        blocks = []
        for k in data:
            blocks.extend(condense(k, data[k], heuristics))
        return _join_blocks(blocks)
    return _join_blocks(condense("root", data, heuristics))


def toon_encode(data: Any) -> str:
    """Convert structured data directly to TOON format without semantic preprocessing."""
    return toon_format.encode(data)


# ── deprecated aliases ───────────────────────────────────────────────────

def condense_json(data: Any, heuristics: Heuristics | None = None) -> str:  # noqa: D103
    warnings.warn(
        "condense_json() is deprecated, use condense_text() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return condense_text(data, heuristics=heuristics)


def toon_encode_json(data: Any) -> str:  # noqa: D103
    warnings.warn(
        "toon_encode_json() is deprecated, use toon_encode() instead",
        DeprecationWarning,
        stacklevel=2,
    )
    return toon_encode(data)


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
    result = condense_text(data)

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
