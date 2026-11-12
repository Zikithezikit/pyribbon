#!/usr/bin/env python3
"""Benchmark pyribbon against pyfusefilter (Xor8/16, Fuse8/16) and rbloom.

Measures bits/key at the *measured* false-positive rate, build time, single-query latency and batch throughput, and
writes a PNG (``--plot``), a GitHub-flavoured Markdown report (``--table``) and the raw numbers (``--json``).
See ``benchmarks/README.md`` for the method and ``python benchmarks/bench.py --help`` for the options.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gc
import hashlib
import itertools
import json
import math
import os
import platform
import re
import statistics
import sys
import sysconfig
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
pc_ns = time.perf_counter_ns
PROBE_START = 10**10  # counter where the negative probes start; members use counters 0..n-1 (disjoint by construction)
BIG_N = 10_000_000  # from here on: 3 build repeats at most and no build warm-up (a build takes seconds)
M64 = (1 << 64) - 1
# Okabe-Ito picks, validated for colour-vision deficiency (dataviz skill); marker + line style are the second encoding.
STYLE = {  # family -> (colour, marker)
    "pyribbon": ("#D55E00", "o"),
    "fuse": ("#009E73", "^"),
    "xor": ("#0072B2", "s"),
    "bloom": ("#CC79A7", "D"),
}


@dataclass
class Config:
    """Run parameters."""

    sizes: list[int]
    str_sizes: list[int]
    repeats: int
    qn: int  # keys per query set (single-call loop and batch)
    probes16: int  # false-positive probes for the 16-bit class (the 8-bit class uses probes8)
    probes8: int
    chunk: int
    seed: int


@dataclass
class Cell:
    """Key sets of one (regime, n) cell."""

    regime: str
    n: int
    cfg: Config
    members: list[Any]
    mem_q: list[Any]  # member queries, sampled with replacement
    non_q: list[Any]  # non-member queries (the first qn keys of the probe stream)


@dataclass
class Impl:
    """One benchmarked filter configuration."""

    key: str
    label: str
    family: str
    fp_bits: int  # 8 or 16: the target false-positive rate is 2**-fp_bits
    build: Callable[[list[Any], str], Any]
    size_bits: Callable[[Any], float]
    batch: Callable[[Any, list[Any]], Any] | None = None  # None: no batch API, the per-key loop is measured
    count_fp: Callable[[Any, list[Any], dict[str, Any]], int] | None = None
    diag: bool = False  # diagnostic variant: reported in the diagnostics section, not in the headline tables


@dataclass
class Lib:
    """A library under test: its configurations plus an optional diagnostics hook."""

    name: str
    version: str
    impls: list[Impl]
    diagnostics: Callable[[dict[str, Any], Cell], dict[str, Any]] | None = None


# ---------------------------------------------------------------------------------------------------------------------
# keys, statistics, timing
# ---------------------------------------------------------------------------------------------------------------------


def keys_at(regime: str, counters: Any, seed: int) -> list[Any]:
    """Fresh key objects for an array of counters. ``int``: distinct pseudo-random 63-bit ints (a bijective mixer, so
    distinct counters give distinct keys); ``str``: ``'user:'`` plus an 11-digit counter (16 characters)."""
    import numpy as np

    c = np.asarray(counters, dtype=np.uint64)
    if regime == "str":
        return [f"user:{i:011d}" for i in c.tolist()]
    u = np.uint64
    m = u((1 << 63) - 1)
    z = (c + u((seed * 0x9E3779B97F4A7C15) & ((1 << 63) - 1))) & m
    z = ((z ^ (z >> u(30))) * u(0xBF58476D1CE4E5B9)) & m
    z = ((z ^ (z >> u(27))) * u(0x94D049BB133111EB)) & m
    z ^= z >> u(31)
    return z.tolist()


def make_keys(regime: str, lo: int, hi: int, seed: int) -> list[Any]:
    """Keys for counters ``lo..hi-1``."""
    import numpy as np

    return keys_at(regime, np.arange(lo, hi, dtype=np.uint64), seed)


def stat(values: Sequence[float]) -> dict[str, Any]:
    """Median, min, max, quartiles and the raw values of repeated measurements."""
    v = sorted(values)
    q = statistics.quantiles(v, n=4, method="inclusive") if len(v) > 1 else [v[0]] * 3
    return {"median": statistics.median(v), "min": v[0], "max": v[-1], "q1": q[0], "q3": q[2], "values": list(values)}


def scaled(s: dict[str, Any], k: float) -> dict[str, Any]:
    """The summary statistics of ``s`` multiplied by ``k`` (unit conversion)."""
    return {name: s[name] * k for name in ("median", "min", "max", "q1", "q3")}


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h


def time_calls(
    run: Callable[..., Any],
    repeats: int,
    warmup: int,
    setup: Callable[[], tuple[Any, ...]] | None = None,
    cleanup: Callable[[Any], None] | None = None,
) -> tuple[list[int], Any]:
    """Wall time (ns) of ``run(*setup())`` over ``repeats`` runs after ``warmup`` untimed ones, GC off while timed.

    Returns the timings and the object produced by the last run (the caller owns it)."""
    times: list[int] = []
    last = None
    for i in range(warmup + repeats):
        if last is not None and cleanup is not None:
            cleanup(last)
        last = None
        args = setup() if setup else ()
        gc.collect()
        gc.disable()
        try:
            t0 = pc_ns()
            last = run(*args)
            t1 = pc_ns()
        finally:
            gc.enable()
        if i >= warmup:
            times.append(t1 - t0)
    return times, last


def _empty(keys: list[Any]) -> None:
    for _ in keys:
        pass


def _loop_in(f: Any, keys: list[Any]) -> None:
    for k in keys:
        k in f  # noqa: B015


def _loop_call(fn: Callable[[Any], Any], keys: list[Any]) -> None:
    for k in keys:
        fn(k)


def _loop_call2(fn: Callable[[Any, Any], Any], arg: Any, keys: list[Any]) -> None:
    for k in keys:
        fn(k, arg)


def per_call_ns(loop: Callable[[list[Any]], None], keys: list[Any], repeats: int) -> dict[str, Any]:
    """ns per iteration of ``loop(keys)`` with the empty ``for`` loop over the same keys subtracted.

    The empty loop is timed right before the real one in every repeat, so drift cancels. The first pass is a warm-up.
    ``median``/``min``/``max`` are the net figures; ``raw_median`` and ``empty_median`` are reported alongside."""
    net, raw, empty = [], [], []
    m = len(keys)
    for i in range(repeats + 1):
        gc.collect()
        gc.disable()
        try:
            t0 = pc_ns()
            _empty(keys)
            t1 = pc_ns()
            loop(keys)
            t2 = pc_ns()
        finally:
            gc.enable()
        if i:
            empty.append((t1 - t0) / m)
            raw.append((t2 - t1) / m)
            net.append(((t2 - t1) - (t1 - t0)) / m)
    s = stat(net)
    s["raw_median"] = statistics.median(raw)
    s["empty_median"] = statistics.median(empty)
    return s


def batch_stats(call: Callable[[list[Any]], Any], mem: list[Any], non: list[Any], repeats: int) -> dict[str, Any]:
    """Throughput (keys/s) of ``call`` on member and non-member batches, and of a 50/50 mix of the two."""
    tm, tn = [], []
    for i in range(repeats + 1):
        gc.collect()
        gc.disable()
        try:
            t0 = pc_ns()
            call(mem)
            t1 = pc_ns()
            call(non)
            t2 = pc_ns()
        finally:
            gc.enable()
        if i:
            tm.append(t1 - t0)
            tn.append(t2 - t1)
    m = len(mem)
    return {
        "member": stat([1e9 * m / t for t in tm]),
        "non_member": stat([1e9 * len(non) / t for t in tn]),
        "mixed": stat([1e9 * (m + len(non)) / (a + b) for a, b in zip(tm, tn, strict=True)]),
    }


# ---------------------------------------------------------------------------------------------------------------------
# libraries under test (imported lazily so --help works without the optional baselines)
# ---------------------------------------------------------------------------------------------------------------------


def pkg_version(name: str) -> str:
    """Installed distribution version, or ``not installed``."""
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "not installed"


def _hash_int(k: int) -> int:
    """Cheap deterministic 63-bit mix of an int (Fibonacci hashing), the ``hash_func`` given to rbloom for ints."""
    return ((k * 0x9E3779B97F4A7C15) & M64) >> 1


def _hash_str(s: str) -> int:
    """Deterministic 63-bit hash of a str (xxh64 of the UTF-8 bytes), the ``hash_func`` given to rbloom for str."""
    try:
        import xxhash

        return xxhash.xxh64_intdigest(s.encode()) >> 1
    except ImportError:
        return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "little") >> 1


def _load_pyribbon() -> Lib:
    import pyribbon
    from pyribbon import RibbonFilter

    impls = [
        Impl(
            f"pyribbon{b}",
            f"pyribbon fp{b}",
            "pyribbon",
            b,
            build=lambda keys, regime, b=b: RibbonFilter(keys, fp_bits=b),
            size_bits=lambda f: 8.0 * f.size_in_bytes,
            batch=lambda f, keys: f.contains_many(keys),
            count_fp=lambda f, chunk, cache: sum(f.contains_many(chunk)),
        )
        for b in (8, 16)
    ]
    return Lib("pyribbon", pyribbon.__version__, impls)


_FUSE_SPECS = [  # class, family, C prefix, C struct, C populate function, fingerprint bits
    ("Xor8", "xor", "xor8", "xor8_t", "xor8_buffered_populate", 8),
    ("Xor16", "xor", "xor16", "xor16_t", "xor16_buffered_populate", 16),
    ("Fuse8", "fuse", "binary_fuse8", "binary_fuse8_t", "binary_fuse8_populate", 8),
    ("Fuse16", "fuse", "binary_fuse16", "binary_fuse16_t", "binary_fuse16_populate", 16),
]


def _load_pyfusefilter() -> Lib:
    import pyfusefilter.pyfusefilter as pfm
    from pyfusefilter._xorfilter import ffi, lib

    impls = []
    for cls_name, family, prefix, _, _, bits in _FUSE_SPECS:
        cls = getattr(pfm, cls_name)
        contain = getattr(lib, f"{prefix}_contain")
        attr = f"_{cls_name}__filter"  # the cdata pointer pyfusefilter keeps; used only for the FPR fast path below

        def count(f: Any, chunk: list[Any], cache: dict[str, Any], contain: Any = contain, attr: str = attr) -> int:
            # Same arithmetic as f.contains(k) (pfm.hash, then the C probe), with the hashing shared by all four
            # filters per chunk. Equality with the per-key path is asserted for every filter before it is used.
            if "pf_hash" not in cache:
                cache["pf_hash"] = list(map(pfm.hash, chunk))
            return sum(map(contain, cache["pf_hash"], itertools.repeat(getattr(f, attr))))

        impls.append(
            Impl(
                cls_name.lower(),
                cls_name,
                family,
                bits,
                build=lambda keys, regime, cls=cls: cls(keys),
                size_bits=lambda f: 8.0 * f.size_in_bytes(),
                count_fp=count,
            )
        )

    def diagnostics(built: dict[str, Any], cell: Cell) -> dict[str, Any]:
        reps, n = cell.cfg.repeats, cell.n
        out: dict[str, Any] = {"raw_probe": {}, "core_build": {}}
        shipped = pfm.hash  # the exact hash pyfusefilter applies to every key
        times, _ = time_calls(
            lambda: list(map(shipped, cell.members)), reps if n < BIG_N else 3, 0 if n >= BIG_N else 1
        )
        out["hash_bulk_ns_per_key"] = scaled(stat(times), 1 / n)
        out["hash_call_ns"] = per_call_ns(lambda ks: _loop_call(shipped, ks), cell.mem_q, reps)
        hashes = list(map(shipped, cell.members))
        hs_mem, hs_non = list(map(shipped, cell.mem_q)), list(map(shipped, cell.non_q))
        for cls_name, _, prefix, ctype, populate, _ in _FUSE_SPECS:
            key = cls_name.lower()
            contain, alloc, free = (getattr(lib, f"{prefix}_{s}") for s in ("contain", "allocate", "free"))
            ptr = getattr(built[key], f"_{cls_name}__filter")
            out["raw_probe"][key] = {
                "member": per_call_ns(lambda ks, c=contain, p=ptr: _loop_call2(c, p, ks), hs_mem, reps),
                "non_member": per_call_ns(lambda ks, c=contain, p=ptr: _loop_call2(c, p, ks), hs_non, reps),
            }

            populate_fn = getattr(lib, populate)

            def run(arr: Any, alloc: Any = alloc, populate: Any = populate_fn, ctype: str = ctype) -> Any:
                flt = ffi.new(ctype + " *")
                if not alloc(n, flt) or not populate(arr, n, flt):
                    raise RuntimeError("pyfusefilter core build failed")
                return flt

            times, last = time_calls(
                run,
                reps if n < BIG_N else 3,
                0 if n >= BIG_N else 1,
                setup=lambda: (ffi.new("uint64_t[]", hashes),),
                cleanup=free,
            )
            free(last)
            out["core_build"][key] = scaled(stat(times), 1 / n)
        return out

    return Lib("pyfusefilter", pkg_version("pyfusefilter"), impls, diagnostics)


def _load_rbloom() -> Lib:
    from rbloom import Bloom

    def build(keys: list[Any], regime: str, fpr: float) -> Any:
        f = Bloom(len(keys), fpr, _hash_str if regime == "str" else _hash_int)
        f.update(keys)
        return f

    def build_builtin(keys: list[Any], regime: str, fpr: float) -> Any:
        f = Bloom(len(keys), fpr)
        f.update(keys)
        return f

    impls: list[Impl] = []
    for b in (8, 16):
        fpr = 2.0**-b
        size = lambda f: float(f.size_in_bits)  # noqa: E731
        impls.append(Impl(f"rbloom{b}", f"rbloom 2^-{b}", "bloom", b, lambda k, r, fpr=fpr: build(k, r, fpr), size))
        impls.append(
            Impl(
                f"rbloom{b}b",
                f"rbloom 2^-{b}, builtin hash()",
                "bloom",
                b,
                lambda k, r, fpr=fpr: build_builtin(k, r, fpr),
                size,
                diag=True,
            )
        )

    def diagnostics(built: dict[str, Any], cell: Cell) -> dict[str, Any]:
        fn = _hash_str if cell.regime == "str" else _hash_int
        return {"hash_call_ns": per_call_ns(lambda ks: _loop_call(fn, ks), cell.mem_q, cell.cfg.repeats)}

    return Lib("rbloom", pkg_version("rbloom"), impls, diagnostics)


def load_libs(skipped: list[str]) -> list[Lib]:
    """Import every library that is installed; record a message for each one that is not."""
    libs = []
    for name, loader in (("pyribbon", _load_pyribbon), ("pyfusefilter", _load_pyfusefilter), ("rbloom", _load_rbloom)):
        try:
            libs.append(loader())
        except ImportError as e:
            skipped.append(f"{name}: skipped, cannot import ({e}); install it with `pip install -e '.[bench]'`")
    return libs


# ---------------------------------------------------------------------------------------------------------------------
# machine information
# ---------------------------------------------------------------------------------------------------------------------


def _read(path: str) -> str | None:
    try:
        return Path(path).read_text().strip()
    except OSError:
        return None


def pin_cpu(cpu: int | None) -> int | None:
    """Pin the process to one CPU (the highest allowed one unless given); returns it, or None where unsupported."""
    try:
        allowed = os.sched_getaffinity(0)
        target = cpu if cpu is not None else max(allowed)
        os.sched_setaffinity(0, {target})
        return target
    except (AttributeError, OSError, ValueError):
        return None


def machine_info(cpu: int | None, libs: list[Lib]) -> dict[str, str]:
    """Ordered label -> value description of the machine and the software under test."""
    model = next(
        (
            ln.split(":", 1)[1].strip()
            for ln in (_read("/proc/cpuinfo") or "").splitlines()
            if ln.startswith("model name")
        ),
        "",
    )
    model = model or platform.processor() or platform.machine()
    cpu_dir = f"/sys/devices/system/cpu/cpu{cpu if cpu is not None else 0}/cpufreq"
    gov, cur, top = (_read(f"{cpu_dir}/{n}") for n in ("scaling_governor", "scaling_cur_freq", "cpuinfo_max_freq"))
    no_turbo = _read("/sys/devices/system/cpu/intel_pstate/no_turbo")
    info = {
        "CPU": re.sub(r"\((R|TM)\)", "", model).replace("  ", " "),
        "Logical CPUs": f"{os.cpu_count()}, benchmark pinned to CPU {cpu}"
        if cpu is not None
        else f"{os.cpu_count()}, not pinned",
        "Frequency scaling governor": gov or "not readable",
        "CPU frequency": (f"{int(cur) / 1e6:.2f} GHz at start" if cur else "not readable")
        + (f", max {int(top) / 1e6:.2f} GHz" if top else "")
        + ({"0": ", turbo enabled", "1": ", turbo disabled"}.get(no_turbo or "", "")),
        "OS / kernel": f"{platform.system()} {platform.release()} ({platform.platform()})",
        "Python": f"{platform.python_implementation()} {platform.python_version()}, built with {platform.python_compiler()}"
        + (", free-threaded" if sysconfig.get_config_var("Py_GIL_DISABLED") else ""),
        "Python build flags": f"CC={sysconfig.get_config_var('CC')}; CFLAGS={sysconfig.get_config_var('CFLAGS')}",
    }
    try:
        import pyribbon._ribbon as ext

        blob = Path(ext.__file__).read_bytes()
        cc = sorted(
            {m.decode(errors="replace") for m in re.findall(rb"(?:GCC: \([^\x00]*|clang version [^\x00]*)", blob)}
        )
        info["pyribbon extension"] = (
            f"{Path(ext.__file__).name}; compiler recorded in the binary: {', '.join(cc) or 'not found'}"
        )
        info["pyribbon build flags"] = (
            "setup.py adds none (/std:c11 on Windows only): the interpreter's CFLAGS above are used"
        )
    except (ImportError, OSError):
        pass
    for lib in libs:
        info[f"{lib.name} version"] = lib.version
    info["Other packages"] = ", ".join(f"{p} {pkg_version(p)}" for p in ("xxhash", "cffi", "numpy", "matplotlib"))
    return info


# ---------------------------------------------------------------------------------------------------------------------
# measurement of one (regime, n) cell
# ---------------------------------------------------------------------------------------------------------------------


def measure_fpr(built: list[tuple[Impl, Any]], regime: str, cfg: Config) -> dict[str, tuple[int, int]]:
    """Count false positives on the shared probe stream. Returns filter key -> (false positives, probes)."""
    chunks = {8: -(-cfg.probes8 // cfg.chunk), 16: -(-cfg.probes16 // cfg.chunk)}
    counts = {impl.key: 0 for impl, _ in built}
    for c in range(max(chunks.values())):
        chunk = make_keys(regime, PROBE_START + c * cfg.chunk, PROBE_START + (c + 1) * cfg.chunk, cfg.seed)
        cache: dict[str, Any] = {}
        for impl, f in built:
            if c < chunks[impl.fp_bits]:
                fn = impl.count_fp or (lambda f, ch, cache: sum(map(f.__contains__, ch)))
                counts[impl.key] += fn(f, chunk, cache)
    return {impl.key: (counts[impl.key], chunks[impl.fp_bits] * cfg.chunk) for impl, _ in built}


def run_cell(regime: str, n: int, libs: list[Lib], cfg: Config, say: Callable[[str], None]) -> dict[str, Any]:
    """Run every measurement for one key regime and size."""
    members = make_keys(regime, 0, n, cfg.seed)
    # Member queries are random members (with replacement), regenerated as fresh objects in query order so that they
    # have the same memory layout as the non-member queries (a random subset of `members` would be scattered over
    # n Python objects and pay cache misses that the non-members do not).
    import numpy as np

    mem_q = keys_at(regime, np.random.default_rng(cfg.seed * 1_000_003 + n).integers(0, n, cfg.qn), cfg.seed)
    non_q = make_keys(regime, PROBE_START, PROBE_START + cfg.qn, cfg.seed)
    cell = Cell(regime, n, cfg, members, mem_q, non_q)
    big = n >= BIG_N
    build_reps = min(cfg.repeats, 3) if big else cfg.repeats
    out: dict[str, Any] = {"regime": regime, "n": n, "build_repeats": build_reps, "filters": {}, "diag": {}}
    built: list[tuple[Impl, Any]] = []
    for lib in libs:
        for impl in lib.impls:
            times, f = time_calls(lambda impl=impl: impl.build(members, regime), build_reps, 0 if big else 1)
            if not all(map(f.__contains__, mem_q)):
                raise RuntimeError(f"{impl.label} has a false negative at n={n} ({regime}): correctness failure")
            r: dict[str, Any] = {
                "label": impl.label,
                "family": impl.family,
                "fp_bits": impl.fp_bits,
                "diag": impl.diag,
                "batch_native": impl.batch is not None,
                "bits_per_key": impl.size_bits(f) / n,
                "build_ns": stat(times),
                "lat_member_ns": per_call_ns(lambda ks, f=f: _loop_in(f, ks), mem_q, cfg.repeats),
                "lat_non_member_ns": per_call_ns(lambda ks, f=f: _loop_in(f, ks), non_q, cfg.repeats),
            }
            call = (lambda ks, f=f, b=impl.batch: b(f, ks)) if impl.batch else (lambda ks, f=f: [k in f for k in ks])
            r["batch_kps"] = batch_stats(call, mem_q, non_q, cfg.repeats)
            out["filters"][impl.key] = r
            built.append((impl, f))
            say(
                f"  {impl.label:<28} {r['bits_per_key']:6.2f} bits/key  build {scaled(r['build_ns'], 1 / n)['median']:8.1f} ns/key"
                f"  query {r['lat_member_ns']['median']:6.1f}/{r['lat_non_member_ns']['median']:6.1f} ns (member/non)"
                f"  batch {r['batch_kps']['mixed']['median'] / 1e6:7.2f} Mkeys/s"
            )
    # The fast FPR paths must agree with the per-key path before they are trusted.
    sample = non_q[: min(len(non_q), 20_000)]
    for impl, f in built:
        if impl.count_fp is not None and impl.count_fp(f, sample, {}) != sum(map(f.__contains__, sample)):
            raise RuntimeError(f"fast FPR path of {impl.label} disagrees with the per-key path")
    t_fpr = time.perf_counter()
    fpr_counts = measure_fpr(built, regime, cfg)
    say(
        f"  false-positive rates measured on {cfg.probes8:,} / {cfg.probes16:,} probes in {time.perf_counter() - t_fpr:.1f} s"
    )
    for key, (fp, probes) in fpr_counts.items():
        r = out["filters"][key]
        lo, hi = wilson(fp, probes)
        r.update(fp=fp, probes=probes, fpr=fp / probes, fpr_lo=lo, fpr_hi=hi)
        if fp:
            r["min_bits"] = math.log2(probes / fp)
            r["overhead_bits"] = r["bits_per_key"] - r["min_bits"]
            r["overhead_pct"] = 100 * r["overhead_bits"] / r["min_bits"]
    for lib in libs:
        if lib.diagnostics:
            t_diag = time.perf_counter()
            out["diag"][lib.name] = lib.diagnostics({i.key: f for i, f in built if i in lib.impls}, cell)
            say(f"  diagnostics for {lib.name} took {time.perf_counter() - t_diag:.1f} s")
    return out


def rbloom_hash_check(libs: list[Lib]) -> dict[str, Any] | None:
    """One-off sanity check of rbloom: FPR on sequential ints with its default hash and with our hash_func."""
    if not any(lib.name == "rbloom" for lib in libs):
        return None
    from rbloom import Bloom

    n, probes = 10_000, 1_000_000
    res: dict[str, Any] = {"n": n, "probes": probes, "target": 2.0**-8}
    for name, hf in (("default hash()", None), ("hash_func", _hash_int)):
        f = Bloom(n, 2.0**-8, hf) if hf else Bloom(n, 2.0**-8)
        f.update(range(n))
        res[name] = sum(map(f.__contains__, range(n, n + probes))) / probes
    return res


# ---------------------------------------------------------------------------------------------------------------------
# report: Markdown
# ---------------------------------------------------------------------------------------------------------------------


def g(x: float, digits: int = 3) -> str:
    """Compact number with ``digits`` significant digits."""
    return f"{x:.{digits}g}"


def span(s: dict[str, Any], digits: int = 3) -> str:
    """``median [min, max]``."""
    return f"{g(s['median'], digits)} [{g(s['min'], digits)}, {g(s['max'], digits)}]"


def md_table(headers: list[str], rows: list[list[str]], left: int = 1) -> str:
    """GitHub-flavoured Markdown table (the first ``left`` columns left-aligned, the rest right-aligned)."""
    sep = ["---"] * left + ["---:"] * (len(headers) - left)
    return "\n".join("| " + " | ".join(r) + " |" for r in [headers, sep, *rows])


def _filters(cell: dict[str, Any], diag: bool = False) -> list[tuple[str, dict[str, Any]]]:
    return [(k, v) for k, v in cell["filters"].items() if v["diag"] == diag]


def verdict_rows(cell: dict[str, Any]) -> list[list[str]]:
    """pyribbon against the best other (non-diagnostic) filter of the same fingerprint class, per metric."""
    n = cell["n"]
    metrics: list[tuple[str, Callable[[dict[str, Any]], float | None], bool, str]] = [
        ("bits/key", lambda v: v["bits_per_key"], True, "{:.2f}"),
        ("bits/key above log2(1/FPR)", lambda v: v.get("overhead_bits"), True, "{:.2f}"),
        ("build ns/key", lambda v: v["build_ns"]["median"] / n, True, "{:.0f}"),
        ("`in` member ns", lambda v: v["lat_member_ns"]["median"], True, "{:.0f}"),
        ("`in` non-member ns", lambda v: v["lat_non_member_ns"]["median"], True, "{:.0f}"),
        ("batch Mkeys/s (50/50 mix)", lambda v: v["batch_kps"]["mixed"]["median"] / 1e6, False, "{:.2f}"),
    ]
    rows = []
    for bits in (8, 16):
        mine = cell["filters"].get(f"pyribbon{bits}")
        # rbloom with its builtin hash() is included: for int keys it is a sound configuration (see the notes).
        others = [(k, v) for k, v in cell["filters"].items() if v["family"] != "pyribbon" and v["fp_bits"] == bits]
        if not mine or not others:
            continue
        for name, fn, lower, fmt in metrics:
            vals = [(v["label"], fn(v)) for _, v in others if fn(v) is not None]
            me = fn(mine)
            if me is None or not vals:
                continue
            best_label, best = (min if lower else max)(vals, key=lambda t: t[1])
            delta = 100 * (me - best) / best
            win = delta < 0 if lower else delta > 0
            rows.append(
                [
                    f"{bits}-bit",
                    name,
                    fmt.format(me),
                    f"{fmt.format(best)} ({best_label})",
                    f"{delta:+.0f}%",
                    "pyribbon ahead" if win else "**pyribbon behind**",
                ]
            )
    return rows


def report_markdown(meta: dict[str, Any], results: list[dict[str, Any]]) -> str:
    """The whole ``benchmark.md``: machine block, parameters, summary, tables, notes."""
    out = ["# pyribbon benchmark", "", "## Machine and software", ""]
    out += [f"- **{k}**: {v}" for k, v in meta["machine"].items()]
    out += ["", "## Run", ""]
    out += [f"- **Date**: {meta['date']}", f"- **Command**: `{meta['command']}`"]
    out += [f"- **{k}**: {v}" for k, v in meta["parameters"].items()]
    out += [f"- {s}" for s in meta["skipped"]]
    ints = [c for c in results if c["regime"] == "int"]
    if ints:
        top = max(ints, key=lambda c: c["n"])
        out += ["", f"## Where pyribbon wins and loses (int keys, n = {top['n']:,})", ""]
        out += [md_table(["Class", "Metric", "pyribbon", "Best other", "Delta", "Verdict"], verdict_rows(top), left=2)]
        out += [
            "",
            "Delta is relative to the best other filter of the same fingerprint class, including rbloom with its builtin `hash()` "
            "(negative = pyribbon lower). The 'above log2(1/FPR)' rows move with the measured FPR, whose uncertainty is in the notes. "
            "Lower is better except for batch throughput. The batch row compares `contains_many` with the others' per-key loop, "
            "because none of them has a batch API. Generated from the data of this run, not hand-written.",
        ]
    for regime, title in (
        ("int", "int keys (pseudo-random 63-bit)"),
        ("str", "str keys (`'user:00000000042'`, 16 characters)"),
    ):
        cells = sorted((c for c in results if c["regime"] == regime), key=lambda c: c["n"])
        if not cells:
            continue
        sp, bd, sq, ba = [], [], [], []
        for c in cells:
            n = c["n"]
            for _, v in _filters(c):
                lab = v["label"]
                fpr = f"{g(v['fpr'])} [{g(v['fpr_lo'])}, {g(v['fpr_hi'])}]"
                ratio = v["fpr"] * 2 ** v["fp_bits"]
                sp.append(
                    [
                        lab,
                        f"{n:,}",
                        f"{v['bits_per_key']:.3f}",
                        fpr,
                        f"{v['fp']:,} / {v['probes']:,}",
                        f"{ratio:.2f}",
                        f"{v['min_bits']:.2f}" if "min_bits" in v else "n/a",
                        f"{v['overhead_bits']:.2f} ({v['overhead_pct']:.0f}%)" if "overhead_bits" in v else "n/a",
                    ]
                )
                bd.append([lab, f"{n:,}", span(scaled(v["build_ns"], 1e-9), 3), span(scaled(v["build_ns"], 1 / n), 3)])
                sq.append(
                    [
                        lab,
                        f"{n:,}",
                        span(v["lat_member_ns"]),
                        span(v["lat_non_member_ns"]),
                        g(v["lat_member_ns"]["raw_median"]),
                    ]
                )
                kind = "`contains_many`" if v["batch_native"] else "per-key loop"
                ba.append(
                    [lab, f"{n:,}", kind]
                    + [g(v["batch_kps"][k]["median"] / 1e6) for k in ("member", "non_member", "mixed")]
                )
        out += [
            "",
            f"## Results: {title}",
            "",
            "### Space at matched false-positive rate",
            "",
            md_table(
                [
                    "Filter",
                    "n",
                    "bits/key",
                    "measured FPR [95% CI]",
                    "FP / probes",
                    "FPR / 2^-bits",
                    "min bits/key = log2(1/FPR)",
                    "above minimum (bits/key, %)",
                ],
                sp,
            ),
            "",
            "### Build time (median [min, max] of the repeats; includes hashing the keys)",
            "",
            md_table(["Filter", "n", "seconds", "ns/key"], bd),
            "",
            "### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])",
            "",
            md_table(["Filter", "n", "member", "non-member", "member, loop overhead not subtracted"], sq),
            "",
            "### Batch query: million keys per second (median)",
            "",
            md_table(["Filter", "n", "API", "members", "non-members", "50/50 mix"], ba),
        ]
        dg = []
        for c in cells:
            n = c["n"]
            for _, v in _filters(c, diag=True):
                dg.append(
                    [
                        v["label"],
                        f"{n:,}",
                        f"{span(scaled(v['build_ns'], 1 / n))} build ns/key",
                        span(v["lat_member_ns"]),
                        span(v["lat_non_member_ns"]),
                        g(v["batch_kps"]["mixed"]["median"] / 1e6),
                    ]
                )
            d = c["diag"].get("pyfusefilter")
            if d:
                dg.append(
                    [
                        "pyfusefilter: Python hashing only",
                        f"{n:,}",
                        f"{span(d['hash_bulk_ns_per_key'])} build ns/key",
                        span(d["hash_call_ns"]),
                        "(same keys)",
                        "n/a",
                    ]
                )
                for key, p in d["raw_probe"].items():
                    dg.append(
                        [
                            f"pyfusefilter {key}: C core only (pre-hashed keys; probe via cffi call)",
                            f"{n:,}",
                            f"{span(d['core_build'][key])} build ns/key",
                            span(p["member"]),
                            span(p["non_member"]),
                            "n/a",
                        ]
                    )
            d = c["diag"].get("rbloom")
            if d:
                dg.append(
                    ["rbloom: `hash_func` call only", f"{n:,}", "n/a", span(d["hash_call_ns"]), "(same keys)", "n/a"]
                )
        out += [
            "",
            "### Diagnostic: Python-side hashing separated from the filter probe",
            "",
            md_table(["Variant", "n", "Build", "Member ns", "Non-member ns", "Batch Mkeys/s (50/50 mix)"], dg),
        ]
    out += notes(meta, results)
    return "\n".join(out) + "\n"


def notes(meta: dict[str, Any], results: list[dict[str, Any]]) -> list[str]:
    """How to read the numbers; the figures quoted come from this run."""
    p = meta["params"]
    chk = meta.get("rbloom_check")
    empty = [c["filters"][k]["lat_member_ns"]["empty_median"] for c in results for k in c["filters"]]
    flagged = sorted(
        {
            f"{v['label']} (n={c['n']:,}, {c['regime']}): {v['fpr'] * 2 ** v['fp_bits']:.2f}x"
            for c in results
            for _, v in _filters(c)
            if not 0.5 <= v["fpr"] * 2 ** v["fp_bits"] <= 2
        }
    )
    out = ["", "## Notes and caveats", ""]
    out += [
        "- **Same keys, same measured FPR.** Every filter is built from the same keys and its FPR is measured on the same "
        f"disjoint negative probes ({p['probes8']:,} for the 8-bit class, {p['probes16']:,} for the 16-bit class; keys differ from "
        "all members by construction). Fingerprint widths are discrete (8 or 16 bits) and Bloom filters are continuous, so each Bloom "
        "filter is sized for 2^-8 or 2^-16 and then *measured*; bits/key is reported together with the measured FPR and with the "
        "overhead above the information-theoretic minimum log2(1/FPR) bits/key, which compares filters with slightly different FPRs.",
        "- **FPR confidence.** Intervals are 95% Wilson intervals for the stated number of probes. The 16-bit filters have only a few "
        "hundred expected false positives, so their FPR (and therefore their 'above minimum' column) is known to roughly 5-10% only.",
        "- **FPR sanity.** "
        + (
            "All measured FPRs are within 0.5x-2x of 2^-bits."
            if not flagged
            else "Outside 0.5x-2x of the target: " + "; ".join(flagged) + "."
        ),
        "- **As shipped.** `pyfusefilter` hashes every key in Python (`str(key).encode()` then `xxhash.xxh64_intdigest`) on every call "
        "and has no batch query; `pyribbon` hashes inside the C call. The headline numbers include these costs because they are what a user "
        "gets. The diagnostic tables separate the Python hashing from the filter probe (the probe-only rows call the library's C function "
        "through cffi with a pre-hashed key; the sum of hashing and probe rows is a lower bound on the shipped call, the rest is Python call overhead). "
        "pyribbon cannot be split this way: its hash is part of the C call.",
        "- **rbloom hashing.** rbloom hashes keys with Python's `hash()` unless given a `hash_func`; for `str`/`bytes` that hash is salted per process "
        "(and cached in the str object), so it cannot be persisted and flatters repeated lookups of the same objects. The headline rbloom rows therefore pass an explicit deterministic "
        "`hash_func` (ints: a 64-bit multiplicative hash; str: xxh64 of the UTF-8 bytes), whose Python call cost is included and listed in the diagnostics. "
        "The 'builtin hash()' rows in the diagnostics use no callback and show rbloom's own probe cost; for int keys that is a sound configuration, so the win/loss summary counts it among the competitors."
        + (
            f" Check on {chk['n']:,} sequential ints and {chk['probes']:,} probes (target {chk['target']:.2e}): "
            f"default hash() gives FPR {chk['default hash()']:.2e}, our hash_func {chk['hash_func']:.2e}, so rbloom's FPR is sane with either."
            if chk
            else ""
        ),
        "- **Batch.** Only pyribbon has a batch API (`contains_many`). For every other library the batch figure is a per-key list comprehension "
        "`[k in f for k in keys]` (marked in the table). The 50/50 mix is the throughput of one member batch plus one non-member batch.",
        f"- **Single-query latency.** A tight Python `for` loop over {p['queries']:,} random member keys (sampled with replacement) or non-member keys, with the same loop "
        f"without the call timed in the same repeat and subtracted (median {g(statistics.median(empty), 3)} ns per empty iteration here). "
        "What remains still contains the `k in f` bytecodes (a few ns). The unsubtracted figure is in the last column.",
        f"- **Timing.** `time.perf_counter_ns`, GC disabled while timed, one warm-up pass, median and min/max of {p['repeats']} repeats "
        "(3 at n = 10^7, no warm-up build there). Keys are generated before timing. Build time includes allocation and hashing, but not key generation.",
        "- **Keys.** `int`: distinct pseudo-random 63-bit integers from a fixed-seed bijective mixer; `str`: `user:` + 11 digits, members 0..n-1, "
        "probes from 10^10 upwards. Query keys are fresh objects created in query order (so members and non-members have the same memory layout) and are the same objects in every repeat (CPython caches a str's hash, which only matters for rbloom's builtin hash rows).",
        "- **Machine.** Numbers are comparable between libraries within this run, not across machines. A `powersave`/`ondemand` governor adds noise; "
        "run on an otherwise idle machine, with turbo and the governor fixed if you can.",
    ]
    return out


# ---------------------------------------------------------------------------------------------------------------------
# report: plot
# ---------------------------------------------------------------------------------------------------------------------


def plot(meta: dict[str, Any], results: list[dict[str, Any]], path: Path) -> None:
    """2x3 panels for the int regime: space, build, FPR, member and non-member latency, batch throughput."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    cells = sorted((c for c in results if c["regime"] == "int"), key=lambda c: c["n"])
    if not cells:
        return
    ink, grid = "#1f2328", "#d8dce0"
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.edgecolor": "#8b949e",
            "axes.labelcolor": ink,
            "text.color": ink,
            "xtick.color": ink,
            "ytick.color": ink,
        }
    )
    fig, axes = plt.subplots(2, 3, figsize=(17, 9.5), constrained_layout=True)
    keys = [k for k, _ in _filters(cells[-1])]

    def series(
        key: str, get: Callable[[dict[str, Any], int], dict[str, float] | float | None]
    ) -> tuple[list[int], list[Any]]:
        xs, ys = [], []
        for c in cells:
            v = c["filters"].get(key)
            y = get(v, c["n"]) if v else None
            if y is not None:
                xs.append(c["n"])
                ys.append(y)
        return xs, ys

    def draw(
        ax: Any, key: str, get: Callable[[dict[str, Any], int], Any], *, diag: bool = False, label: str | None = None
    ) -> None:
        v = cells[-1]["filters"][key]
        colour, marker = STYLE[v["family"]]
        xs, ys = series(key, get)
        if not xs:
            return
        kw: dict[str, Any] = {
            "color": colour,
            "marker": marker,
            "linestyle": ":" if diag else ("-" if v["fp_bits"] == 8 else "--"),
            "markerfacecolor": "white" if (v["fp_bits"] == 16 or diag) else colour,
            "markersize": 4 if diag else 6.5,
            "linewidth": 1.1 if diag else 1.8,
            "label": label or v["label"],
        }
        if isinstance(ys[0], dict):  # (median, min, max) -> error bars over the repeats
            med = [y["median"] for y in ys]
            ax.errorbar(
                xs,
                med,
                yerr=[
                    [m - y["min"] for m, y in zip(med, ys, strict=True)],
                    [y["max"] - m for m, y in zip(med, ys, strict=True)],
                ],
                capsize=2,
                elinewidth=0.8,
                **kw,
            )
        else:
            ax.plot(xs, ys, **kw)

    ax_space, ax_build, ax_fpr, ax_non, ax_mem, ax_batch = axes.flat
    for k in keys:
        draw(ax_space, k, lambda v, n: v.get("overhead_bits"))
        draw(ax_build, k, lambda v, n: scaled(v["build_ns"], 1 / n))
        draw(ax_non, k, lambda v, n: v["lat_non_member_ns"])
        draw(ax_mem, k, lambda v, n: v["lat_member_ns"])
        draw(ax_batch, k, lambda v, n: scaled(v["batch_kps"]["mixed"], 1e-6))
        v = cells[-1]["filters"][k]
        xs, ys = series(k, lambda v, n: (v["fpr"], v["fpr_lo"], v["fpr_hi"]))
        if xs:
            colour, marker = STYLE[v["family"]]
            ax_fpr.errorbar(
                xs,
                [y[0] for y in ys],
                yerr=[[y[0] - y[1] for y in ys], [y[2] - y[0] for y in ys]],
                color=colour,
                marker=marker,
                linestyle="-" if v["fp_bits"] == 8 else "--",
                markerfacecolor=colour if v["fp_bits"] == 8 else "white",
                capsize=2,
                elinewidth=0.8,
                linewidth=1.2,
                markersize=5.5,
            )
    # Diagnostics (dotted): the filter probe without the Python-side hashing.
    last = cells[-1]
    for lib_key, sel in (("pyfusefilter", "fuse8"),):
        if lib_key in last["diag"]:
            for ax, which in ((ax_non, "non_member"), (ax_mem, "member")):
                xs = [c["n"] for c in cells if lib_key in c["diag"]]
                ys = [c["diag"][lib_key]["raw_probe"][sel][which] for c in cells if lib_key in c["diag"]]
                med = [y["median"] for y in ys]
                ax.plot(
                    xs,
                    med,
                    color=STYLE["fuse"][0],
                    marker="^",
                    markersize=4,
                    markerfacecolor="white",
                    linestyle=":",
                    linewidth=1.1,
                    label="Fuse8 probe only, pre-hashed (diagnostic)",
                )
    if "rbloom8b" in last["filters"]:
        draw(
            ax_non,
            "rbloom8b",
            lambda v, n: v["lat_non_member_ns"],
            diag=True,
            label="rbloom 2^-8, builtin hash (diagnostic)",
        )
        draw(
            ax_mem,
            "rbloom8b",
            lambda v, n: v["lat_member_ns"],
            diag=True,
            label="rbloom 2^-8, builtin hash (diagnostic)",
        )
        draw(
            ax_build,
            "rbloom8b",
            lambda v, n: scaled(v["build_ns"], 1 / n),
            diag=True,
            label="rbloom 2^-8, builtin hash (diagnostic)",
        )
        draw(
            ax_batch,
            "rbloom8b",
            lambda v, n: scaled(v["batch_kps"]["mixed"], 1e-6),
            diag=True,
            label="rbloom 2^-8, builtin hash (diagnostic)",
        )
    for lo, name in ((2**-8, "2^-8"), (2**-16, "2^-16")):
        ax_fpr.axhline(lo, color="#6e7781", linewidth=0.8, linestyle=":")
        ax_fpr.text(cells[-1]["n"], lo * 1.35, f"target {name}", fontsize=8, color="#57606a", va="bottom", ha="right")
    titles = [
        (ax_space, "Space above the minimum log2(1/FPR)", "bits/key above log2(1/measured FPR)"),
        (ax_build, "Build time", "ns per key (log)"),
        (ax_fpr, "Measured false-positive rate (95% CI)", "FPR (log)"),
        (ax_non, "Single query, non-member key", "ns per call of key in f (loop overhead removed, log)"),
        (ax_mem, "Single query, member key", "ns per call of key in f (loop overhead removed, log)"),
        (ax_batch, "Batch query, 50/50 members and non-members", "million keys/s (log); others: per-key loop"),
    ]
    for ax, title, ylabel in titles:
        ax.set_xscale("log")
        if ax is not ax_space:
            ax.set_yscale("log")
        ax.set_title(title, loc="left", fontsize=11)
        ax.set_ylabel(ylabel)
        ax.set_xlabel("number of keys n")
        ax.grid(True, color=grid, linewidth=0.6)
        ax.set_axisbelow(True)
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
    handles: dict[str, Any] = {}
    for ax in (ax_space, ax_non):
        for h, lab in zip(*ax.get_legend_handles_labels(), strict=True):
            handles.setdefault(lab, h)
    fig.legend(handles.values(), handles.keys(), loc="outside lower center", ncol=5, frameon=False, fontsize=10)
    m = meta["machine"]
    fig.suptitle(
        f"pyribbon vs pyfusefilter vs rbloom, int keys. {m['CPU']}, {m['Python'].split(',')[0]}, governor {m['Frequency scaling governor']}, "
        f"{meta['parameters']['Pinning']}, median of {meta['params']['repeats']} runs (bars: min-max), {meta['date'][:10]}",
        fontsize=11,
        x=0.01,
        ha="left",
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=140)
    plt.close(fig)


