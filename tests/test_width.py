"""Width 128: the ``width`` argument, the format it writes, and how it compares with width 64 (docs/internals.md)."""

from __future__ import annotations

import pickle
import random
from typing import Any

import pytest
import spec_reference as ref

from pyribbon import ConstructionError, FormatError, RibbonFilter, Width

KEYS = [*range(2000), *(f"key-{i}" for i in range(500)), *(b"bytes-%d" % i for i in range(500))]


def test_width_is_an_enum_of_exactly_two_members() -> None:
    assert [(w.name, w.value) for w in Width] == [("W64", 64), ("W128", 128)]
    assert Width.W128 == 128 and isinstance(Width.W64, int)


def test_default_width_is_64() -> None:
    assert RibbonFilter(KEYS).width is Width.W64
    assert RibbonFilter([]).width is Width.W64


def test_repr_names_the_width() -> None:
    narrow, wide = RibbonFilter(range(300)), RibbonFilter(range(300), fp_bits=5, width=Width.W128)
    assert repr(narrow) == f"RibbonFilter(keys=300, fp_bits=8, width=64, size_in_bytes={narrow.size_in_bytes})"
    assert repr(wide) == f"RibbonFilter(keys=300, fp_bits=5, width=128, size_in_bytes={wide.size_in_bytes})"


@pytest.mark.parametrize("width", list(Width))
def test_the_property_returns_the_enum_member(width: Width) -> None:
    f = RibbonFilter(KEYS, width=width)
    assert f.width is width
    assert RibbonFilter.from_buffer(f.to_bytes()).width is width
    assert pickle.loads(pickle.dumps(f)).width is width


def test_the_enum_members_and_their_int_values_build_the_same_filter() -> None:
    assert RibbonFilter(KEYS, width=Width.W128).to_bytes() == RibbonFilter(KEYS, width=128).to_bytes()
    assert RibbonFilter(KEYS, width=Width.W64).to_bytes() == RibbonFilter(KEYS).to_bytes()


@pytest.mark.parametrize("width", [0, 1, 32, 63, 65, 96, 127, 129, 256, -64, True, False])
def test_other_widths_are_refused(width: int) -> None:
    with pytest.raises(ValueError, match="width must be 64 or 128"):
        RibbonFilter(KEYS, width=width)


@pytest.mark.parametrize("width", ["128", 128.0, None])
def test_width_must_be_an_int(width: Any) -> None:
    with pytest.raises(TypeError):
        RibbonFilter(KEYS, width=width)


def test_numpy_integers_are_accepted_as_widths() -> None:
    np = pytest.importorskip("numpy")
    assert RibbonFilter(KEYS, width=np.int64(128)).width is Width.W128
    assert RibbonFilter(KEYS, width=np.uint8(64)).width is Width.W64
    with pytest.raises(ValueError, match="width must be 64 or 128"):
        RibbonFilter(KEYS, width=np.int32(96))


def test_width_is_keyword_only() -> None:
    with pytest.raises(TypeError):
        RibbonFilter(KEYS, 8, 0, None, 32, 128)  # type: ignore[misc]


@pytest.mark.parametrize("fp_bits", [1, 8, 13, 32])
@pytest.mark.parametrize("n", [0, 1, 2, 127, 128, 129, 255, 256, 257, 1000, 20000])
def test_no_false_negatives(n: int, fp_bits: int) -> None:
    keys = [(i * 2654435761) % 2**40 for i in range(n)]
    f = RibbonFilter(keys, fp_bits=fp_bits, width=128)
    assert f.width is Width.W128
    assert all(k in f for k in keys)
    assert f.contains_many(keys) == [True] * n


def test_empty_filter_has_the_width_in_its_header() -> None:
    blob = RibbonFilter([], width=128).to_bytes()
    assert len(blob) == 64
    assert blob[12] == 7
    assert RibbonFilter.from_buffer(blob).width is Width.W128
    assert RibbonFilter.from_buffer(RibbonFilter([]).to_bytes()).width is Width.W64


def test_the_minimum_table_is_twice_the_width() -> None:
    narrow, wide = RibbonFilter([1], fp_bits=8), RibbonFilter([1], fp_bits=8, width=128)
    assert narrow.size_in_bytes == 64 + 128  # 128 rows x 8 bits
    assert wide.size_in_bytes == 64 + 256


