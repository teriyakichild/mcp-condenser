#!/usr/bin/env python3
"""Accuracy benchmark: verify an LLM can answer questions from condensed output.

Requires a running Ollama server. Run with:
    uv run python benchmarks/accuracy.py
    uv run python benchmarks/accuracy.py --model qwen3:1.7b --toon-only
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

from mcp_condenser.condenser import condense_json, count_tokens


# ---------------------------------------------------------------------------
# Ollama helper
# ---------------------------------------------------------------------------

def ask_ollama(model: str, context: str, question: str, host: str = "http://localhost:11434") -> str:
    """Send a question + context to Ollama and return the response text."""
    import httpx

    resp = httpx.post(
        f"{host}/api/chat",
        json={
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
        },
        timeout=300.0,
    )
    resp.raise_for_status()
    return resp.json()["message"]["content"]


# ---------------------------------------------------------------------------
# Fixture loader
# ---------------------------------------------------------------------------

def load_sample(fixtures_dir: Path, filename: str):
    """Load a fixture file, unwrapping {"result": "<json>"} envelope if present."""
    raw = (fixtures_dir / filename).read_text()
    data = json.loads(raw)
    if isinstance(data, dict) and set(data.keys()) == {"result"} and isinstance(data["result"], str):
        inner = data["result"]
        data = json.loads(inner)
        raw = inner
    return raw, data


# ---------------------------------------------------------------------------
# Match functions
# ---------------------------------------------------------------------------

def contains(answer: str, expected: str) -> bool:
    """Expected string appears somewhere in the LLM response."""
    return expected in answer


def numeric_close(answer: str, expected: str, tol: float = 0.01) -> bool:
    """Extract a number from the answer and check it's within tolerance."""
    expected_num = float(expected)
    numbers = re.findall(r"[\d,]+\.?\d*", answer.replace(",", ""))
    for raw_num in numbers:
        try:
            val = float(raw_num)
            if abs(val - expected_num) <= tol * max(abs(expected_num), 1):
                return True
        except ValueError:
            continue
    return False


def contains_or_numeric(answer: str, expected: str) -> bool:
    return contains(answer, expected) or numeric_close(answer, expected)


# ---------------------------------------------------------------------------
# Questions per fixture
# ---------------------------------------------------------------------------

QUESTIONS: dict[str, list[tuple[str, str, callable]]] = {
    "toolresult.json": [
        (
            "What is the node's available filesystem space in bytes?",
            "29417222144",
            contains,
        ),
        (
            "What is the node's filesystem capacity in bytes?",
            "40571502592",
            contains,
        ),
        (
            "What is the 10-second average CPU PSI (some) value?",
            "1.79",
            contains_or_numeric,
        ),
        (
            "What is the node's memory working set in bytes?",
            "3740188672",
            contains,
        ),
        (
            "What is the node name?",
            "talos-default-worker-1",
            contains,
        ),
        (
            "How many pods are listed in the pods array?",
            "16",
            contains_or_numeric,
        ),
        (
            "What is the node's memory RSS bytes?",
            "2135183360",
            contains,
        ),
        (
            "How many system containers are listed?",
            "3",
            contains_or_numeric,
        ),
        (
            "What namespace is the jaeger pod running in?",
            "ecommerce-prod",
            contains,
        ),
        (
            "What is the node's filesystem used bytes?",
            "11154280448",
            contains,
        ),
    ],
    "toolresult2_small.json": [
        (
            "How many pods are listed in the pods array?",
            "6",
            contains_or_numeric,
        ),
        (
            "Which pod has the highest memory working set bytes? Give the pod name only.",
            "opensearch-0",
            contains,
        ),
        (
            "What is the node's filesystem capacity in bytes?",
            "40571502592",
            contains,
        ),
        (
            "What is the memory working set bytes for the grafana pod?",
            "404434944",
            contains,
        ),
        (
            "What is the 10-second average CPU PSI (some) value for the node?",
            "6.24",
            contains_or_numeric,
        ),
        (
            "Which pod has the lowest memory working set bytes? Give the pod name only.",
            "coredns",
            contains,
        ),
        (
            "What is the node name?",
            "talos-default-worker-2",
            contains,
        ),
        (
            "What namespace is the basic-memory pod in?",
            "aura",
            contains,
        ),
        (
            "How many containers does the grafana pod have?",
            "4",
            contains_or_numeric,
        ),
        (
            "What is the IO PSI full avg10 value for the node?",
            "0.44",
            contains_or_numeric,
        ),
        (
            "What is the opensearch pod's memory RSS bytes?",
            "824295424",
            contains,
        ),
    ],
}


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

def run_benchmark(args) -> list[dict]:
    """Run all benchmark questions and return results."""
    fixtures_dir = Path(args.fixtures_dir)
    results = []

    for fixture, questions in QUESTIONS.items():
        raw, data = load_sample(fixtures_dir, fixture)
        condensed = condense_json(data)

        for question, expected, match_fn in questions:
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
                else:
                    t0 = time.perf_counter()
                    answer = ask_ollama(args.model, raw, question, host=args.host)
                    elapsed = time.perf_counter() - t0
                    passed = match_fn(answer, expected)
                    results.append({
                        "fixture": fixture,
                        "question": question[:50],
                        "format": "json",
                        "tokens": count_tokens(raw),
                        "elapsed": elapsed,
                        "passed": passed,
                        "answer": answer.strip()[:80],
                        "expected": expected,
                    })

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
            else:
                t0 = time.perf_counter()
                answer = ask_ollama(args.model, condensed, question, host=args.host)
                elapsed = time.perf_counter() - t0
                passed = match_fn(answer, expected)
                results.append({
                    "fixture": fixture,
                    "question": question[:50],
                    "format": "toon",
                    "tokens": count_tokens(condensed),
                    "elapsed": elapsed,
                    "passed": passed,
                    "answer": answer.strip()[:80],
                    "expected": expected,
                })

    return results


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------

def print_summary(results: list[dict], fixtures_dir: Path):
    """Print formatted summary table to stdout."""
    print()
    print("=" * 80)
    print("  Accuracy Benchmark")
    print("=" * 80)

    # Per-fixture token comparison
    print()
    print(f"  {'Fixture':<28} {'JSON tokens':>12} {'TOON tokens':>12} {'Reduction':>10}")
    print(f"  {'-'*28} {'-'*12} {'-'*12} {'-'*10}")
    for fixture in QUESTIONS:
        raw, data = load_sample(fixtures_dir, fixture)
        condensed = condense_json(data)
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


def print_json(results: list[dict]):
    """Print results as JSON for machine consumption."""
    json.dump(results, sys.stdout, indent=2)
    print()


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

    args = parser.parse_args()
    results = run_benchmark(args)

    if args.json_output:
        print_json(results)
    else:
        print_summary(results, Path(args.fixtures_dir))

    # Exit 1 if any TOON answers failed
    toon_results = [r for r in results if r["format"] == "toon" and r["passed"] is not None]
    if any(not r["passed"] for r in toon_results):
        sys.exit(1)


if __name__ == "__main__":
    main()
