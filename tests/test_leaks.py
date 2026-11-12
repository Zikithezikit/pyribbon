"""Memory and reference leaks: RSS growth over build/load/query loops, reference counts, buffer exports, GC.

Linux only (RSS is read from ``/proc/self/statm``) and skipped under the sanitizer job, whose shadow memory inflates
RSS. Each loop runs a warm-up first, so allocator pools and caches have reached steady state; the measured growth
must then stay below ``LIMIT``. Every loop is sized so that a leak of the smallest plausible object per iteration
(the C struct, a hash array, the banding arrays) would exceed it: ``test_rss_probe_sees_a_deliberate_leak`` shows
the probe sees a leak of that size, and the loops assert that they really took the path they claim to test.
"""

from __future__ import annotations

import gc
import mmap
import os
import pickle
import sys
import weakref
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from pyribbon import ConstructionError, FormatError, RibbonFilter

pytestmark = [
    pytest.mark.skipif(not sys.platform.startswith("linux"), reason="RSS is read from /proc/self/statm"),
    pytest.mark.skipif(bool(os.environ.get("PYRIBBON_SANITIZED")), reason="sanitizer builds inflate RSS"),
]

LIMIT = 2 * 1024 * 1024
N = 10_000
KEYS = list(range(N))
BLOB = RibbonFilter(KEYS).to_bytes()


def rss() -> int:
    with open("/proc/self/statm") as fh:
        return int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")


