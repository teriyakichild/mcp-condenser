#!/usr/bin/env python3
"""Multi-model benchmark matrix — runs accuracy benchmarks across models and
generates markdown report tables.

Usage:
    uv run python benchmarks/matrix.py --host http://192.168.4.75:11434
    uv run python benchmarks/matrix.py --models qwen3:1.7b,qwen3:4b --host http://192.168.4.75:11434
    uv run python benchmarks/matrix.py --context-sweep --model llama3.1:8b --host http://192.168.4.75:11434
"""

import argparse
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

from mcp_condenser.condenser import condense_json, count_tokens

from benchmarks.accuracy import ask_ollama, fits_context, run_benchmark
from benchmarks.fixtures import FIXTURE_METADATA, QUESTIONS, load_sample

DEFAULT_MODELS = [
    "qwen3:1.7b",
    "qwen3:4b",
    "llama3.1:8b",
    "qwen3:14b",
    "qwen3:30b",
]

# Fixtures included by default (skip toolresult2.json — it's 70K tokens)
DEFAULT_FIXTURES = [
    "toolresult.json",
    "toolresult2_small.json",
    "aws_ec2_instances.json",
    "db_query_results.json",
]

LARGE_FIXTURES = [
    "toolresult2.json",
]

CONTEXT_SIZES = [8192, 16384, 32768, 65536, 131072]


# ---------------------------------------------------------------------------
# Result helpers
# ---------------------------------------------------------------------------

def _score(results: list[dict], fixture: str, fmt: str) -> tuple[int, int]:
    """Return (passed, total) for a fixture/format pair."""
    rs = [r for r in results if r["fixture"] == fixture and r["format"] == fmt and r["passed"] is not None]
    return sum(1 for r in rs if r["passed"]), len(rs)


def _pct(passed: int, total: int) -> str:
    if total == 0:
        return "--"
    return f"{passed}/{total} ({passed/total*100:.0f}%)"


# ---------------------------------------------------------------------------
# Token reduction table
# ---------------------------------------------------------------------------

def generate_token_table(fixtures_dir: Path, fixtures: list[str]) -> str:
    """Generate markdown table showing token reduction per fixture."""
    lines = [
        "| Fixture | Domain | JSON tokens | TOON tokens | Reduction |",
        "|---------|--------|-------------|-------------|-----------|",
    ]
    for fixture in fixtures:
        path = fixtures_dir / fixture
        if not path.exists():
            continue
        raw, data = load_sample(fixtures_dir, fixture)
        condensed = condense_json(data)
        rt = count_tokens(raw)
        ct = count_tokens(condensed)
        pct = (1 - ct / rt) * 100
        meta = FIXTURE_METADATA.get(fixture, {})
        domain = meta.get("domain", "")
        label = meta.get("label", fixture)
        lines.append(f"| {label} | {domain} | {rt:,} | {ct:,} | **{pct:.1f}%** |")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Accuracy matrix table
# ---------------------------------------------------------------------------

def generate_accuracy_matrix(
    all_results: dict[str, list[dict]],
    fixtures: list[str],
) -> str:
    """Generate model × fixture accuracy matrix as markdown.

    all_results: {model_name: [result_dicts]}
    """
    # Header
    fixture_labels = []
    for f in fixtures:
        meta = FIXTURE_METADATA.get(f, {})
        fixture_labels.append(meta.get("label", f))

    header = "| Model | " + " | ".join(fixture_labels) + " |"
    sep = "|-------|" + "|".join(["-----" for _ in fixtures]) + "|"
    lines = [header, sep]

    for model, results in all_results.items():
        cells = [f"**{model}**"]
        for fixture in fixtures:
            jp, jt = _score(results, fixture, "json")
            tp, tt = _score(results, fixture, "toon")
            json_s = _pct(jp, jt)
            toon_s = _pct(tp, tt)
            if jt == 0:
                cells.append(f"-- / {toon_s}")
            else:
                cells.append(f"{json_s} / {toon_s}")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append("*Cells show JSON accuracy / TOON accuracy.*")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Context window enablement table
# ---------------------------------------------------------------------------