# ---------------------------------------------------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------------------------------------------------


def _size(s: str) -> int:
    return int(float(s))


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Command-line options."""
    p = argparse.ArgumentParser(
        description="Benchmark pyribbon against pyfusefilter (Xor8/16, Fuse8/16) and rbloom. Needs `pip install -e '.[bench]'`.",
        epilog="Full run: make bench. Smoke test: python benchmarks/bench.py --quick --out-dir /tmp/bench-quick",
    )
    p.add_argument(
        "--quick",
        action="store_true",
        help="tiny sizes and few probes (about 20 s); output goes to a temp dir unless --out-dir is given",
    )
    p.add_argument(
        "--sizes", type=_size, nargs="+", help="int-key sizes (default: 1e3 1e4 1e5 1e6 1e7; accepts 1e6 notation)"
    )
    p.add_argument(
        "--str-sizes",
        type=_size,
        nargs="+",
        help="str-key sizes (default: 1e4 1e6, or the largest --sizes entry if neither fits)",
    )
    p.add_argument("--repeats", type=int, help="timed repeats per measurement (default 7, 3 in --quick)")
    p.add_argument(
        "--probes",
        type=_size,
        help="false-positive probes for the 16-bit class; the 8-bit class uses a fifth (default 2e7)",
    )
    p.add_argument("--queries", type=_size, help="keys per single-query loop and batch (default 1e5)")
    p.add_argument("--seed", type=int, default=20261112, help="seed of the key generator and the query sampler")
    p.add_argument("--cpu", type=int, help="CPU to pin to (default: the highest allowed one)")
    p.add_argument(
        "--out-dir",
        type=Path,
        help="directory for benchmark.png/.md/.json (default: docs/, or a temp dir with --quick)",
    )
    p.add_argument("--plot", type=Path, help="PNG path (default: OUT_DIR/benchmark.png)")
    p.add_argument("--table", type=Path, help="Markdown path (default: OUT_DIR/benchmark.md)")
    p.add_argument("--json", type=Path, help="raw-results path (default: OUT_DIR/benchmark.json)")
    return p.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the benchmark and write the reports."""
    args = parse_args(argv)
    out_dir = args.out_dir or (Path(tempfile.mkdtemp(prefix="pyribbon-bench-")) if args.quick else ROOT / "docs")
    plot_path, table_path, json_path = (
        args.plot or out_dir / "benchmark.png",
        args.table or out_dir / "benchmark.md",
        args.json or out_dir / "benchmark.json",
    )
    sizes = args.sizes or ([1_000, 10_000] if args.quick else [1_000, 10_000, 100_000, 1_000_000, 10_000_000])
    str_sizes = args.str_sizes or (
        [1_000] if args.quick else [s for s in (10_000, 1_000_000) if s <= max(sizes)] or [max(sizes)]
    )
    probes16 = args.probes or (200_000 if args.quick else 20_000_000)
    probes8 = max(probes16 // 5, 1)
    cfg = Config(
        sorted(set(sizes)),
        sorted(set(str_sizes)),
        args.repeats or (3 if args.quick else 7),
        args.queries or (2_000 if args.quick else 100_000),
        probes16,
        probes8,
        min(1_000_000, probes8),
        args.seed,
    )
    skipped: list[str] = []
    libs = load_libs(skipped)
    if not any(lib.name == "pyribbon" for lib in libs):
        print("\n".join(skipped) or "pyribbon is not importable", file=sys.stderr)
        return 1

    def say(msg: str) -> None:
        print(msg, flush=True)

    cpu = pin_cpu(args.cpu)
    machine = machine_info(cpu, libs)
    say("== machine and software ==")
    for k, v in machine.items():
        say(f"{k}: {v}")
    for s in skipped:
        say(s)
    started = dt.datetime.now().astimezone()
    meta: dict[str, Any] = {
        "date": started.isoformat(timespec="seconds"),
        "command": "python " + " ".join([Path(sys.argv[0]).as_posix(), *(argv if argv is not None else sys.argv[1:])]),
        "machine": machine,
        "skipped": skipped,
        "params": {k: getattr(cfg, k) for k in ("repeats", "probes8", "probes16", "chunk", "seed")}
        | {"sizes": cfg.sizes, "str_sizes": cfg.str_sizes, "queries": cfg.qn, "quick": args.quick, "cpu": cpu},
        "parameters": {
            "Pinning": f"CPU {cpu}" if cpu is not None else "not pinned",
            "Key sizes (int)": ", ".join(f"{s:,}" for s in cfg.sizes),
            "Key sizes (str)": ", ".join(f"{s:,}" for s in cfg.str_sizes),
            "Repeats": f"{cfg.repeats} (at most 3 at n >= 10,000,000); statistics are median and min/max",
            "Query set": f"{cfg.qn:,} keys per loop/batch",
            "FPR probes": f"{cfg.probes8:,} (8-bit class), {cfg.probes16:,} (16-bit class), in chunks of {cfg.chunk:,}",
            "Seed": str(cfg.seed),
            "Mode": "quick (smoke test, numbers not meaningful)" if args.quick else "full",
        },
    }
    meta["rbloom_check"] = rbloom_hash_check(libs)
    results: list[dict[str, Any]] = []
    t_start = time.perf_counter()
    try:
        for regime, regime_sizes in (("int", cfg.sizes), ("str", cfg.str_sizes)):
            for n in regime_sizes:
                say(f"\n== {regime} keys, n = {n:,} ==")
                t0 = time.perf_counter()
                results.append(run_cell(regime, n, libs, cfg, say))
                say(f"  cell took {time.perf_counter() - t0:.1f} s")
                json_path.parent.mkdir(parents=True, exist_ok=True)
                json_path.write_text(json.dumps({"meta": meta, "results": results}, indent=1))
    finally:  # a failure in a late cell still leaves reports for the cells that finished
        if results:
            meta["elapsed_s"] = time.perf_counter() - t_start
            meta["parameters"]["Total run time"] = f"{meta['elapsed_s']:.0f} s" + (
                "" if len(results) == len(cfg.sizes) + len(cfg.str_sizes) else " (INCOMPLETE: the run failed)"
            )
            json_path.write_text(json.dumps({"meta": meta, "results": results}, indent=1))
            table_path.parent.mkdir(parents=True, exist_ok=True)
            table_path.write_text(report_markdown(meta, results))
            plot(meta, results, plot_path)
            say(f"\nwrote {plot_path}, {table_path}, {json_path} (total {meta['elapsed_s']:.0f} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
