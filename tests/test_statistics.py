"""Statistical tests (all marked slow): false-positive rate, construction success vs overhead, size vs sizing table.

Run with ``pytest -m slow -s tests/test_statistics.py`` to see one table row per case. Environment variables:

* ``PYRIBBON_STATS_OUT=path.json``: also write every row as JSON when the module finishes.
* ``PYRIBBON_STATS_SCALE=0.05``: shrink every probe and trial count (for a quick look; the 5-sigma bounds are
  recomputed from the scaled counts, so the assertions stay valid but lose power).

The false-positive probes are exact binomial trials. For a fixed filter and a negative key whose equation
``(start, coeff, fp)`` is pseudo-random, ``P(false positive) = 2**-r`` exactly, whatever the filter contains (``fp`` is
uniform and independent of the filter), and different negative keys are independent, so 5 sigma is a genuine bound.
"""

from __future__ import annotations

import json
import math
import os
import random
import statistics
from collections.abc import Callable, Iterable, Iterator
from typing import Any

import pytest
import spec_reference as ref

from pyribbon import ConstructionError, RibbonFilter

pytestmark = pytest.mark.slow

SCALE = float(os.environ.get("PYRIBBON_STATS_SCALE", "1"))
SIGMAS = 5.0
CHUNK = 1_000_000
TOTAL_PROBE_CAP = 300_000_000  # per case, all families together
_printed_header: set[str] = set()


@pytest.fixture(scope="module")
def stats(request: pytest.FixtureRequest) -> Iterator[dict[str, list[dict[str, Any]]]]:
    """Collect every table row; write them to ``PYRIBBON_STATS_OUT`` and print the worst z-score at the end."""
    rows: dict[str, list[dict[str, Any]]] = {"fpr": [], "construction": [], "sweep": [], "size": []}
    yield rows
    path = os.environ.get("PYRIBBON_STATS_OUT")
    if path:
        with open(path, "w") as fh:
            json.dump(rows, fh, indent=1)
    reporter = request.config.pluginmanager.getplugin("terminalreporter")
    if reporter is not None and rows["fpr"]:
        worst = max(rows["fpr"], key=lambda row: abs(row["z"]))
        reporter.write_line(
            f"\nFPR: {len(rows['fpr'])} rows, worst |z| = {abs(worst['z']):.2f} "
            f"(r={worst['r']}, n={worst['n']}, {worst['family']})"
        )


def emit(capsys: pytest.CaptureFixture[str], table: str, header: str, line: str) -> None:
    """Print a table row to the real terminal, with the header before the first row of that table."""
    with capsys.disabled():
        if table not in _printed_header:
            _printed_header.add(table)
            print(f"\n{header}")
        print(line)


# ---------------------------------------------------------------------------------------------------------------
# (a) false-positive rate


