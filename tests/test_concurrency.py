"""Concurrency: querying one filter from many threads, concurrent builds and loads, and GIL release.

An immutable ``RibbonFilter`` is safe to query concurrently from any number of threads: no field is written after
construction, there is no lazy state and the C core has no globals (DESIGN.md section 6). A query also holds a
reference to its filter, so dropping the last other reference while it runs cannot free it. Concurrent builds are
independent. These tests compare every concurrent answer with a precomputed single-threaded one.

The timing tests are inherently noisy (they depend on the machine, its load and its frequency governor). Their
thresholds are loose on purpose: they distinguish "the GIL is released during the C loop" from "it is held throughout"
(a factor of about 4 on four threads), not a 10% change in speed.
"""

from __future__ import annotations

import os
import sys
import sysconfig
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from pyribbon import ConstructionError, RibbonFilter

THREADS = 8
DURATION = 3.0


@pytest.fixture
def fast_thread_switching() -> Iterator[None]:
    """Switch threads every 10 microseconds so that Python-level queries interleave as much as possible."""
    old = sys.getswitchinterval()
    sys.setswitchinterval(1e-5)
    try:
        yield
    finally:
        sys.setswitchinterval(old)


def _mixed_probes() -> list[Any]:
    """Members and non-members of every key type: more than the 1024-key threshold above which the GIL is released."""
    probes: list[Any] = [*range(0, 60_000, 11), *range(-2000, 0), *range(10**9, 10**9 + 1500)]
    probes += [b"k%d" % i for i in range(1500)] + [f"s{i}é" for i in range(1500)] + [2**80 + i for i in range(200)]
    return probes


@pytest.mark.parametrize("how", ["built", "loaded"])
@pytest.mark.usefixtures("fast_thread_switching")
def test_eight_threads_query_one_shared_filter(how: str) -> None:
    built = RibbonFilter([*range(50_000), b"k7", "s7é", 2**80], fp_bits=4, seed=5)  # fp_bits=4: ~6% false positives
    blob = built.to_bytes()
    shared = built if how == "built" else RibbonFilter.from_buffer(blob)  # "loaded": zero copy over a shared buffer
    probes = _mixed_probes()
    expected = [k in built for k in probes]  # single-threaded reference answers
    assert any(expected) and not all(expected)  # both answers occur, so a wrong answer cannot hide
    barrier = threading.Barrier(THREADS)

    def worker(index: int) -> tuple[int, int]:
        barrier.wait()
        deadline = time.monotonic() + DURATION
        loops = bad = 0
        while time.monotonic() < deadline:
            if index % 3 == 0:
                got = [k in shared for k in probes]  # GIL held for every probe
            elif index % 3 == 1:
                got = shared.contains_many(probes)  # GIL released while probing
            else:
                lo = (loops * 977) % (len(probes) - 300)
                got = shared.contains_many(probes[lo : lo + 300])  # below the threshold: GIL held
                bad += got != expected[lo : lo + 300]
                loops += 1
                continue
            bad += got != expected
            loops += 1
        return loops, bad

    with ThreadPoolExecutor(THREADS) as pool:
        results = list(pool.map(worker, range(THREADS)))
    assert [bad for _, bad in results] == [0] * THREADS, results
    assert all(loops >= 3 for loops, _ in results), results  # every thread really ran for the whole period


@pytest.mark.usefixtures("fast_thread_switching")
def test_replacing_a_filter_while_other_threads_query_it() -> None:
    """A query holds a reference to its filter, so dropping the owner's reference mid-query cannot free it."""
    members = list(range(20_000))
    holder: dict[str, RibbonFilter] = {"f": RibbonFilter(members, seed=0)}
    stop = threading.Event()
    barrier = threading.Barrier(5)
    progress = [0] * 5  # one slot per thread, written only by that thread

    def reader(i: int) -> int:
        barrier.wait()
        rounds = 0
        while not stop.is_set():
            f = holder["f"]
            assert all(f.contains_many(members))  # every filter in play contains all members
            assert all(m in f for m in members[:200])
            rounds += 1
            progress[i] = rounds
        return rounds

    def replacer() -> int:
        barrier.wait()
        seed = 0
        while not stop.is_set():
            seed += 1
            holder["f"] = RibbonFilter(members, seed=seed)  # drops the previous filter while readers may be inside it
            progress[4] = seed
        return seed

    with ThreadPoolExecutor(5) as pool:
        futures = [pool.submit(reader, i) for i in range(4)] + [pool.submit(replacer)]
        # Run for at least 2 s and until every thread has finished a round: on a busy machine a thread can go that long
        # without being scheduled, which says nothing about the library.
        start = time.monotonic()
        while time.monotonic() - start < 2.0 or (not all(progress) and time.monotonic() - start < 60.0):
            time.sleep(0.05)
        stop.set()
        rounds = [f.result() for f in futures]
    assert all(r >= 1 for r in rounds), rounds


