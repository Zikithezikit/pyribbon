"""Property-based tests: no false negatives for any key type, size, fp_bits and seed; round trips; C vs reference.

Facts established by experiment (and by argument) before they were asserted:

* A filter's serialized bytes do not depend on the order of the keys. Banding succeeds iff the linear system is
  consistent, which is a property of the equation set, and the solution with every free variable set to zero is unique,
  so order only changes the intermediate echelon form, never the output. The same holds for the attempt that succeeds.
* Duplicate keys add no new equations. They change only ``num_keys`` (and, through ``n``, possibly the row count).
"""

from __future__ import annotations

import array
import copy
import pickle
import random
import struct
from collections.abc import Callable
from typing import Any

import pytest
import spec_reference as ref
from hypothesis import event, given
from hypothesis import settings as hsettings
from hypothesis import strategies as st

from pyribbon import ConstructionError, RibbonFilter

HEADER = 64
SEEDS = st.one_of(st.integers(0, 2**64 - 1), st.sampled_from([0, 1, 2**32 - 1, 2**32, 2**63, 2**64 - 1]))
FP_BITS = st.integers(1, 32)
DATA_SEEDS = st.integers(0, 2**32 - 1)
OVERHEADS = st.sampled_from([None, 0.0, 0.0, 0.02, 0.05, 0.3, 1.0])
BOUNDARY_SIZES = [0, 1, 2, 3, 31, 32, 33, 63, 64, 65, 118, 119, 120, 121, 122, 127, 128, 129, 191, 192, 193, 255, 256]
BOUNDARY_SIZES += [257, 1023, 1024, 1025]
SIZES = st.one_of(st.sampled_from(BOUNDARY_SIZES), st.integers(0, 3000))
KINDS = st.sampled_from(["int", "seq", "bytes", "str", "bigint", "mixed"])
# sizes at which zero or tiny overhead makes the banding fail often (the row count is 128 or a multiple of 64)
HARD_SIZES = st.sampled_from([120, 127, 128, 129, 130, 140, 192, 250, 256, 257, 320, 512, 1000])

# int keys on both sides of every encoding boundary: int64 (by value) vs big ints (canonical little-endian bytes)
INT_EDGES = [0, 1, -1, 127, 128, -128, -129, 255, 256, 2**31 - 1, 2**31, -(2**31), 2**53 + 1, 2**63 - 1, 2**63]
INT_EDGES += [-(2**63), -(2**63) - 1, 2**64 - 1, 2**64, -(2**64), 2**71 - 1, 2**71, -(2**71), 2**127, 2**200, -(2**200)]
INT_EDGES += [10**100, -(10**100), 2**1000, -(2**1000) + 1]
TRICKY_STRS = ["", "a", "e", "é", "é", "ẹ́̂", "\U0001f600", "\U0010ffff", "\x00", "a\x00b"]
TRICKY_STRS += ["\U0001f468‍\U0001f469‍\U0001f467", "日本語", "ﬁ", "‮", "퟿", "", "￿"]


def _rand_str(rng: random.Random) -> str:
    out = []
    for _ in range(rng.randrange(0, 12)):
        pool = rng.random()
        if pool < 0.45:
            cp = rng.randrange(0x20, 0x7F)
        elif pool < 0.65:
            cp = rng.randrange(0x300, 0x370)  # combining marks
        elif pool < 0.85:
            cp = rng.randrange(0x80, 0xD800)
        else:
            cp = rng.randrange(0x10000, 0x110000)  # non-BMP
        out.append(chr(cp))
    return "".join(out)


def _rand_int(rng: random.Random) -> int:
    c = rng.random()
    if c < 0.35:
        return rng.randrange(-(2**63), 2**63)
    if c < 0.55:
        return rng.randrange(-1000, 1000)
    if c < 0.8:
        return rng.choice([-1, 1]) * (2 ** rng.randrange(56, 400) + rng.randrange(-2, 3))
    return rng.choice([-1, 1]) * rng.getrandbits(rng.randrange(1, 300))


def _rand_bytes(rng: random.Random) -> bytes:
    return rng.randbytes(rng.randrange(0, 40))