def plan_probes(r: int) -> tuple[int, int]:
    """Probe counts ``(ints, strs_and_bytes_each)``: about 2000 expected hits, DESIGN.md section 10 minimums, capped."""
    ideal = 2000 * 2**r
    ints = min(max(ideal, 10_000_000 if r < 8 else 100_000_000), TOTAL_PROBE_CAP)
    aux = min(max(ideal, 10_000_000), (TOTAL_PROBE_CAP - ints) // 2)
    return max(int(ints * SCALE), 1000), max(int(aux * SCALE), 1000)


def count_positives(f: RibbonFilter, total: int, make: Callable[[int, int], Iterable[Any]]) -> int:
    return sum(sum(f.contains_many(make(lo, min(lo + CHUNK, total)))) for lo in range(0, total, CHUNK))


FPR_CASES = [(r, n) for n in (1_000, 100_000) for r in (1, 2, 4, 6, 8, 10, 12, 16)] + [(8, 1_000_000)]


@pytest.mark.parametrize(("r", "n"), FPR_CASES, ids=[f"r{r}-n{n}" for r, n in FPR_CASES])
def test_false_positive_rate_matches_two_to_the_minus_r(
    r: int, n: int, capsys: pytest.CaptureFixture[str], stats: dict[str, list[dict[str, Any]]]
) -> None:
    f = RibbonFilter(range(n), fp_bits=r, seed=12345 + r)
    assert all(f.contains_many(range(n)))  # members first: no false negatives at this size either
    ints, aux = plan_probes(r)
    families: list[tuple[str, int, Callable[[int, int], Iterable[Any]]]] = [
        ("int", ints, lambda lo, hi: range(n + lo, n + hi)),  # disjoint from the members [0, n)
        ("str", aux, lambda lo, hi: [f"neg-{i}" for i in range(lo, hi)]),
        ("bytes", aux, lambda lo, hi: [b"nb-%d" % i for i in range(lo, hi)]),
    ]
    p = 2.0**-r
    header = (
        f"{'r':>3} {'n':>9} {'family':>6} {'probes':>11} {'FP':>10} {'rate':>11} {'2^-r':>11} {'expected':>11} {'z':>7}"
    )
    failures = []
    for family, probes, make in families:
        fp = count_positives(f, probes, make)
        mean, sd = probes * p, math.sqrt(probes * p * (1 - p))
        z = (fp - mean) / sd
        row = {"r": r, "n": n, "family": family, "probes": probes, "fp": fp, "rate": fp / probes, "p": p,
               "expected_fp": mean, "z": z}  # fmt: skip
        stats["fpr"].append(row)
        emit(capsys, "fpr", header,
             f"{r:>3} {n:>9} {family:>6} {probes:>11} {fp:>10} {fp / probes:>11.3e} {p:>11.3e} {mean:>11.1f} {z:>+7.2f}")  # fmt: skip
        if abs(z) > SIGMAS:
            failures.append(row)
        assert mean >= 50 or SCALE < 1, "too few expected false positives to test anything"
    assert not failures, f"false-positive count outside {SIGMAS} sigma of the binomial mean: {failures}"


# ---------------------------------------------------------------------------------------------------------------
# (b) construction success vs overhead


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0, 1.0
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


def single_attempt_fails(keys: list[int], seed: int, overhead: float | None) -> bool:
    try:
        RibbonFilter(keys, seed=seed, overhead=overhead, max_attempts=1)
    except ConstructionError:
        return True
    return False


@pytest.mark.parametrize(("n", "trials"), [(100, 5000), (1000, 3000), (10_000, 1500), (100_000, 500)])
def test_per_attempt_failure_rate_at_default_overhead(
    n: int, trials: int, capsys: pytest.CaptureFixture[str], stats: dict[str, list[dict[str, Any]]]
) -> None:
    trials = max(int(trials * SCALE), 50)
    rng = random.Random(n)
    fails = 0
    for trial in range(trials):
        keys = list(range(trial * n, (trial + 1) * n))  # a disjoint key range per trial: independent trials
        fails += single_attempt_fails(keys, rng.getrandbits(64), None)
    lo, hi = wilson(fails, trials)
    eps = ref.default_overhead(n)
    rows = ref.initial_rows(n, eps)
    stats["construction"].append({"n": n, "overhead": eps, "rows": rows, "trials": trials, "failures": fails,
                                  "rate": fails / trials, "ci95": [lo, hi]})  # fmt: skip
    emit(capsys, "construction", f"{'n':>8} {'overhead':>9} {'rows':>9} {'trials':>7} {'fails':>6} {'rate':>8}   95% CI (bound 7%)",
         f"{n:>8} {eps:>9.4f} {rows:>9} {trials:>7} {fails:>6} {fails / trials:>8.4f}   [{lo:.4f}, {hi:.4f}]")  # fmt: skip
    assert fails / trials <= 0.07, f"per-attempt failure {fails / trials:.3f} at n={n} exceeds 7%"


@pytest.mark.parametrize(("n", "builds"), [(1000, 2000), (10_000, 300)])
def test_default_parameter_builds_never_raise(n: int, builds: int) -> None:
    builds = max(int(builds * SCALE), 20)
    rng = random.Random(n + 1)
    for build in range(builds):
        keys = list(range(build * n, (build + 1) * n))
        f = RibbonFilter(keys, seed=rng.getrandbits(64))  # a ConstructionError here fails the test
        assert all(f.contains_many(keys))


@pytest.mark.parametrize(("n", "trials"), [(1000, 1500), (10_000, 600), (100_000, 200)])
def test_failure_rate_does_not_increase_with_overhead(
    n: int, trials: int, capsys: pytest.CaptureFixture[str], stats: dict[str, list[dict[str, Any]]]
) -> None:
    trials = max(int(trials * SCALE), 50)
    base = ref.default_overhead(n)
    overheads = [base + d for d in (-0.02, -0.01, 0.0, 0.01, 0.02)]
    rng = random.Random(7 * n)
    fails = [0] * len(overheads)
    for trial in range(trials):  # the same key set and seed at every overhead: a paired comparison
        keys = list(range(trial * n, (trial + 1) * n))  # disjoint across trials, so the trials are independent
        seed = rng.getrandbits(64)
        for i, eps in enumerate(overheads):
            fails[i] += single_attempt_fails(keys, seed, eps)
    rates = [k / trials for k in fails]
    header = f"{'n':>8} {'overhead':>9} {'rows':>9} {'trials':>7} {'fails':>6} {'rate':>8}   (default overhead is the middle row)"
    for eps, k in zip(overheads, fails, strict=True):
        rows = ref.initial_rows(n, eps)
        stats["sweep"].append(
            {"n": n, "overhead": eps, "rows": rows, "trials": trials, "failures": k, "rate": k / trials}
        )
        emit(capsys, "sweep", header, f"{n:>8} {eps:>9.4f} {rows:>9} {trials:>7} {k:>6} {k / trials:>8.4f}")
    for i in range(len(rates) - 1):  # non-increasing within noise (3 sigma of the difference of two proportions)
        pooled = (rates[i] + rates[i + 1]) / 2
        sigma = math.sqrt(2 * pooled * (1 - pooled) / trials)
        assert rates[i + 1] <= rates[i] + 3 * sigma, (
            f"failure rate rose from {rates[i]:.4f} to {rates[i + 1]:.4f} at n={n}"
        )
    assert rates[2] <= 0.07
    if n >= 10_000 and SCALE >= 0.5:  # rows are rounded up to 64, so only large n resolves the +-2 pp steps
        pooled = (rates[0] + rates[-1]) / 2
        sigma = math.sqrt(2 * pooled * (1 - pooled) / trials)
        assert rates[0] - rates[-1] >= 3 * sigma, "2 pp less overhead must fail clearly more often than 2 pp more"


# ---------------------------------------------------------------------------------------------------------------
# (c) size at the defaults vs the documented sizing (rows rounded up to 64, plus the 64-byte header)

SIZE_CASES = [(n, 8) for n in (100, 1000, 10_000, 100_000, 1_000_000)] + [(10_000, r) for r in (1, 4, 16, 32)]


@pytest.mark.parametrize(("n", "r"), SIZE_CASES, ids=[f"n{n}-r{r}" for n, r in SIZE_CASES])
def test_size_at_defaults_matches_documented_sizing(
    n: int, r: int, capsys: pytest.CaptureFixture[str], stats: dict[str, list[dict[str, Any]]]
) -> None:
    eps = ref.default_overhead(n)  # mirror of rb_default_overhead
    rows = ref.initial_rows(n, eps)
    expected = 64 + rows * r // 8
    sizes, grown = [], 0
    for i in range(9):
        f = RibbonFilter(range(i * n, (i + 1) * n), fp_bits=r, seed=i * 7919 + 1)  # disjoint key ranges
        sizes.append(f.size_in_bytes)
        blob = f.to_bytes()
        built_rows = int.from_bytes(blob[24:32], "little")
        assert f.size_in_bytes == 64 + built_rows * r // 8
        grown += built_rows != rows  # a third or later attempt grows the table
    median = statistics.median(sizes)
    design = r * (1 + eps)  # DESIGN.md section 2: bits/key before rounding m up to 64 and before the header
    stats["size"].append({"n": n, "r": r, "overhead": eps, "rows": rows, "design_bits_per_key": design,
                          "expected_bits_per_key": 8 * expected / n, "measured_bits_per_key": 8 * median / n,
                          "sizes": sizes, "grown_builds": grown})  # fmt: skip
    emit(capsys, "size", f"{'n':>8} {'r':>3} {'overhead':>9} {'rows':>9} {'DESIGN b/key':>13} {'expected':>9} {'measured':>9} {'min..max':>15} {'grown':>5}",
         f"{n:>8} {r:>3} {eps:>9.4f} {rows:>9} {design:>13.3f} {8 * expected / n:>9.3f} {8 * median / n:>9.3f} "
         f"{8 * min(sizes) / n:>7.3f}..{8 * max(sizes) / n:<7.3f} {grown:>5}")  # fmt: skip
    assert abs(median - expected) / expected <= 0.03
    assert 8 * (median - 64) / n > r  # more than r bits per key, as any filter with FP = 2**-r must use