def test_threads_build_different_filters_concurrently() -> None:
    def spec(i: int) -> tuple[list[Any], dict[str, Any]]:
        lo = i * 400_000
        keys: list[Any] = list(range(lo, lo + 200_000)) if i % 2 == 0 else [f"key-{j}" for j in range(lo, lo + 200_000)]
        return keys, {"fp_bits": 1 + (i * 5) % 32, "seed": i * 2**59 + 3}

    specs = [spec(i) for i in range(THREADS)]
    # sequential reference: builds are deterministic, so the concurrent results must be byte-identical
    expected = [RibbonFilter(keys, **kw).to_bytes() for keys, kw in specs]
    assert len(set(expected)) == THREADS
    barrier = threading.Barrier(THREADS)

    def worker(i: int) -> list[bool]:
        keys, kw = specs[i]
        barrier.wait()
        ok = []
        for _ in range(3):
            f = RibbonFilter(keys, **kw)
            ok.append(f.to_bytes() == expected[i] and all(f.contains_many(keys)))
            try:  # failures in one thread must not disturb the others
                RibbonFilter(keys, overhead=0.0, max_attempts=1)
                ok.append(False)
            except ConstructionError:
                ok.append(True)
        return ok

    with ThreadPoolExecutor(THREADS) as pool:
        results = list(pool.map(worker, range(THREADS)))
    assert all(all(r) and len(r) == 6 for r in results), results


def test_threads_load_and_query_the_same_buffer_concurrently() -> None:
    keys = list(range(30_000))
    blob = RibbonFilter(keys, fp_bits=12, seed=9).to_bytes()
    barrier = threading.Barrier(THREADS)

    def worker(i: int) -> bool:
        barrier.wait()
        for _ in range(20):
            f = RibbonFilter.from_buffer(blob, verify=bool(i % 2))
            if not (all(f.contains_many(keys)) and f.to_bytes() == blob):
                return False
        return True

    with ThreadPoolExecutor(THREADS) as pool:
        assert all(pool.map(worker, range(THREADS)))


# ---------------------------------------------------------------------------------------------------------------
# GIL release


def _best_of(runs: int, body: Callable[[], Any]) -> float:
    best = float("inf")
    for _ in range(runs):
        start = time.perf_counter()
        body()
        best = min(best, time.perf_counter() - start)
    return best


@pytest.mark.slow
@pytest.mark.skipif((os.cpu_count() or 1) < 4, reason="needs at least 4 CPUs to show parallel speed-up")
def test_contains_many_runs_in_parallel_because_it_releases_the_gil() -> None:
    n = 2_000_000
    f = RibbonFilter(range(n), fp_bits=32)  # members with 32 columns: the probe loop dominates the time
    probes = list(range(n))
    f.contains_many(probes[:5000])  # warm up

    def one() -> None:
        assert all(f.contains_many(probes))

    single = _best_of(3, one)

    def four_threads() -> None:
        with ThreadPoolExecutor(4) as pool:
            for future in [pool.submit(one) for _ in range(4)]:
                future.result()

    parallel = _best_of(3, four_threads)
    # Four times the work. With the GIL held throughout it would take about 4x as long (measured here: ~1.7x, since
    # key hashing and list construction do hold the GIL); 3x leaves a wide margin for noise.
    assert parallel < 3.0 * single, f"4 threads took {parallel / single:.2f}x the single-thread time"


@pytest.mark.skipif(
    bool(sysconfig.get_config_var("Py_GIL_DISABLED")), reason="a free-threaded build has no GIL to hold"
)
def test_a_large_build_does_not_hold_the_gil() -> None:
    keys = list(range(3_000_000))
    ticks = 0
    gap = 0.0
    stop = threading.Event()
    started = threading.Event()

    def ticker() -> None:
        nonlocal ticks, gap
        last = time.perf_counter()
        started.set()
        while not stop.is_set():
            ticks += 1
            if ticks % 1000 == 0:
                now = time.perf_counter()
                gap = max(gap, now - last)
                last = now

    thread = threading.Thread(target=ticker)
    thread.start()
    started.wait()
    time.sleep(0.3)  # calibrate: how fast the pure-Python thread runs when nothing else does
    alone = ticks / 0.3
    ticks, gap = 0, 0.0
    start = time.perf_counter()
    f = RibbonFilter(keys)
    duration = time.perf_counter() - start
    during, longest_gap = ticks, gap
    stop.set()
    thread.join()
    assert all(f.contains_many(keys[::1000]))
    # While the build runs the other thread must keep going: banding and back-substitution (most of the build) run
    # without the GIL. If the whole build held it, `during` would be about 0 and the gap about the whole duration. The
    # threshold is low because a shared CI runner can take most of the CPU for a while (0.17 was seen on macOS Intel).
    assert during > 0.05 * alone * duration, f"ticker ran {during / (alone * duration):.2f} of its free speed"
    assert longest_gap < 0.7 * duration, f"ticker stalled {longest_gap:.2f}s of a {duration:.2f}s build"