def make_keys(rng: random.Random, n: int, kind: str) -> list[Any]:
    """Return ``n`` random keys of one kind (or a mixture of every key type)."""
    if kind == "seq":
        start = rng.randrange(-(2**62), 2**62)
        return list(range(start, start + n))
    if kind == "int":
        return [rng.randrange(-(2**63), 2**63) for _ in range(n)]
    if kind == "bigint":
        return [_rand_int(rng) for _ in range(n)]
    if kind == "bytes":
        return [_rand_bytes(rng) for _ in range(n)]
    if kind == "str":
        return [rng.choice(TRICKY_STRS) if rng.random() < 0.1 else _rand_str(rng) for _ in range(n)]
    makers: list[Callable[[], Any]] = [
        lambda: _rand_bytes(rng),
        lambda: bytearray(_rand_bytes(rng)),
        lambda: memoryview(_rand_bytes(rng)),
        lambda: _rand_str(rng),
        lambda: _rand_int(rng),
    ]
    return [rng.choice(makers)() for _ in range(n)]


def _try_build(keys: list[Any], **kwargs: Any) -> bytes | None:
    try:
        return RibbonFilter(keys, **kwargs).to_bytes()
    except ConstructionError:
        return None


def _header_field(blob: bytes, fmt: str, offset: int) -> int:
    return int(struct.unpack_from(fmt, blob, offset)[0])


# ---------------------------------------------------------------------------------------------------------------
# no false negatives


def _assert_all_members(keys: list[Any], f: RibbonFilter, fp_bits: int) -> None:
    assert len(f) == len(keys)
    assert f.fp_bits == fp_bits
    assert all(k in f for k in keys)
    assert f.contains_many(keys) == [True] * len(keys)
    if keys:
        assert f.size_in_bytes >= HEADER + 16 * fp_bits  # the 128-row minimum: even one key gets a payload
    else:
        assert f.size_in_bytes == HEADER  # an empty filter is header only


@given(
    keys=st.lists(st.binary(max_size=40), max_size=60),
    fp_bits=FP_BITS,
    seed=SEEDS,
)
def test_no_false_negatives_bytes(keys: list[bytes], fp_bits: int, seed: int) -> None:
    _assert_all_members(keys, RibbonFilter(keys, fp_bits=fp_bits, seed=seed), fp_bits)


@given(
    keys=st.lists(
        st.one_of(
            st.sampled_from(TRICKY_STRS),
            st.text(max_size=12),
            st.text(alphabet=st.characters(min_codepoint=0x10000, exclude_categories=["Cs"]), max_size=5),
            st.text(alphabet=st.characters(categories=["Mn", "Me", "Mc"]), max_size=6),
        ),
        max_size=60,
    ),
    fp_bits=FP_BITS,
    seed=SEEDS,
)
def test_no_false_negatives_str(keys: list[str], fp_bits: int, seed: int) -> None:
    _assert_all_members(keys, RibbonFilter(keys, fp_bits=fp_bits, seed=seed), fp_bits)


def _int_keys() -> st.SearchStrategy[int]:
    near_pow2 = st.integers(8, 300).flatmap(
        lambda k: st.sampled_from([2**k - 1, 2**k, 2**k + 1, -(2**k) + 1, -(2**k), -(2**k) - 1])
    )
    return st.one_of(
        st.sampled_from(INT_EDGES),
        st.integers(-(2**63), 2**63 - 1),
        near_pow2,
        st.integers(-(2**100), 2**100),
        st.integers(-(2**3000), 2**3000),
    )


@given(keys=st.lists(_int_keys(), max_size=60), fp_bits=FP_BITS, seed=SEEDS)
def test_no_false_negatives_int(keys: list[int], fp_bits: int, seed: int) -> None:
    _assert_all_members(keys, RibbonFilter(keys, fp_bits=fp_bits, seed=seed), fp_bits)


@given(
    keys=st.lists(
        st.one_of(
            st.binary(max_size=20),
            st.binary(max_size=20).map(bytearray),
            st.binary(max_size=20).map(memoryview),
            st.text(max_size=8),
            _int_keys(),
        ),
        max_size=60,
    ),
    fp_bits=FP_BITS,
    seed=SEEDS,
)
def test_no_false_negatives_mixed_key_types(keys: list[Any], fp_bits: int, seed: int) -> None:
    _assert_all_members(keys, RibbonFilter(keys, fp_bits=fp_bits, seed=seed), fp_bits)


@given(
    n=SIZES,
    kind=KINDS,
    fp_bits=FP_BITS,
    seed=SEEDS,
    overhead=OVERHEADS,
    data_seed=DATA_SEEDS,
)
@hsettings(max_examples=150)
def test_no_false_negatives_by_set_size(
    n: int, kind: str, fp_bits: int, seed: int, overhead: float | None, data_seed: int
) -> None:
    keys = make_keys(random.Random(data_seed), n, kind)
    _assert_all_members(keys, RibbonFilter(keys, fp_bits=fp_bits, seed=seed, overhead=overhead), fp_bits)