@pytest.mark.parametrize("n", [1000, 20000, 200000])
def test_wide_ribbons_need_fewer_bits_per_key(n: int) -> None:
    keys = list(range(n))
    narrow, wide = RibbonFilter(keys), RibbonFilter(keys, width=128)
    assert wide.bits_per_key <= narrow.bits_per_key  # at 1000 keys both round up to the same 64-row block
    # from 20,000 keys up the saving is at least 4%
    if n >= 20000:
        assert wide.bits_per_key < 0.96 * narrow.bits_per_key


def test_round_trip_pickle_and_copy_keep_the_width() -> None:
    f = RibbonFilter(KEYS, fp_bits=12, seed=5, width=128)
    blob = f.to_bytes()
    for g in (
        RibbonFilter.from_buffer(blob),
        RibbonFilter.from_buffer(memoryview(blob), verify=False),
        pickle.loads(pickle.dumps(f)),
    ):
        assert g.width is Width.W128
        assert g.to_bytes() == blob
        assert g.contains_many(KEYS) == [True] * len(KEYS)
    assert RibbonFilter(KEYS, fp_bits=12, seed=5, width=128).to_bytes() == blob  # deterministic


def test_same_keys_give_different_filters_per_width() -> None:
    a, b = RibbonFilter(KEYS, width=64).to_bytes(), RibbonFilter(KEYS, width=128).to_bytes()
    assert a != b
    assert (a[12], b[12]) == (6, 7)


def test_matches_the_reference_byte_for_byte() -> None:
    rng = random.Random(3)
    for n, r in [(1, 1), (50, 8), (300, 5), (1000, 12), (2500, 32)]:
        keys = [rng.getrandbits(63) for _ in range(n)]
        rows, attempt, payload = ref.build([ref.hash_int(k, 7) for k in keys], r, 7, None, 32, 128)
        expected = ref.serialize(n, rows, r, 7, attempt, payload, 128)
        assert RibbonFilter(keys, fp_bits=r, seed=7, width=128).to_bytes() == expected


@pytest.mark.parametrize("r", [1, 4, 8])
def test_false_positive_rate_is_about_two_to_the_minus_r(r: int) -> None:
    """400,000 probes at 6 sigma. The slow statistics tests cover more sizes and fp_bits."""
    n, probes = 30000, 400_000
    f = RibbonFilter(range(n), fp_bits=r, width=128)
    hits = sum(f.contains_many(range(n, n + probes)))
    expected = probes / 2**r
    sigma = (probes * 2**-r * (1 - 2**-r)) ** 0.5
    assert abs(hits - expected) < 6 * sigma, (hits, expected)


@pytest.mark.parametrize("n", [300, 3000])
def test_default_overhead_succeeds_on_the_first_attempt_about_97_percent_of_the_time(n: int) -> None:
    """The table is calibrated for 97% per attempt, so about 9 of 300 single-attempt builds fail."""
    failures = 0
    for trial in range(300):
        try:
            RibbonFilter(range(trial * n, (trial + 1) * n), max_attempts=1, width=128)
        except ConstructionError:
            failures += 1
    assert failures < 30, failures  # 30 is far beyond chance; a table that is too tight would exceed it


def test_failure_is_reported_for_width_128_too() -> None:
    with pytest.raises(ConstructionError):
        RibbonFilter(range(100000), overhead=0.0, max_attempts=1, width=128)
    f = RibbonFilter(range(100000), overhead=0.0, width=128)  # growth from the third attempt makes it succeed
    assert all(k in f for k in range(0, 100000, 97))


def test_a_flipped_width_bit_is_a_checksum_error() -> None:
    blob = bytearray(RibbonFilter(range(300), width=128).to_bytes())
    blob[12] ^= 1
    with pytest.raises(FormatError, match="checksum"):
        RibbonFilter.from_buffer(bytes(blob))


@pytest.mark.parametrize("n", [1, 127, 128, 129, 255, 256, 257, 1000, 12345])
def test_sizing_matches_the_reference(n: int) -> None:
    """Rows come from integer arithmetic on the calibrated table, so the pure-Python reference sizes the same filter."""
    rows, _, _ = ref.build([ref.hash_int(i, 0) for i in range(n)], width=128)
    assert RibbonFilter(range(n), width=128).size_in_bytes == 64 + rows  # r = 8: payload bytes == rows