def generate_context_table(
    sweep_results: dict[int, list[dict]],
    fixtures: list[str],
    fixtures_dir: Path,
) -> str:
    """Generate context window enablement table.

    sweep_results: {num_ctx: [result_dicts]}
    Shows which fixtures fit in JSON vs TOON at each context size.
    """
    # Pre-compute token counts
    fixture_tokens: dict[str, tuple[int, int]] = {}
    for fixture in fixtures:
        path = fixtures_dir / fixture
        if not path.exists():
            continue
        raw, data = load_sample(fixtures_dir, fixture)
        condensed = condense_json(data)
        fixture_tokens[fixture] = (count_tokens(raw), count_tokens(condensed))

    fixture_labels = [FIXTURE_METADATA.get(f, {}).get("label", f) for f in fixtures]

    header = "| Fixture | JSON tok | TOON tok | " + " | ".join(f"{s//1024}K" for s in CONTEXT_SIZES) + " |"
    sep = "|---------|----------|----------|" + "|".join(["-----" for _ in CONTEXT_SIZES]) + "|"
    lines = [header, sep]

    for fixture in fixtures:
        if fixture not in fixture_tokens:
            continue
        jt, tt = fixture_tokens[fixture]
        meta = FIXTURE_METADATA.get(fixture, {})
        label = meta.get("label", fixture)
        cells = [label, f"{jt:,}", f"{tt:,}"]
        for ctx in CONTEXT_SIZES:
            json_fits = fits_context_static(jt, ctx)
            toon_fits = fits_context_static(tt, ctx)
            if json_fits and toon_fits:
                cells.append("Both")
            elif toon_fits:
                cells.append("**TOON only**")
            else:
                cells.append("--")
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines)


def fits_context_static(tiktoken_count: int, ctx_limit: int) -> bool:
    """Check if a tiktoken count fits, using the same 3x safety factor."""
    return tiktoken_count * 3 <= ctx_limit


# ---------------------------------------------------------------------------
# Context sweep runner
# ---------------------------------------------------------------------------