@pytest.mark.parametrize("n", BOUNDARY_SIZES)
@pytest.mark.parametrize("fp_bits", [1, 8, 32])
def test_boundary_sizes_are_always_exercised(n: int, fp_bits: int) -> None:
    keys = make_keys(random.Random(n * 100 + fp_bits), n, "mixed")
    _assert_all_members(keys, RibbonFilter(keys, fp_bits=fp_bits, seed=n), fp_bits)


@pytest.mark.parametrize("n", [10_000, 100_000, 1_000_000])
def test_large_int_sets(n: int) -> None:
    f = RibbonFilter(range(n))
    assert len(f) == n
    assert all(f.contains_many(range(n)))
    assert all(i in f for i in range(n - 1, max(n - 2000, -1), -1))


@pytest.mark.parametrize("kind", ["str", "bytes", "bigint", "mixed"])
def test_large_sets_of_other_key_types(kind: str) -> None:
    keys = make_keys(random.Random(5), 100_000, kind)
    f = RibbonFilter(keys, seed=2**64 - 1)
    assert all(f.contains_many(keys))


@pytest.mark.parametrize("fp_bits", [1, 32])
def test_large_set_extreme_fp_bits(fp_bits: int) -> None:
    f = RibbonFilter(range(50_000), fp_bits=fp_bits, seed=2**64 - 1)
    assert all(f.contains_many(range(50_000)))


def test_int_encoding_edges_are_members_and_stay_distinct() -> None:
    f = RibbonFilter(INT_EDGES, fp_bits=32)
    assert all(e in f for e in INT_EDGES)
    others = {e + d for e in INT_EDGES for d in (-2, -1, 1, 2)} - set(INT_EDGES)
    # fp_bits=32: each of these has a false-positive chance of 2**-32 (about 1e-7 for the whole loop)
    assert not any(o in f for o in others)


# ---------------------------------------------------------------------------------------------------------------
# key identity


@given(
    payloads=st.lists(st.binary(max_size=30), min_size=1, max_size=40),
    fp_bits=FP_BITS,
    seed=SEEDS,
    pad=st.binary(max_size=5),
)
def test_bytes_like_keys_are_interchangeable(payloads: list[bytes], fp_bits: int, seed: int, pad: bytes) -> None:
    f = RibbonFilter(payloads, fp_bits=fp_bits, seed=seed)
    for p in payloads:
        embedded = memoryview(pad + p + pad)[len(pad) : len(pad) + len(p)]
        assert bytearray(p) in f and memoryview(p) in f and memoryview(bytearray(p)) in f and embedded in f
    blob = f.to_bytes()
    for wrap in (bytearray, memoryview):  # building from another bytes-like type gives the very same filter
        assert RibbonFilter([wrap(p) for p in payloads], fp_bits=fp_bits, seed=seed).to_bytes() == blob


def test_memoryview_keys_are_raw_bytes_regardless_of_format() -> None:
    values = array.array("H", [1, 2, 515, 65535])
    f = RibbonFilter([memoryview(values)], fp_bits=32)
    assert values.tobytes() in f
    assert memoryview(values).cast("B") in f
    assert memoryview(bytes(values.tobytes())).cast("B", shape=[2, 4]) in f  # 2-D C-contiguous: still the same 8 bytes


@given(values=st.lists(st.integers(-(2**70), 2**70), min_size=1, max_size=40), seed=SEEDS)
def test_key_types_do_not_alias(values: list[int], seed: int) -> None:
    # fp_bits=32: a wrong answer here has probability 2**-32 per probe (the whole property: about 1e-5)
    f = RibbonFilter(values, fp_bits=32, seed=seed)
    members = set(values)
    for v in values:
        assert v in f
        assert str(v) not in f and str(v).encode() not in f
        assert bytes([abs(v) % 256]) not in f and bytearray(str(v).encode()) not in f
    g = RibbonFilter([str(v) for v in values], fp_bits=32, seed=seed)
    assert all(str(v) in g for v in values) and all(v not in g for v in members)


# ---------------------------------------------------------------------------------------------------------------
# key order and duplicates


