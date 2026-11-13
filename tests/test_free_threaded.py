"""Free-threaded CPython: the extension must run without the GIL, and stay correct under many threads.

On a free-threaded build (``python3.14t``) threads really run in parallel, so these tests can expose a data race that
the GIL would hide. On other builds they still run, as plain stress tests. Every concurrent answer is compared with a
single-threaded one computed first.
"""

from __future__ import annotations

import array
import gc
import os
import subprocess
import sys
import sysconfig
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest

from pyribbon import RibbonFilter

THREADS = 16
DURATION = 3.0
FREE_THREADED = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))


@pytest.mark.skipif(not FREE_THREADED, reason="only a free-threaded build can re-enable the GIL on import")
@pytest.mark.skipif(os.environ.get("PYTHON_GIL") == "1", reason="the GIL was forced on")
def test_importing_the_extension_does_not_enable_the_gil() -> None:
    code = "import sys, pyribbon; sys.exit(1 if sys._is_gil_enabled() else 0)"
    env = {k: v for k, v in os.environ.items() if k != "PYTHON_GIL"}  # the default, as a user would run it
    done = subprocess.run([sys.executable, "-W", "error", "-c", code], env=env, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_many_threads_query_build_and_load_at_once() -> None:
    members = [*range(40_000), b"k1", "s1é", 2**80]
    shared = RibbonFilter(members, fp_bits=4, seed=3)  # fp_bits=4: about 6% false positives, so both answers occur
    blob = shared.to_bytes()
    loaded = RibbonFilter.from_buffer(blob)
    probes: list[Any] = [*range(0, 80_000, 7), b"k1", b"nope", "s1é", "x", 2**80, 2**81]
    ints = array.array("q", range(-500, 60_000, 5))
    expected = [k in shared for k in probes]
    expected_ints = shared.contains_many(ints)
    assert any(expected) and not all(expected)
    barrier = threading.Barrier(THREADS)

    def worker(index: int) -> int:
        barrier.wait()
        deadline = time.monotonic() + DURATION
        rounds = 0
        while time.monotonic() < deadline:
            kind = (index + rounds) % 6
            if kind == 0:
                assert [k in shared for k in probes] == expected
            elif kind == 1:
                assert loaded.contains_many(probes) == expected  # a list: hashed key by key, probed without the GIL
            elif kind == 2:
                assert shared.contains_many(ints) == expected_ints  # an integer buffer: hashed and probed without it
            elif kind == 3:
                other = RibbonFilter.from_buffer(blob, verify=bool(rounds % 2))  # many views of one bytes object
                assert other.to_bytes() == blob and all(m in other for m in members[:300])
            elif kind == 4:
                built = RibbonFilter(members[:20_000], fp_bits=4, seed=3 + index)  # concurrent builds
                assert all(built.contains_many(members[:20_000]))
                assert len(built) == 20_000
            else:
                gc.collect()  # the collector walks filters (tp_traverse) while other threads use them
                assert (loaded.fp_bits, len(loaded), loaded.size_in_bytes) == (4, len(members), len(blob))
            rounds += 1
        return rounds

    with ThreadPoolExecutor(THREADS) as pool:
        rounds = list(pool.map(worker, range(THREADS)))
    assert all(r >= 6 for r in rounds), rounds  # every thread ran every kind of operation


def test_dropping_filters_that_other_threads_are_probing() -> None:
    """A probe holds a reference to its filter, so the last owner letting go mid-probe cannot free it."""
    members = list(range(30_000))
    blob = RibbonFilter(members, seed=1).to_bytes()
    slot: list[RibbonFilter] = [RibbonFilter.from_buffer(blob)]
    stop = threading.Event()
    barrier = threading.Barrier(THREADS)
    progress = [0] * THREADS  # one slot per thread, written only by that thread

    def reader(i: int) -> int:
        barrier.wait()
        rounds = 0
        while not stop.is_set():
            f = slot[0]
            assert all(f.contains_many(members))
            assert all(m in f for m in members[:100])
            rounds += 1
            progress[i] = rounds
        return rounds

    def swapper(i: int) -> int:
        barrier.wait()
        swaps = 0
        while not stop.is_set():
            slot[0] = RibbonFilter.from_buffer(blob, verify=False)  # frees the previous filter, releases its view
            swaps += 1
            progress[i] = swaps
        return swaps

    with ThreadPoolExecutor(THREADS) as pool:
        futures = [pool.submit(reader, i) for i in range(THREADS - 2)]
        futures += [pool.submit(swapper, i) for i in (THREADS - 2, THREADS - 1)]
        # Run for DURATION and until every thread has finished a round: on a busy machine a thread can go that long
        # without being scheduled, which says nothing about the library.
        start = time.monotonic()
        while time.monotonic() - start < DURATION or (not all(progress) and time.monotonic() - start < 60.0):
            time.sleep(0.05)
        stop.set()
        counts = [f.result() for f in futures]
    assert all(c >= 1 for c in counts), counts