def growth(body: Callable[[int], None], iterations: int) -> int:
    """RSS growth in bytes over ``iterations`` runs of ``body``, after a warm-up of a tenth as many."""
    body(max(5, iterations // 10))
    gc.collect()
    before = rss()
    body(iterations)
    gc.collect()
    return rss() - before


def assert_no_growth(body: Callable[[int], None], iterations: int) -> None:
    grown = growth(body, iterations)
    assert grown < LIMIT, f"RSS grew by {grown / 1e6:.1f} MB over {iterations} iterations"


def test_rss_probe_sees_a_deliberate_leak() -> None:
    hoard: list[bytes] = []

    def leak(k: int) -> None:
        for _ in range(k):
            # above glibc's maximum dynamic mmap threshold (32 MB): always fresh pages, never recycled heap holes,
            # whatever earlier tests allocated and freed
            hoard.append(b"\xaa" * 33_000_000)

    assert growth(leak, 2) > LIMIT  # 66 MB retained must register, or the thresholds below mean nothing
    hoard.clear()


# ---------------------------------------------------------------------------------------------------------------
# RSS loops


@pytest.mark.parametrize("fp_bits", [8, 32])
def test_build_and_free_loop(fp_bits: int) -> None:
    def body(k: int) -> None:
        for i in range(k):
            f = RibbonFilter(KEYS, fp_bits=fp_bits, seed=i)
            assert 0 in f and (N - 1) in f
            del f

    assert_no_growth(body, 300)


def test_from_buffer_and_free_loop() -> None:
    def body(k: int) -> None:
        for _ in range(k):
            f = RibbonFilter.from_buffer(BLOB)
            assert 5 in f
            del f

    assert_no_growth(body, 300)


def test_from_buffer_loop_on_a_tiny_filter() -> None:
    tiny = RibbonFilter([1, 2, 3]).to_bytes()

    def body(k: int) -> None:
        for _ in range(k):
            RibbonFilter.from_buffer(tiny, verify=False)

    assert_no_growth(body, 300_000)  # per-iteration objects are tiny, so the loop is long


def test_to_bytes_and_pickle_loop() -> None:
    f = RibbonFilter(KEYS)

    def body(k: int) -> None:
        for _ in range(k):
            assert f.to_bytes() == BLOB
            assert pickle.loads(pickle.dumps(f)).to_bytes() == BLOB

    assert_no_growth(body, 300)


def test_failed_construction_loop() -> None:
    def body(k: int) -> None:
        raised = 0
        for i in range(k):
            try:
                RibbonFilter(KEYS, overhead=0.0, max_attempts=1, seed=i)
            except ConstructionError:
                raised += 1
        assert raised == k  # 0.5% slack on 10000 keys: a single attempt always fails; the error path is what we measure

    assert_no_growth(body, 300)


def test_failed_load_loop() -> None:
    payload_flip = bytearray(BLOB)
    payload_flip[-1] ^= 1
    bad = [BLOB[:-1], BLOB[:10], BLOB + b"\0", b"NOTRIBBN" + BLOB[8:], bytes(payload_flip), b""]

    def body(k: int) -> None:
        raised = 0
        for i in range(k):
            try:
                RibbonFilter.from_buffer(bad[i % len(bad)])
            except FormatError:
                raised += 1
        assert raised == k

    assert_no_growth(body, 300_000)


def test_unsupported_key_error_paths_loop() -> None:
    f = RibbonFilter(KEYS)
    with_float = [*KEYS, 1.5]  # fails after hashing every key: the temporary hash array must be freed
    with_none = [*KEYS, None]
    lone_surrogate = [*KEYS, "\ud800"]

    def failing_generator() -> Any:
        yield from KEYS
        raise ZeroDivisionError

    def body(k: int) -> None:
        for _ in range(k):
            for call, error in (
                (lambda: RibbonFilter(with_float), TypeError),
                (lambda: RibbonFilter(lone_surrogate), UnicodeEncodeError),
                (lambda: RibbonFilter(failing_generator()), ZeroDivisionError),
                (lambda: RibbonFilter(KEYS, fp_bits=0), ValueError),
                (lambda: RibbonFilter(5), TypeError),  # type: ignore[arg-type]
                (lambda: f.contains_many(with_none), TypeError),
                (lambda: f.contains_many("abc"), TypeError),
                (lambda: 2.5 in f, TypeError),  # type: ignore[operator]
            ):
                with pytest.raises(error):
                    call()

    assert_no_growth(body, 300)


def test_contains_many_loops() -> None:
    f = RibbonFilter(KEYS)
    small = KEYS[:10]

    def body(k: int) -> None:
        for _ in range(k):
            assert all(f.contains_many(KEYS))  # the GIL-released path

    def small_body(k: int) -> None:
        for _ in range(k):
            assert all(f.contains_many(small))

    assert_no_growth(body, 300)
    assert_no_growth(small_body, 300_000)


def test_single_key_queries_of_every_type_loop() -> None:
    f = RibbonFilter([b"a", "a", 7, 2**100])
    keys: list[Any] = [b"abc", bytearray(b"abc"), memoryview(b"abc"), "abc\U0001f600", 12345, 2**200, -(2**70), True]

    def body(k: int) -> None:
        for i in range(k):
            keys[i % len(keys)] in f  # noqa: B015

    assert_no_growth(body, 1_000_000)


# ---------------------------------------------------------------------------------------------------------------
# reference counts and buffer exports


def test_buffer_refcount_returns_to_baseline() -> None:
    blob = RibbonFilter(KEYS).to_bytes()  # a fresh object, so its count is not shared with a constant
    baseline = sys.getrefcount(blob)
    f = RibbonFilter.from_buffer(blob)
    assert sys.getrefcount(blob) > baseline  # zero copy: the filter pins the very object it was given
    g = RibbonFilter.from_buffer(blob, verify=False)
    assert sys.getrefcount(blob) > baseline + 1
    del f
    del g
    assert sys.getrefcount(blob) == baseline
    for bad in (blob[:5], blob[:-1]):
        base = sys.getrefcount(bad)
        with pytest.raises(FormatError):
            RibbonFilter.from_buffer(bad)
        assert sys.getrefcount(bad) == base  # a failed load drops its reference at once
    big = bytes(blob) + b"x"
    base = sys.getrefcount(big)
    for _ in range(1000):
        with pytest.raises(FormatError):
            RibbonFilter.from_buffer(big)
    assert sys.getrefcount(big) == base


def test_key_objects_keep_their_refcounts() -> None:
    str_keys = [f"key-{i}-{'x' * (i % 7)}" for i in range(200)]
    big_ints = [2**100 + i for i in range(50)]
    byte_keys = [b"k%d" % i for i in range(50)]
    objects: list[Any] = [*str_keys, *big_ints, *byte_keys]
    before = [sys.getrefcount(o) for o in objects]
    f = RibbonFilter(objects)
    assert all(o in f for o in objects)
    assert all(f.contains_many(objects))
    g = RibbonFilter.from_buffer(f.to_bytes())
    assert all(o in g for o in objects)
    for bad_tail in (1.5, None, "\ud800"):
        with pytest.raises((TypeError, UnicodeEncodeError)):
            RibbonFilter([*objects, bad_tail])  # type: ignore[list-item]
        with pytest.raises((TypeError, UnicodeEncodeError)):
            f.contains_many([*objects, bad_tail])
    assert [sys.getrefcount(o) for o in objects] == before


def test_failing_key_object_is_released() -> None:
    class Bad:
        pass

    bad = Bad()
    base = sys.getrefcount(bad)
    f = RibbonFilter([1])
    for _ in range(1000):
        with pytest.raises(TypeError):
            bad in f  # type: ignore[operator]  # noqa: B015
        with pytest.raises(TypeError):
            RibbonFilter([1, bad])  # type: ignore[list-item]
    assert sys.getrefcount(bad) == base


def test_index_objects_are_released() -> None:
    class Idx:
        def __index__(self) -> int:
            return 10**30

    idx = Idx()
    base = sys.getrefcount(idx)
    f = RibbonFilter([10**30])
    for _ in range(1000):
        assert idx in f  # type: ignore[comparison-overlap]
    RibbonFilter([idx, idx])  # type: ignore[list-item]
    assert sys.getrefcount(idx) == base


def test_type_and_exception_refcounts_are_stable() -> None:
    def churn() -> None:
        for i in range(200):
            f = RibbonFilter(range(300), seed=i)
            RibbonFilter.from_buffer(f.to_bytes())
            pickle.loads(pickle.dumps(f))
            with pytest.raises(FormatError):
                RibbonFilter.from_buffer(b"x")
            with pytest.raises(ConstructionError):
                RibbonFilter(range(5000), overhead=0.0, max_attempts=1)

    churn()
    before = (sys.getrefcount(RibbonFilter), sys.getrefcount(FormatError), sys.getrefcount(ConstructionError))
    churn()
    assert (sys.getrefcount(RibbonFilter), sys.getrefcount(FormatError), sys.getrefcount(ConstructionError)) == before


def test_buffer_exports_are_released_after_every_kind_of_use() -> None:
    blob = BLOB
    data = bytearray(blob)
    key_bytearray = bytearray(b"key")
    key_view = memoryview(bytearray(b"key"))
    f = RibbonFilter([b"key", b"other"])
    for _ in range(100):
        RibbonFilter.from_buffer(data)
        with pytest.raises(FormatError):
            RibbonFilter.from_buffer(data[:-1])  # slicing copies; the failed load of the copy must release it too
        assert key_bytearray in f and key_view in f
        f.contains_many([key_bytearray, key_view])
        RibbonFilter([key_bytearray, key_view])
        with pytest.raises(TypeError):
            RibbonFilter([key_bytearray, 1.5])  # type: ignore[list-item]
    data.append(0)  # BufferError if any export were still held
    key_bytearray.append(0)
    key_view.release()  # BufferError ("exported buffers") if a key export leaked


def test_mmap_can_be_closed_after_filters_are_gone(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(BLOB)
    with path.open("rb") as fh:
        mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
        for _ in range(100):
            RibbonFilter.from_buffer(mm, verify=False)
        f = RibbonFilter.from_buffer(mm)
        with pytest.raises(BufferError):
            mm.close()
        del f
        mm.close()


# ---------------------------------------------------------------------------------------------------------------
# garbage collection


def test_gc_finds_nothing_after_a_mixed_workload() -> None:
    gc.collect()
    for i in range(50):
        f = RibbonFilter(range(500), seed=i)
        g = RibbonFilter.from_buffer(bytearray(f.to_bytes()))
        assert 3 in g and f.contains_many([1, 2]) == [True, True]
        pickle.loads(pickle.dumps(g))
        try:
            RibbonFilter([1, 1.5])  # type: ignore[list-item]
        except TypeError:
            pass
        try:
            RibbonFilter.from_buffer(b"nope")
        except FormatError:
            pass
        del f, g
    assert gc.collect() == 0  # no unreachable cycles were created
    assert gc.garbage == []


def test_filter_in_a_reference_cycle_with_its_buffer_owner_is_collected() -> None:
    """A filter references the object it was loaded from; if that object references the filter, the cycle must be
    collectable. This needs the filter type to take part in GC (``Py_TPFLAGS_HAVE_GC`` and ``tp_traverse``)."""

    class Owner(bytearray):
        filter: RibbonFilter

    owner = Owner(BLOB)
    owner.filter = RibbonFilter.from_buffer(owner)  # owner -> filter -> (buffer of) owner
    alive = weakref.ref(owner)
    del owner
    gc.collect()
    assert alive() is None, "filter and its buffer owner form an uncollectable cycle"