def _check_order_independence(
    n: int,
    kind: str,
    fp_bits: int,
    seed: int,
    overhead: float | None,
    max_attempts: int,
    data_seed: int,
    perm_seed: int,
) -> None:
    keys = make_keys(random.Random(data_seed), n, kind)
    shuffled = keys[:]
    random.Random(perm_seed).shuffle(shuffled)
    kwargs = {"fp_bits": fp_bits, "seed": seed, "overhead": overhead, "max_attempts": max_attempts}
    a = _try_build(keys, **kwargs)
    b = _try_build(shuffled, **kwargs)
    event("both built" if a is not None else "both failed")
    assert a == b  # identical bytes, or both construction attempts exhausted: success does not depend on order


@given(
    n=SIZES,
    kind=KINDS,
    fp_bits=FP_BITS,
    seed=SEEDS,
    overhead=OVERHEADS,
    max_attempts=st.integers(1, 4),
    data_seed=DATA_SEEDS,
    perm_seed=DATA_SEEDS,
)
@hsettings(max_examples=150)
def test_serialized_bytes_do_not_depend_on_key_order(
    n: int,
    kind: str,
    fp_bits: int,
    seed: int,
    overhead: float | None,
    max_attempts: int,
    data_seed: int,
    perm_seed: int,
) -> None:
    _check_order_independence(n, kind, fp_bits, seed, overhead, max_attempts, data_seed, perm_seed)


@given(
    n=HARD_SIZES,
    kind=st.sampled_from(["int", "bytes", "mixed"]),
    fp_bits=FP_BITS,
    seed=SEEDS,
    overhead=st.sampled_from([0.0, 0.01]),
    max_attempts=st.integers(1, 3),
    data_seed=DATA_SEEDS,
    perm_seed=DATA_SEEDS,
)
@hsettings(max_examples=150)
def test_key_order_independence_when_construction_often_fails(
    n: int, kind: str, fp_bits: int, seed: int, overhead: float, max_attempts: int, data_seed: int, perm_seed: int
) -> None:
    """Sets sized so that many builds need a retry or fail outright: success itself must not depend on order."""
    _check_order_independence(n, kind, fp_bits, seed, overhead, max_attempts, data_seed, perm_seed)


def test_order_independence_is_not_vacuous() -> None:
    """The experiment behind the property: failures and retried attempts both occur, and shuffling changes nothing."""
    rng = random.Random(11)
    built = failed = retried = 0
    for trial in range(60):
        keys = make_keys(rng, rng.choice([256, 320, 1000]), "int")
        shuffled = rng.sample(keys, len(keys))
        kwargs: dict[str, Any] = {"fp_bits": 4, "seed": trial, "overhead": 0.0, "max_attempts": rng.choice([1, 2, 4])}
        a, b = _try_build(keys, **kwargs), _try_build(shuffled, **kwargs)
        assert a == b
        if a is None:
            failed += 1
        else:
            built += 1
            retried += _header_field(a, "<I", 40) > 0
    assert built >= 5 and failed >= 5 and retried >= 1


@given(
    n=st.integers(1, 400),
    dups=st.integers(1, 60),
    fp_bits=FP_BITS,
    seed=SEEDS,
    overhead=st.sampled_from([0.05, 0.1, 0.5]),
    data_seed=DATA_SEEDS,
)
def test_duplicates_do_not_change_the_solution(
    n: int, dups: int, fp_bits: int, seed: int, overhead: float, data_seed: int
) -> None:
    rng = random.Random(data_seed)
    keys = make_keys(rng, n, "int")
    with_dups = keys + [rng.choice(keys) for _ in range(dups)]
    rng.shuffle(with_dups)
    f = RibbonFilter(with_dups, fp_bits=fp_bits, seed=seed, overhead=overhead)
    assert all(k in f for k in keys) and len(f) == n + dups
    a = RibbonFilter(keys, fp_bits=fp_bits, seed=seed, overhead=overhead).to_bytes()
    b = f.to_bytes()
    same_shape = a[24:32] == b[24:32] and a[40:44] == b[40:44]  # num_rows and attempt
    event("same shape" if same_shape else "different shape")
    if same_shape:  # the equation set is the same, so is the payload; only num_keys and the checksums differ
        assert a[HEADER:] == b[HEADER:]
        assert a[16:24] != b[16:24] and _header_field(b, "<Q", 16) == n + dups


