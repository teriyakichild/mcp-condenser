"""Benchmark tests for condenser compression quality and performance."""

import json
import time
from pathlib import Path

import pytest

from mcp_condenser.condenser import condense_json, toon_encode_json, count_tokens

FIXTURES = Path(__file__).parent / "fixtures"

SAMPLES = [
    "toolresult.json",
    "toolresult2.json",
    "tool_t1_i5.json",
]


def load_sample(filename: str):
    """Load a fixture file, unwrapping the {"result": "<json>"} envelope if present."""
    raw = (FIXTURES / filename).read_text()
    data = json.loads(raw)
    # tool_t1_i5.json wraps inner JSON as a string in {"result": "..."}
    if isinstance(data, dict) and set(data.keys()) == {"result"} and isinstance(data["result"], str):
        inner = data["result"]
        data = json.loads(inner)
        raw = inner
    return raw, data


class TestBenchmarkTokenReduction:
    """Validate token reduction claims across real-world samples."""

    @pytest.mark.parametrize("filename", SAMPLES)
    def test_condense_reduces_tokens(self, filename):
        raw, data = load_sample(filename)
        orig_tokens = count_tokens(raw)
        condensed = condense_json(data)
        cond_tokens = count_tokens(condensed)
        reduction = 1 - cond_tokens / orig_tokens
        assert reduction >= 0.40, (
            f"{filename}: condense_json only achieved {reduction:.1%} reduction "
            f"({orig_tokens} -> {cond_tokens} tokens)"
        )

    @pytest.mark.parametrize("filename", SAMPLES)
    def test_toon_encode_reduces_tokens(self, filename):
        """TOON-only encoding should reduce tokens for flat data.

        Note: deeply nested structures may expand slightly since TOON
        format adds structure overhead without the preprocessing elision
        that condense_json provides. We use a lenient floor here.
        """
        raw, data = load_sample(filename)
        orig_tokens = count_tokens(raw)
        toon = toon_encode_json(data)
        toon_tokens = count_tokens(toon)
        reduction = 1 - toon_tokens / orig_tokens
        assert reduction >= -0.15, (
            f"{filename}: toon_encode_json expanded too much ({reduction:.1%}), "
            f"({orig_tokens} -> {toon_tokens} tokens)"
        )

    @pytest.mark.parametrize("filename", SAMPLES)
    def test_condense_better_than_toon_only(self, filename):
        _, data = load_sample(filename)
        condensed = condense_json(data)
        toon = toon_encode_json(data)
        cond_tokens = count_tokens(condensed)
        toon_tokens = count_tokens(toon)
        assert cond_tokens <= toon_tokens, (
            f"{filename}: condense_json ({cond_tokens} tokens) should produce "
            f"fewer tokens than toon_encode_json ({toon_tokens} tokens)"
        )


class TestBenchmarkPerformance:
    """Ensure each method completes within acceptable time."""

    @pytest.mark.parametrize("filename", SAMPLES)
    def test_condense_performance(self, filename):
        _, data = load_sample(filename)
        start = time.perf_counter()
        condense_json(data)
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"{filename}: condense_json took {elapsed:.2f}s (limit 5s)"

    @pytest.mark.parametrize("filename", SAMPLES)
    def test_toon_encode_performance(self, filename):
        _, data = load_sample(filename)
        start = time.perf_counter()
        toon_encode_json(data)
        elapsed = time.perf_counter() - start
        assert elapsed < 5.0, f"{filename}: toon_encode_json took {elapsed:.2f}s (limit 5s)"


class TestBenchmarkSummary:
    """Print a comparison table with actual compression numbers."""

    def test_print_summary(self, capsys):
        rows = []
        for filename in SAMPLES:
            raw, data = load_sample(filename)
            orig_tokens = count_tokens(raw)

            t0 = time.perf_counter()
            condensed = condense_json(data)
            t_condense = time.perf_counter() - t0

            t0 = time.perf_counter()
            toon = toon_encode_json(data)
            t_toon = time.perf_counter() - t0

            cond_tokens = count_tokens(condensed)
            toon_tokens = count_tokens(toon)

            rows.append({
                "file": filename,
                "size_kb": len(raw) / 1024,
                "orig_tokens": orig_tokens,
                "cond_tokens": cond_tokens,
                "cond_pct": round((1 - cond_tokens / orig_tokens) * 100, 1),
                "toon_tokens": toon_tokens,
                "toon_pct": round((1 - toon_tokens / orig_tokens) * 100, 1),
                "t_condense": t_condense,
                "t_toon": t_toon,
            })

        # Print table
        print()
        print("=" * 95)
        print(f"{'File':<20} {'Size':>7} {'Orig':>8} {'Condense':>10} {'Red%':>6} {'TOON':>10} {'Red%':>6} {'T(c)':>7} {'T(t)':>7}")
        print("-" * 95)
        for r in rows:
            print(
                f"{r['file']:<20} {r['size_kb']:>6.0f}K "
                f"{r['orig_tokens']:>8,} "
                f"{r['cond_tokens']:>10,} {r['cond_pct']:>5.1f}% "
                f"{r['toon_tokens']:>10,} {r['toon_pct']:>5.1f}% "
                f"{r['t_condense']:>6.2f}s {r['t_toon']:>6.2f}s"
            )
        print("=" * 95)

        captured = capsys.readouterr()
        assert "File" in captured.out
