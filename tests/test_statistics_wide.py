"""Statistical tests of width 128 (all marked slow): false-positive rate and construction success at the default overhead.

The same bounds and probe counts as ``test_statistics.py``, which covers width 64 and feeds ``docs/measurements.md``.
These tests write nothing to that file, so the published tables stay a record of one width. The sizing table for width 128
was calibrated up to 2^22 slots (docs/internals.md section 2), so the failure-rate test covers sizes up to 100,000 keys.
``PYRIBBON_STATS_SCALE`` shrinks every count as it does there.
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable, Iterable
from typing import Any

import pytest
from test_statistics import SCALE, SIGMAS, count_positives, plan_probes, wilson

from pyribbon import ConstructionError, RibbonFilter, Width

pytestmark = pytest.mark.slow

FPR_CASES = [(r, n) for n in (1_000, 100_000) for r in (1, 4, 8, 12, 16)]


@pytest.mark.parametrize(("r", "n"), FPR_CASES, ids=[f"r{r}-n{n}" for r, n in FPR_CASES])
def test_false_positive_rate_matches_two_to_the_minus_r(r: int, n: int) -> None:
    f = RibbonFilter(range(n), fp_bits=r, seed=777 + r, width=Width.W128)
    assert all(f.contains_many(range(n)))
    ints, aux = plan_probes(r)
    families: list[tuple[str, int, Callable[[int, int], Iterable[Any]]]] = [
        ("int", ints, lambda lo, hi: range(n + lo, n + hi)),
        ("str", aux, lambda lo, hi: [f"neg-{i}" for i in range(lo, hi)]),
    ]
    p = 2.0**-r
    for family, probes, make in families:
        fp = count_positives(f, probes, make)
        mean, sd = probes * p, math.sqrt(probes * p * (1 - p))
        assert abs(fp - mean) <= SIGMAS * sd, (
            f"{family}: {fp} false positives of {probes}, expected {mean:.1f} +- {sd:.1f}"
        )
        assert mean >= 50 or SCALE < 1, "too few expected false positives to test anything"


def _single_attempt_fails(keys: list[int], seed: int) -> bool:
    try:
        RibbonFilter(keys, seed=seed, max_attempts=1, width=Width.W128)
    except ConstructionError:
        return True
    return False


@pytest.mark.parametrize(("n", "trials"), [(100, 3000), (1000, 2000), (10_000, 1000), (100_000, 300)])
def test_per_attempt_failure_rate_at_default_overhead(n: int, trials: int) -> None:
    """The table is calibrated for 97% per attempt; the bound is the 7% the width-64 test uses."""
    trials = max(int(trials * SCALE), 50)
    rng = random.Random(n + 128)
    fails = sum(
        _single_attempt_fails(list(range(t * n, (t + 1) * n)), rng.getrandbits(64))  # a disjoint key range per trial
        for t in range(trials)
    )
    low, high = wilson(fails, trials)
    assert fails / trials <= 0.07, f"per-attempt failure {fails / trials:.3f} at n={n} (95% CI [{low:.3f}, {high:.3f}])"


@pytest.mark.parametrize(("n", "builds"), [(1000, 1000), (10_000, 200)])
def test_default_parameter_builds_never_raise(n: int, builds: int) -> None:
    builds = max(int(builds * SCALE), 20)
    rng = random.Random(n + 129)
    for build in range(builds):
        keys = list(range(build * n, (build + 1) * n))
        f = RibbonFilter(keys, seed=rng.getrandbits(64), width=Width.W128)  # a ConstructionError here fails the test
        assert all(f.contains_many(keys))