def test_duplicates_leave_payload_unchanged_deterministic() -> None:
    keys = list(range(200))
    a = RibbonFilter(keys, overhead=0.05).to_bytes()
    b = RibbonFilter(keys + keys[:20], overhead=0.05).to_bytes()  # 220 keys still round up to the same 256 rows
    assert a[24:32] == b[24:32] == struct.pack("<Q", 256)
    assert a[HEADER:] == b[HEADER:] and a != b


def test_large_set_is_order_independent() -> None:
    keys = [f"key-{i}" for i in range(20_000)]
    shuffled = random.Random(3).sample(keys, len(keys))
    assert RibbonFilter(keys, seed=9).to_bytes() == RibbonFilter(shuffled, seed=9).to_bytes()


# ---------------------------------------------------------------------------------------------------------------
# contains_many and round trips


@given(
    n=st.integers(0, 300),
    probes_n=st.integers(0, 300),
    kind=KINDS,
    fp_bits=st.integers(1, 3),  # many false positives: both answers occur among the non-members
    seed=SEEDS,
    data_seed=DATA_SEEDS,
)
def test_contains_many_equals_contains(
    n: int, probes_n: int, kind: str, fp_bits: int, seed: int, data_seed: int
) -> None:
    rng = random.Random(data_seed)
    keys = make_keys(rng, n, kind)
    f = RibbonFilter(keys, fp_bits=fp_bits, seed=seed)
    probes = keys[::2] + make_keys(rng, probes_n, "mixed")
    rng.shuffle(probes)
    expected = [k in f for k in probes]
    assert f.contains_many(probes) == expected
    assert f.contains_many(tuple(probes)) == expected
    assert f.contains_many(iter(probes)) == expected
    assert f.contains_many(keys) == [True] * n


@pytest.mark.parametrize("size", [0, 1, 1023, 1024, 1025, 2048, 5000])
def test_contains_many_across_the_gil_release_threshold(size: int) -> None:
    f = RibbonFilter(range(5000), fp_bits=2)
    probes = [i * 7 - 3000 for i in range(size)]  # members and non-members interleaved
    expected = [k in f for k in probes]
    assert f.contains_many(probes) == expected
    assert size < 100 or (any(expected) and not all(expected))


@given(
    n=SIZES,
    kind=KINDS,
    fp_bits=FP_BITS,
    seed=SEEDS,
    overhead=OVERHEADS,
    data_seed=DATA_SEEDS,
)
@hsettings(max_examples=150)
def test_serialization_and_pickle_round_trips(
    n: int, kind: str, fp_bits: int, seed: int, overhead: float | None, data_seed: int
) -> None:
    rng = random.Random(data_seed)
    keys = make_keys(rng, n, kind)
    f = RibbonFilter(keys, fp_bits=fp_bits, seed=seed, overhead=overhead)
    blob = f.to_bytes()
    non_members = make_keys(rng, 60, "mixed")
    probes = keys[:60] + non_members
    expected = [p in f for p in probes]
    clones = [RibbonFilter.from_buffer(blob), RibbonFilter.from_buffer(blob, verify=False)]
    clones += [RibbonFilter.from_buffer(bytearray(blob)), RibbonFilter.from_buffer(memoryview(blob))]
    clones += [pickle.loads(pickle.dumps(f, protocol)) for protocol in range(pickle.HIGHEST_PROTOCOL + 1)]
    clones += [copy.copy(f), copy.deepcopy(f)]
    for g in clones:
        assert g is not f
        assert g.to_bytes() == blob
        assert (len(g), g.fp_bits, g.size_in_bytes, g.bits_per_key) == (len(f), fp_bits, len(blob), f.bits_per_key)
        assert repr(g) == repr(f)
        assert g.contains_many(probes) == expected
        assert [p in g for p in probes] == expected  # members stay members; non-members get the same answer
    assert expected[: len(keys[:60])] == [True] * len(keys[:60])


# ---------------------------------------------------------------------------------------------------------------
# differential: C extension vs the pure-Python reference of the spec


def _check_against_reference(
    n: int, kind: str, fp_bits: int, seed: int, overhead: float | None, max_attempts: int, data_seed: int
) -> None:
    rng = random.Random(data_seed)
    keys = make_keys(rng, n, kind)
    hashes = [ref.hash_key(k, seed) for k in keys]
    try:
        rows, attempt, payload = ref.build(hashes, fp_bits, seed, overhead, max_attempts)
        expected: bytes | None = ref.serialize(n, rows, fp_bits, seed, attempt, payload)
    except ref.ReferenceError as exc:
        assert exc.status == "CONSTRUCT"
        expected = None
    got = _try_build(keys, fp_bits=fp_bits, seed=seed, overhead=overhead, max_attempts=max_attempts)
    event("built" if expected is not None else "construction failed")
    assert got == expected  # byte for byte, or both give up
    if expected is None:
        return
    f = RibbonFilter.from_buffer(expected)
    probes = keys[:6] + make_keys(rng, 10, "mixed")
    for p in probes:
        assert (p in f) == ref.contains(expected, ref.hash_key(p, seed))