def run_context_sweep(
    model: str,
    host: str,
    fixtures_dir: Path,
    fixtures: list[str],
) -> dict[int, list[dict]]:
    """Run a single model at multiple context sizes."""
    sweep_results: dict[int, list[dict]] = {}
    for ctx in CONTEXT_SIZES:
        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Context sweep: {model} @ {ctx//1024}K context", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        # Build questions dict filtered to requested fixtures
        qs = {f: QUESTIONS[f] for f in fixtures if f in QUESTIONS}
        args = SimpleNamespace(
            model=model,
            host=host,
            fixtures_dir=str(fixtures_dir),
            ctx=ctx,
            num_ctx=ctx,
            toon_only=False,
            heuristics_obj=None,
        )
        results = run_benchmark(args, questions=qs)
        sweep_results[ctx] = results

    return sweep_results


# ---------------------------------------------------------------------------
# Matrix runner
# ---------------------------------------------------------------------------

def run_matrix(
    models: list[str],
    host: str,
    fixtures_dir: Path,
    fixtures: list[str],
    output_dir: Path,
    resume: bool = False,
) -> dict[str, list[dict]]:
    """Run benchmark across all models, saving results incrementally."""
    all_results: dict[str, list[dict]] = {}
    raw_path = output_dir / "raw_results.json"

    # Resume from previous run
    if resume and raw_path.exists():
        prev = json.loads(raw_path.read_text())
        for model, results in prev.items():
            all_results[model] = results
        print(f"  Resumed {len(all_results)} models from {raw_path}", file=sys.stderr)

    # Build questions dict filtered to requested fixtures
    qs = {f: QUESTIONS[f] for f in fixtures if f in QUESTIONS}

    for model in models:
        if model in all_results:
            print(f"\n  Skipping {model} — already complete", file=sys.stderr)
            continue

        print(f"\n{'='*60}", file=sys.stderr)
        print(f"  Model: {model}", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)

        args = SimpleNamespace(
            model=model,
            host=host,
            fixtures_dir=str(fixtures_dir),
            ctx=128000,
            num_ctx=0,
            toon_only=False,
            heuristics_obj=None,
        )

        try:
            results = run_benchmark(args, questions=qs)
            all_results[model] = results

            # Incremental save
            output_dir.mkdir(parents=True, exist_ok=True)
            raw_path.write_text(json.dumps(all_results, indent=2))
            print(f"  Saved results for {model}", file=sys.stderr)
        except Exception as e:
            print(f"  ERROR running {model}: {e}", file=sys.stderr)
            continue

    return all_results


# ---------------------------------------------------------------------------
# Report writer
# ---------------------------------------------------------------------------

def write_reports(
    all_results: dict[str, list[dict]],
    fixtures: list[str],
    fixtures_dir: Path,
    output_dir: Path,
    sweep_results: dict[int, list[dict]] | None = None,
):
    """Write all markdown report files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Token reduction table
    token_md = generate_token_table(fixtures_dir, fixtures)

    # Accuracy matrix
    matrix_md = generate_accuracy_matrix(all_results, fixtures)

    # Context enablement
    all_fixtures = fixtures + LARGE_FIXTURES
    context_md = generate_context_table(
        sweep_results or {},
        all_fixtures,
        fixtures_dir,
    )

    # Combined report
    report_lines = [
        "# Benchmark Results",
        "",
        "## Token Reduction",
        "",
        token_md,
        "",
        "## Accuracy Matrix",
        "",
        "*JSON accuracy / TOON accuracy per model and fixture.*",
        "",
        matrix_md,
        "",
        "## Context Window Enablement",
        "",
        context_md,
        "",
    ]

    report_path = output_dir / "accuracy_matrix.md"
    report_path.write_text("\n".join(report_lines))
    print(f"\n  Report written to {report_path}", file=sys.stderr)

    # Also write individual tables
    (output_dir / "token_reduction.md").write_text(token_md)
    (output_dir / "context_enablement.md").write_text(context_md)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Multi-model accuracy benchmark matrix",
    )
    parser.add_argument(
        "--host",
        default="http://192.168.4.75:11434",
        help="Ollama server URL (default: http://192.168.4.75:11434)",
    )
    parser.add_argument(
        "--models",
        default=",".join(DEFAULT_MODELS),
        help=f"Comma-separated model list (default: {','.join(DEFAULT_MODELS)})",
    )
    parser.add_argument(
        "--fixtures",
        default=None,
        help="Comma-separated fixture filenames (default: standard set minus large)",
    )
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures",
        help="Path to fixture files (default: tests/fixtures)",
    )
    parser.add_argument(
        "--output-dir",
        default="benchmarks/results",
        help="Output directory for reports (default: benchmarks/results)",
    )
    parser.add_argument(
        "--include-large",
        action="store_true",
        help="Include toolresult2.json (70K tokens, slow)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip models already present in raw_results.json",
    )
    parser.add_argument(
        "--context-sweep",
        action="store_true",
        help="Run context window sweep instead of model matrix",
    )
    parser.add_argument(
        "--model",
        default="llama3.1:8b",
        help="Model for context sweep (default: llama3.1:8b)",
    )

    args = parser.parse_args()

    models = [m.strip() for m in args.models.split(",")]
    fixtures_dir = Path(args.fixtures_dir)
    output_dir = Path(args.output_dir)

    if args.fixtures:
        fixtures = [f.strip() for f in args.fixtures.split(",")]
    else:
        fixtures = list(DEFAULT_FIXTURES)
        if args.include_large:
            fixtures.extend(LARGE_FIXTURES)

    # Filter to fixtures that actually exist and have questions
    available = [f for f in fixtures if (fixtures_dir / f).exists() and f in QUESTIONS]
    missing = [f for f in fixtures if f not in available]
    if missing:
        print(f"  Warning: skipping missing fixtures: {missing}", file=sys.stderr)
    fixtures = available

    if not fixtures:
        print("  Error: no valid fixtures found", file=sys.stderr)
        sys.exit(1)

    t0 = time.perf_counter()

    if args.context_sweep:
        # Context window sweep mode
        print(f"\n  Context sweep: {args.model} across {[s//1024 for s in CONTEXT_SIZES]}K", file=sys.stderr)
        sweep_fixtures = fixtures + [f for f in LARGE_FIXTURES if (fixtures_dir / f).exists() and f in QUESTIONS]
        sweep_results = run_context_sweep(
            args.model, args.host, fixtures_dir, sweep_fixtures,
        )
        # Save sweep results
        output_dir.mkdir(parents=True, exist_ok=True)
        sweep_path = output_dir / "context_sweep.json"
        serializable = {str(k): v for k, v in sweep_results.items()}
        sweep_path.write_text(json.dumps(serializable, indent=2))

        write_reports({args.model: []}, fixtures, fixtures_dir, output_dir, sweep_results)
    else:
        # Model matrix mode
        all_results = run_matrix(
            models, args.host, fixtures_dir, fixtures, output_dir, args.resume,
        )
        write_reports(all_results, fixtures, fixtures_dir, output_dir)

    elapsed = time.perf_counter() - t0
    print(f"\n  Total time: {elapsed/60:.1f} minutes", file=sys.stderr)


if __name__ == "__main__":
    main()
