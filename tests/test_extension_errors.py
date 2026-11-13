"""Error paths of the C extension that the behaviour tests do not reach: allocation failures, signals that arrive while
keys are collected, and buffers that declare an explicit byte order.

The memory-failure tests run a child interpreter under ``RLIMIT_AS``, so the extension's own ``malloc`` calls fail
for real. The limit is set a known distance above the current address-space size and every request that must fail
is several times larger than the room left, so none of them depends on allocator details. Linux only, and skipped
under the sanitizer job, whose shadow memory makes address-space limits meaningless.
"""

from __future__ import annotations

import ctypes
import itertools
import os
import signal
import subprocess
import sys
import textwrap
from collections.abc import Iterator

import pytest

from pyribbon import RibbonFilter

needs_rlimit = pytest.mark.skipif(
    not sys.platform.startswith("linux") or bool(os.environ.get("PYRIBBON_SANITIZED")),
    reason="needs RLIMIT_AS on Linux without sanitizer shadow memory",
)

# Child program: `limit(extra)` allows `extra` more bytes of address space; the failing call must raise MemoryError;
# afterwards the limit is lifted and the module must still work.
_CHILD = """
import array, itertools, resource
from pyribbon import RibbonFilter

def vm():
    with open("/proc/self/statm") as fh:
        return int(fh.read().split()[0]) * resource.getpagesize()

def limit(extra):
    resource.setrlimit(resource.RLIMIT_AS, (vm() + extra, resource.getrlimit(resource.RLIMIT_AS)[1]))

def unlimit():
    resource.setrlimit(resource.RLIMIT_AS, (resource.RLIM_INFINITY, resource.RLIM_INFINITY))

MiB = 1 << 20
"""


def _run_child(body: str) -> None:
    code = _CHILD + textwrap.dedent(body) + '\nunlimit()\nassert 7 in RibbonFilter([7])\nprint("child ok")\n'
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0 and "child ok" in done.stdout, done.stdout + done.stderr


@needs_rlimit
@pytest.mark.parametrize(
    "body",
    [
        pytest.param(  # the hash array of an integer buffer cannot be allocated (8 bytes per 1-byte item: 512 MiB)
            """
            arr = array.array("B", bytes(64 * MiB))
            f = RibbonFilter([1, 2, 3])
            limit(128 * MiB)
            for call in (lambda: RibbonFilter(arr), lambda: f.contains_many(arr)):
                try:
                    call()
                except MemoryError:
                    pass
                else:
                    raise SystemExit("no MemoryError")
            """,
            id="int-buffer-hash-array",
        ),
        pytest.param(  # the preallocation from a __len__ hint (8 MiB) fails
            """
            class Hinted:
                def __len__(self): return 1 << 20
                def __iter__(self): return iter([1, 2, 3])
            f = RibbonFilter([1])
            limit(2 * MiB)
            for call in (lambda: RibbonFilter(Hinted()), lambda: f.contains_many(Hinted())):
                try:
                    call()
                except MemoryError:
                    pass
                else:
                    raise SystemExit("no MemoryError")
            """,
            id="length-hint-preallocation",
        ),
        pytest.param(  # the hash array of an unsized iterable cannot keep growing
            """
            f = RibbonFilter([1])
            limit(48 * MiB)
            for call in (lambda: RibbonFilter(itertools.count()), lambda: f.contains_many(itertools.count())):
                try:
                    call()
                except MemoryError:
                    pass
                else:
                    raise SystemExit("no MemoryError")
            """,
            id="hash-array-growth",
        ),
        pytest.param(  # the hashes fit (16 MiB) but the core cannot allocate its ~35 MiB slot table: RB_E_NOMEM
            """
            arr = array.array("q", range(2_000_000))
            limit(24 * MiB)
            try:
                RibbonFilter(arr)
            except MemoryError:
                pass
            else:
                raise SystemExit("no MemoryError")
            """,
            id="core-build-nomem",
        ),
        pytest.param(  # the 256 MiB hash array fits, the 32 MiB result array does not
            """
            f = RibbonFilter(range(10))
            arr = array.array("B", bytes(32 * MiB))
            limit(264 * MiB)
            try:
                f.contains_many(arr)
            except MemoryError:
                pass
            else:
                raise SystemExit("no MemoryError")
            """,
            id="contains-many-result-array",
        ),
    ],
)
def test_allocation_failure_raises_memory_error_and_recovers(body: str) -> None:
    _run_child(body)


@pytest.mark.skipif(not hasattr(signal, "setitimer"), reason="needs setitimer")
def test_signal_handler_exception_interrupts_key_collection() -> None:
    class Tick(Exception):
        pass

    def handler(signum: int, frame: object) -> None:
        raise Tick

    f = RibbonFilter([1])
    old = signal.signal(signal.SIGALRM, handler)
    try:
        for call in (lambda it: RibbonFilter(it), f.contains_many):
            # A C iterator: no bytecode runs between keys, so only the extension's own check can run the handler.
            it = itertools.islice(itertools.count(), 20_000_000)
            signal.setitimer(signal.ITIMER_REAL, 0.05)
            with pytest.raises(Tick):
                call(it)
            assert next(it, None) is not None  # stopped early: the iterator was not drained first
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


@pytest.mark.parametrize(
    "ctype",
    [
        ctypes.c_int8,
        ctypes.c_uint8,
        ctypes.c_int16,
        ctypes.c_uint16,
        ctypes.c_int32,
        ctypes.c_uint32,
        ctypes.c_int64,
        ctypes.c_uint64,
    ],
)
def test_buffers_with_explicit_little_endian_format(ctype: type) -> None:
    # ctypes arrays export formats such as "<i": the extension must read them like the native ones
    values = [0, 1, 2, 3, 100, 101, 102]
    arr = (ctype * len(values))(*values)
    assert memoryview(arr).format.startswith("<")
    assert RibbonFilter(arr, seed=3).to_bytes() == RibbonFilter(values, seed=3).to_bytes()
    assert RibbonFilter(values, seed=3).contains_many(arr) == [True] * len(values)


def test_negative_one_overhead_is_rejected_not_taken_for_an_error() -> None:
    # -1.0 is also the error return of PyFloat_AsDouble, so the argument check must tell the two apart
    with pytest.raises(ValueError, match="overhead"):
        RibbonFilter([1, 2, 3], overhead=-1.0)
    with pytest.raises(TypeError):
        RibbonFilter([1, 2, 3], overhead="x")  # type: ignore[arg-type]


@pytest.mark.skipif(sys.version_info < (3, 12), reason="Python-level __buffer__ needs PEP 688 (3.12)")
def test_memory_error_from_buffer_export_is_not_swallowed() -> None:
    class Exhausted:
        def __buffer__(self, flags: int) -> memoryview:
            raise MemoryError("export failed")

        def __iter__(self) -> Iterator[int]:
            return iter([1])

    with pytest.raises(MemoryError, match="export failed"):
        RibbonFilter(Exhausted())  # type: ignore[arg-type]
    with pytest.raises(MemoryError, match="export failed"):
        RibbonFilter([1]).contains_many(Exhausted())  # type: ignore[arg-type]