@given(
    n=st.one_of(st.sampled_from([0, 1, 63, 64, 65, 120, 121, 127, 128, 129]), st.integers(0, 160)),
    kind=KINDS,
    fp_bits=FP_BITS,
    seed=SEEDS,
    overhead=st.sampled_from([None, 0.0, 0.0, 0.01, 0.03, 0.06, 0.2]),
    max_attempts=st.integers(1, 5),
    data_seed=DATA_SEEDS,
)
@hsettings(max_examples=150)
def test_build_and_query_match_the_reference(
    n: int, kind: str, fp_bits: int, seed: int, overhead: float | None, max_attempts: int, data_seed: int
) -> None:
    _check_against_reference(n, kind, fp_bits, seed, overhead, max_attempts, data_seed)


@given(
    n=HARD_SIZES.filter(lambda n: n <= 330),
    kind=st.sampled_from(["int", "str", "mixed"]),
    fp_bits=st.sampled_from([1, 4, 8, 32]),
    seed=SEEDS,
    overhead=st.sampled_from([0.0, 0.01]),
    max_attempts=st.integers(1, 3),
    data_seed=DATA_SEEDS,
)
@hsettings(max_examples=100)
def test_reference_agrees_when_construction_often_fails(
    n: int, kind: str, fp_bits: int, seed: int, overhead: float, max_attempts: int, data_seed: int
) -> None:
    """Failure (ConstructionError vs the reference's CONSTRUCT) and the attempt that succeeds must agree too."""
    _check_against_reference(n, kind, fp_bits, seed, overhead, max_attempts, data_seed)


def test_reference_comparison_is_not_vacuous() -> None:
    """Both outcomes of the differential test occur: some builds fail (identically), most succeed."""
    outcomes = {"built": 0, "failed": 0, "second attempt or later": 0}
    rng = random.Random(21)
    for i in range(80):
        n = rng.choice([100, 120, 127, 128, 130, 140])
        keys = make_keys(rng, n, "int")
        hashes = [ref.hash_int(k, i) for k in keys]
        attempts = rng.choice([1, 2, 3])
        try:
            rows, attempt, payload = ref.build(hashes, 8, i, 0.0, attempts)
            exp: bytes | None = ref.serialize(n, rows, 8, i, attempt, payload)
            outcomes["built"] += 1
            outcomes["second attempt or later"] += attempt > 0
        except ref.ReferenceError:
            exp = None
            outcomes["failed"] += 1
        assert _try_build(keys, fp_bits=8, seed=i, overhead=0.0, max_attempts=attempts) == exp
    assert all(v >= 3 for v in outcomes.values()), outcomes


@pytest.mark.parametrize(("seed_a", "seed_b"), [(0, 1), (0, 2), (5, 6), (2**63, 2**63 + 1), (2**64 - 2, 2**64 - 1)])
def test_nearby_seeds_give_independent_false_positives(seed_a: int, seed_b: int) -> None:
    """Regression: XORing the seed into dense int keys made seed 1 rebuild almost the filter of seed 0."""
    n = 20_000
    a = RibbonFilter(range(n), fp_bits=4, seed=seed_a)
    b = RibbonFilter(range(n), fp_bits=4, seed=seed_b)
    assert a.to_bytes()[HEADER:] != b.to_bytes()[HEADER:]
    probes = range(n, n + 200_000)  # disjoint from the members
    in_a, in_b = a.contains_many(probes), b.contains_many(probes)
    assert 12_500 - 5 * 108 <= sum(in_a) <= 12_500 + 5 * 108  # each filter alone: 200000 / 16, sd 108
    assert 12_500 - 5 * 108 <= sum(in_b) <= 12_500 + 5 * 108
    both = sum(x and y for x, y in zip(in_a, in_b, strict=True))
    # independent filters share about 200000 / 256 = 781 probes (sd 28); identical ones would share about 12500
    assert 400 <= both <= 1200
