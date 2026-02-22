#!/usr/bin/env python3
"""Accuracy benchmark: verify an LLM can answer questions from condensed output.

Requires a running Ollama server. Run with:
    uv run python benchmarks/accuracy.py
    uv run python benchmarks/accuracy.py --model qwen3:1.7b --toon-only
"""

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

from mcp_condenser.condenser import Heuristics, condense_json, count_tokens

from benchmarks.fixtures import (
    QUESTIONS,
    load_sample,
)


# ---------------------------------------------------------------------------
# Ollama helper
# ---------------------------------------------------------------------------

def ask_ollama(model: str, context: str, question: str, host: str = "http://localhost:11434", num_ctx: int = 0) -> str:
    """Send a question + context to Ollama and return the response text."""
    import httpx

    body = {
        "model": model,
        "stream": False,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a data analyst. Answer questions about the "
                    "provided data concisely. Give only the answer value, "
                    "no explanation."
                ),
            },
            {
                "role": "user",
                "content": f"DATA:\n{context}\n\nQUESTION: {question}",
            },
        ],
    }
    if num_ctx > 0:
        body["options"] = {"num_ctx": num_ctx}

    resp = httpx.post(
        f"{host}/api/chat",
        json=body,
        timeout=600.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ---------------------------------------------------------------------------
# Context size check
# ---------------------------------------------------------------------------

def fits_context(text: str, ctx_limit: int) -> bool:
    """Check if text fits in the model context window.

    Ollama tokenizers typically produce more tokens than tiktoken (observed
    ~3x on JSON-heavy inputs). We use a conservative 3x multiplier so we
    skip rather than silently truncate.
    """
    estimated = count_tokens(text) * 3
    return estimated <= ctx_limit


# ---------------------------------------------------------------------------
# Run benchmark
# ---------------------------------------------------------------------------

def _status(icon: str, fmt: str, fixture: str, question: str, elapsed: float = 0):
    """Print a live status line to stderr."""
    q = question[:60]
    print(f"  {icon} [{fmt:<4}] {fixture:<24} {q:<62} {elapsed:>5.1f}s", file=sys.stderr)


def run_benchmark(args, questions: dict | None = None) -> list[dict]:
    """Run all benchmark questions and return results.

    Args:
        args: Parsed CLI arguments (or equivalent namespace).
        questions: Optional dict of fixture -> question list. Defaults to
            the full QUESTIONS dict from fixtures.py.
    """
    if questions is None:
        questions = QUESTIONS
    fixtures_dir = Path(args.fixtures_dir)
    results = []

    total_q = sum(len(qs) for qs in questions.values())
    formats = 1 if args.toon_only else 2
    total_calls = total_q * formats
    done = 0

    h = getattr(args, 'heuristics_obj', None)
    for fixture, qs in questions.items():
        fixture_path = fixtures_dir / fixture
        if not fixture_path.exists():
            print(f"  (skipping {fixture} — file not found)", file=sys.stderr)
            continue

        raw, data = load_sample(fixtures_dir, fixture)
        condensed = condense_json(data, heuristics=h)

        print(f"\n  --- {fixture} ({len(qs)} questions) ---", file=sys.stderr)

        for question, expected, match_fn in qs:
            # JSON baseline (unless --toon-only)
            if not args.toon_only:
                if not fits_context(raw, args.ctx):
                    results.append({
                        "fixture": fixture,
                        "question": question[:50],
                        "format": "json",
                        "tokens": count_tokens(raw),
                        "elapsed": 0,
                        "passed": None,
                        "answer": "(skipped: too large for context)",
                        "expected": expected,
                    })
                    done += 1
                    _status("-", "json", fixture, question)
                else:
                    try:
                        t0 = time.perf_counter()
                        answer = ask_ollama(args.model, raw, question, host=args.host, num_ctx=args.num_ctx)
                        elapsed = time.perf_counter() - t0
                        passed = match_fn(answer, expected)
                        results.append({
                            "fixture": fixture,
                            "question": question[:50],
                            "format": "json",
                            "tokens": count_tokens(raw),
                            "elapsed": elapsed,
                            "passed": passed,
                            "answer": answer.strip(),
                            "expected": expected,
                        })
                        done += 1
                        icon = "+" if passed else "x"
                        _status(icon, "json", fixture, question, elapsed)
                    except Exception as e:
                        results.append({
                            "fixture": fixture,
                            "question": question[:50],
                            "format": "json",
                            "tokens": count_tokens(raw),
                            "elapsed": 0,
                            "passed": None,
                            "answer": f"(error: {e})",
                            "expected": expected,
                        })
                        done += 1
                        _status("!", "json", fixture, question)

            # Condensed TOON
            if not fits_context(condensed, args.ctx):
                results.append({
                    "fixture": fixture,
                    "question": question[:50],
                    "format": "toon",
                    "tokens": count_tokens(condensed),
                    "elapsed": 0,
                    "passed": None,
                    "answer": "(skipped: too large for context)",
                    "expected": expected,
                })
                done += 1
                _status("-", "toon", fixture, question)
            else:
                try:
                    t0 = time.perf_counter()
                    answer = ask_ollama(args.model, condensed, question, host=args.host, num_ctx=args.num_ctx)
                    elapsed = time.perf_counter() - t0
                    passed = match_fn(answer, expected)
                    results.append({
                        "fixture": fixture,
                        "question": question[:50],
                        "format": "toon",
                        "tokens": count_tokens(condensed),
                        "elapsed": elapsed,
                        "passed": passed,
                        "answer": answer.strip(),
                        "expected": expected,
                    })
                    done += 1
                    icon = "+" if passed else "x"
                    _status(icon, "toon", fixture, question, elapsed)
                except Exception as e:
                    results.append({
                        "fixture": fixture,
                        "question": question[:50],
                        "format": "toon",
                        "tokens": count_tokens(condensed),
                        "elapsed": 0,
                        "passed": None,
                        "answer": f"(error: {e})",
                        "expected": expected,
                    })
                    done += 1
                    _status("!", "toon", fixture, question)

        print(f"  ({done}/{total_calls} complete)", file=sys.stderr)

    print(file=sys.stderr)
    return results


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def print_summary(results: list[dict], fixtures_dir: Path, heuristics: Heuristics | None = None, heuristic_overrides: dict | None = None):
    """Print formatted summary table to stdout."""
    print()
    print("=" * 80)
    print("  Accuracy Benchmark")
    print("=" * 80)

    if heuristic_overrides:
        print(f"  Heuristics: {heuristic_overrides}")

    # Per-fixture token comparison
    fixtures_seen = sorted(set(r["fixture"] for r in results))
    print()
    print(f"  {'Fixture':<28} {'JSON tokens':>12} {'TOON tokens':>12} {'Reduction':>10}")
    print(f"  {'-'*28} {'-'*12} {'-'*12} {'-'*10}")
    for fixture in fixtures_seen:
        raw, data = load_sample(fixtures_dir, fixture)
        condensed = condense_json(data, heuristics=heuristics)
        rt = count_tokens(raw)
        ct = count_tokens(condensed)
        pct = (1 - ct / rt) * 100
        print(f"  {fixture:<28} {rt:>12,} {ct:>12,} {pct:>9.1f}%")

    # Per-question results
    print()
    print(f"  {'Fixture':<28} {'Question':<42} {'Fmt':<5} {'Tokens':>7} {'Time':>7} {'Result':>6}")
    print(f"  {'-'*28} {'-'*42} {'-'*5} {'-'*7} {'-'*7} {'-'*6}")
    for r in results:
        if r["passed"] is None:
            status = "SKIP"
        elif r["passed"]:
            status = "PASS"
        else:
            status = "FAIL"
        print(
            f"  {r['fixture']:<28} {r['question']:<42} {r['format']:<5} "
            f"{r['tokens']:>7,} {r['elapsed']:>6.1f}s {status:>6}"
        )

    # Totals
    json_results = [r for r in results if r["format"] == "json" and r["passed"] is not None]
    toon_results = [r for r in results if r["format"] == "toon" and r["passed"] is not None]
    json_pass = sum(1 for r in json_results if r["passed"])
    toon_pass = sum(1 for r in toon_results if r["passed"])
    json_time = sum(r["elapsed"] for r in json_results)
    toon_time = sum(r["elapsed"] for r in toon_results)

    print()
    if json_results:
        print(f"  {'JSON accuracy:':<20} {json_pass}/{len(json_results)}  ({json_pass/len(json_results)*100:.0f}%)")
    print(f"  {'TOON accuracy:':<20} {toon_pass}/{len(toon_results)}  ({toon_pass/len(toon_results)*100:.0f}%)")
    if json_results:
        print(f"  {'JSON total time:':<20} {json_time:.1f}s")
    print(f"  {'TOON total time:':<20} {toon_time:.1f}s")
    if json_time > 0 and toon_time > 0:
        print(f"  {'Speedup:':<20} {json_time/toon_time:.1f}x")
    print()

    # Failure details
    failures = [r for r in results if r["passed"] is False]
    if failures:
        print("=" * 80)
        print("  Failure Details")
        print("=" * 80)
        for r in failures:
            print()
            print(f"  Fixture:  {r['fixture']}")
            print(f"  Format:   {r['format']}")
            print(f"  Question: {r['question']}")
            print(f"  Expected: {r['expected']}")
            print(f"  Got:      {r['answer']}")
            print(f"  {'-' * 76}")
        print()


def print_json(results: list[dict]):
    """Print results as JSON for machine consumption."""
    json.dump(results, sys.stdout, indent=2)
    print()


def log_failures(results: list[dict], model: str, log_path: Path):
    """Append failed results to a JSONL log file for tracking over time."""
    failures = [r for r in results if r["passed"] is False]
    if not failures:
        return
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a") as f:
        for r in failures:
            entry = {
                "timestamp": timestamp,
                "model": model,
                **r,
            }
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Accuracy benchmark for MCP Condenser TOON format",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama server URL (default: http://localhost:11434)",
    )
    parser.add_argument(
        "--model",
        default="qwen3:1.7b",
        help="Ollama model to use (default: qwen3:1.7b)",
    )
    parser.add_argument(
        "--ctx",
        type=int,
        default=128000,
        help="Model context window size in tokens (default: 128000)",
    )
    parser.add_argument(
        "--num-ctx",
        type=int,
        default=0,
        help="Ollama num_ctx option — caps the context window the model allocates (0 = use model default)",
    )
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures",
        help="Path to fixture files (default: tests/fixtures)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output results as JSON for machine consumption",
    )
    parser.add_argument(
        "--toon-only",
        action="store_true",
        help="Skip JSON baseline (halves runtime)",
    )

    parser.add_argument(
        "--failures-log",
        default="benchmarks/failures.jsonl",
        help="Path to JSONL failure log (default: benchmarks/failures.jsonl)",
    )
    parser.add_argument(
        "--heuristics",
        default="",
        help="Heuristic overrides as key:val,key:val (e.g. max_table_columns:12,elide_mostly_zero_pct:0.8)",
    )

    args = parser.parse_args()

    # Parse heuristic overrides
    heuristic_overrides: dict[str, bool | int | float | str] = {}
    if args.heuristics:
        for pair in args.heuristics.split(","):
            pair = pair.strip()
            if ":" in pair:
                name, val = pair.rsplit(":", 1)
                val = val.strip()
                try:
                    heuristic_overrides[name.strip()] = int(val)
                except ValueError:
                    try:
                        heuristic_overrides[name.strip()] = float(val)
                    except ValueError:
                        if val.lower() in ("true", "false", "yes", "no"):
                            heuristic_overrides[name.strip()] = val.lower() in ("true", "yes")
                        else:
                            heuristic_overrides[name.strip()] = val
    args.heuristics_obj = Heuristics(**heuristic_overrides) if heuristic_overrides else None
    args.heuristic_overrides = heuristic_overrides

    results = run_benchmark(args)

    log_failures(results, args.model, Path(args.failures_log))

    if args.json_output:
        print_json(results)
    else:
        print_summary(results, Path(args.fixtures_dir), heuristics=args.heuristics_obj, heuristic_overrides=args.heuristic_overrides)

    # Exit 1 if any TOON answers failed
    toon_results = [r for r in results if r["format"] == "toon" and r["passed"] is not None]
    if any(not r["passed"] for r in toon_results):
        sys.exit(1)


if __name__ == "__main__":
    main()
