"""Behaviour tests for the public API, cross-checked against the pure-Python reference of the spec."""

from __future__ import annotations

import copy
import importlib.metadata
import mmap
import pickle
from pathlib import Path

import pytest
import spec_reference as ref

import pyribbon
from pyribbon import ConstructionError, FormatError, RibbonError, RibbonFilter

INT_KEYS = [0, 1, -1, 42, 2**31, -(2**31), 2**63 - 1, -(2**63), 2**63, -(2**63) - 1, 2**64, 2**64 - 1, -(2**71), 2**200]
STR_KEYS = ["", "a", "alice", "ünïcödé ключ 鍵", "x" * 1000]
BYTES_KEYS = [b"", b"a", b"\x00", b"\xff" * 33, bytes(range(256))]


def test_version_matches_installed_metadata() -> None:
    assert importlib.metadata.version("pyribbon") == pyribbon.__version__


def test_membership_all_key_types() -> None:
    keys: list[object] = [*INT_KEYS, *STR_KEYS, *BYTES_KEYS]
    f = RibbonFilter(keys)  # type: ignore[arg-type]
    assert all(k in f for k in keys)  # type: ignore[operator]
    assert len(f) == len(keys)
    assert f.fp_bits == 8


def test_bytes_like_keys_are_equal_by_content() -> None:
    f = RibbonFilter([b"abc"], fp_bits=32)
    assert bytearray(b"abc") in f
    assert memoryview(b"abc") in f
    assert memoryview(bytearray(b"abc")) in f


def test_key_types_are_distinct() -> None:
    f = RibbonFilter(["a", 5, b"b"], fp_bits=32)
    assert b"a" not in f  # str vs bytes
    assert 97 not in f  # str vs int
    assert "5" not in f and b"5" not in f  # int vs str / bytes
    assert 5 in f and "a" in f and b"b" in f
    assert "b" not in f  # bytes vs str


def test_bool_and_index_objects_are_ints() -> None:
    class Idx:
        def __index__(self) -> int:
            return 7

    f = RibbonFilter([1, 7], fp_bits=32)
    assert True in f
    assert Idx() in f  # type: ignore[comparison-overlap]


@pytest.mark.parametrize("bad", [1.5, None, (1, 2), [1], {"a": 1}, object(), 2j])
def test_unsupported_key_type_raises(bad: object) -> None:
    f = RibbonFilter([1, 2, 3])
    with pytest.raises(TypeError, match="unsupported key type"):
        bad in f  # type: ignore[operator]  # noqa: B015
    with pytest.raises(TypeError, match="unsupported key type"):
        RibbonFilter([1, bad])  # type: ignore[list-item]
    with pytest.raises(TypeError, match="unsupported key type"):
        f.contains_many([1, bad])  # type: ignore[list-item]


@pytest.mark.parametrize("single", ["hello", b"hello", bytearray(b"hi"), memoryview(b"hi")])
def test_single_key_instead_of_iterable_raises(single: object) -> None:
    with pytest.raises(TypeError, match="iterable of keys"):
        RibbonFilter(single)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="iterable of keys"):
        RibbonFilter([1]).contains_many(single)  # type: ignore[arg-type]


def test_lone_surrogate_raises_unicode_error() -> None:
    with pytest.raises(UnicodeEncodeError):
        RibbonFilter(["\ud800"])


def test_non_contiguous_memoryview_raises() -> None:
    view = memoryview(bytes(range(20)))[::2]
    with pytest.raises(BufferError):
        RibbonFilter([view])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"fp_bits": 0},
        {"fp_bits": 33},
        {"fp_bits": -1},
        {"seed": -1},
        {"seed": 2**64},
        {"max_attempts": 0},
        {"max_attempts": 256},
        {"overhead": -0.1},
        {"overhead": 4.1},
        {"overhead": float("nan")},
    ],
)
def test_invalid_arguments_raise_value_error(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        RibbonFilter([1, 2, 3], **kwargs)  # type: ignore[arg-type]


def test_wrong_argument_types() -> None:
    with pytest.raises(TypeError):
        RibbonFilter([1], fp_bits="8")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RibbonFilter([1], seed="x")  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RibbonFilter([1], 8)  # type: ignore[misc]  # options are keyword-only
    with pytest.raises(TypeError):
        RibbonFilter(5)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        RibbonFilter()  # type: ignore[call-arg]


def test_empty_filter() -> None:
    f = RibbonFilter([])
    assert len(f) == 0
    assert 1 not in f and "x" not in f and b"" not in f
    assert f.contains_many([1, 2]) == [False, False]
    assert f.contains_many([]) == []
    assert f.size_in_bytes == 64
    assert f.bits_per_key == 0.0
    g = RibbonFilter.from_buffer(f.to_bytes())
    assert len(g) == 0 and 1 not in g


@pytest.mark.parametrize("n", [1, 2, 63, 64, 65, 127, 128, 129, 1000])
def test_small_sizes_have_no_false_negatives(n: int) -> None:
    f = RibbonFilter(range(n))
    assert all(i in f for i in range(n))
    assert len(f) == n
    assert f.size_in_bytes >= 64 + 128  # minimum of 128 rows x 8 bits + header


def test_duplicates_are_harmless_and_counted() -> None:
    f = RibbonFilter([1, 2, 3] * 100)
    assert all(k in f for k in (1, 2, 3))
    assert len(f) == 300


def test_generator_and_single_pass_iterables() -> None:
    f = RibbonFilter((i * 3 for i in range(5000)), fp_bits=32)
    assert all(i * 3 in f for i in range(5000))
    assert len(f) == 5000
    assert f.contains_many(iter([0, 3, 4])) == [True, True, False]
    assert f.contains_many(i for i in (4, 3)) == [False, True]


def test_contains_many_matches_contains() -> None:
    f = RibbonFilter(range(5000), fp_bits=4)  # high FPR: plenty of True answers among the negatives
    probe = list(range(-3000, 8000))  # spans both the small-batch and the GIL-released path
    expected = [k in f for k in probe]
    assert f.contains_many(probe) == expected
    assert f.contains_many(probe[:10]) == expected[:10]
    assert any(expected[:3000]) and not all(expected[:3000])  # fp_bits=4: some negatives hit, most do not
    assert all(f.contains_many(range(5000)))


def test_construction_failure_raises_and_never_returns_a_filter() -> None:
    with pytest.raises(ConstructionError) as info:
        RibbonFilter(range(200_000), overhead=0.0, max_attempts=1)
    assert isinstance(info.value, RibbonError)
    assert "overhead" in str(info.value)
    # the same set builds when the retry budget is available: growth kicks in from the third attempt
    f = RibbonFilter(range(200_000), overhead=0.0)
    assert all(i in f for i in range(0, 200_000, 997))


def test_seed_changes_the_filter_and_is_stored() -> None:
    a = RibbonFilter(range(500), seed=0).to_bytes()
    b = RibbonFilter(range(500), seed=12345).to_bytes()
    assert a != b
    g = RibbonFilter.from_buffer(b)
    assert all(i in g for i in range(500))  # the stored seed is applied automatically


def test_to_bytes_roundtrip_and_properties() -> None:
    f = RibbonFilter(range(3000), fp_bits=11, seed=9)
    blob = f.to_bytes()
    assert isinstance(blob, bytes) and len(blob) == f.size_in_bytes
    assert f.bits_per_key == pytest.approx(8 * len(blob) / 3000)
    g = RibbonFilter.from_buffer(blob)
    assert (len(g), g.fp_bits, g.size_in_bytes, g.to_bytes()) == (len(f), 11, len(blob), blob)
    assert all(i in g for i in range(3000))
    assert repr(f) == f"RibbonFilter(keys=3000, fp_bits=11, size_in_bytes={len(blob)})"


def test_matches_pure_python_reference_byte_for_byte() -> None:
    keys: list[object] = [*INT_KEYS, *STR_KEYS, *BYTES_KEYS, bytearray(b"abc"), *range(300)]
    for r, seed, overhead in [(8, 0, 0.07), (1, 3, 0.1), (20, 2**64 - 1, 0.06), (32, 5, 0.12)]:
        hashes = [ref.hash_key(k, seed) for k in keys]
        rows, attempt, payload = ref.build(hashes, r, seed, overhead)
        expected = ref.serialize(len(keys), rows, r, seed, attempt, payload)
        f = RibbonFilter(keys, fp_bits=r, seed=seed, overhead=overhead)  # type: ignore[arg-type]
        assert f.to_bytes() == expected


def test_default_sizing_agrees_with_reference() -> None:
    for n in (1, 100, 1000, 20000):
        hashes = [ref.hash_int(i, 0) for i in range(n)]
        rows, _, _ = ref.build(hashes)
        f = RibbonFilter(range(n))
        assert abs(f.size_in_bytes - (64 + rows)) <= 8 * 8 * 2  # rows * 8 bits / 8 = rows bytes; allow float drift


def test_queries_agree_with_reference_query() -> None:
    f = RibbonFilter(range(400), fp_bits=3)  # r = 3: false positives are common, so both answers occur
    blob = f.to_bytes()
    answers = []
    for i in range(-200, 800):
        got = i in f
        assert got == ref.contains(blob, ref.hash_int(i, 0))
        answers.append(got)
    assert True in answers[200:600] and False in answers[:200] and True in answers[:200]


@pytest.mark.parametrize("wrap", [bytes, bytearray, memoryview])
def test_from_buffer_accepts_buffer_types(wrap: type) -> None:
    f = RibbonFilter(range(100))
    g = RibbonFilter.from_buffer(wrap(f.to_bytes()))
    assert all(i in g for i in range(100))


def test_from_buffer_is_zero_copy_and_holds_the_buffer() -> None:
    f = RibbonFilter(range(1000))
    data = bytearray(f.to_bytes())
    g = RibbonFilter.from_buffer(data)
    with pytest.raises(BufferError):
        data.append(0)  # the filter holds a buffer export: no copy was made, and the source cannot move
    del g
    data.append(0)  # released on deallocation
    # offsets: a filter embedded in a larger buffer is loaded by slicing
    blob = f.to_bytes()
    padded = memoryview(b"\x01\x02\x03" + blob + b"\xff\xfe")[3 : 3 + len(blob)]
    assert all(i in RibbonFilter.from_buffer(padded) for i in range(1000))


def test_from_buffer_mmap(tmp_path: Path) -> None:
    f = RibbonFilter(range(2000), fp_bits=12)
    path = tmp_path / "filter.bin"
    path.write_bytes(f.to_bytes())
    with path.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        g = RibbonFilter.from_buffer(mm, verify=False)
        assert all(i in g for i in range(2000))
        with pytest.raises(BufferError):
            mm.close()  # still exported
        del g
    # leaving the with-block closed the map without a BufferError: the filter had released its export


def test_format_errors() -> None:
    blob = RibbonFilter(range(300)).to_bytes()
    assert issubclass(FormatError, ValueError) and issubclass(FormatError, RibbonError)
    for bad in (b"", blob[:10], blob[:-1], blob + b"\x00", b"NOTRIBBN" + blob[8:], bytes(len(blob))):
        with pytest.raises(FormatError):
            RibbonFilter.from_buffer(bad)
    flipped = bytearray(blob)
    flipped[-1] ^= 1
    with pytest.raises(FormatError, match="checksum"):
        RibbonFilter.from_buffer(bytes(flipped))
    RibbonFilter.from_buffer(bytes(flipped), verify=False)  # header is fine; only answers could differ
    with pytest.raises(TypeError):
        RibbonFilter.from_buffer("text")  # type: ignore[arg-type]
    with pytest.raises(BufferError):
        RibbonFilter.from_buffer(memoryview(blob)[::2])


def test_pickle_and_copy() -> None:
    f = RibbonFilter(["a", "b", 3], fp_bits=16, seed=77)
    for clone in (pickle.loads(pickle.dumps(f)), copy.copy(f), copy.deepcopy(f)):
        assert clone is not f
        assert clone.to_bytes() == f.to_bytes()
        assert "a" in clone and 3 in clone


def test_type_is_final_and_immutable() -> None:
    with pytest.raises(TypeError):
        type("Sub", (RibbonFilter,), {})
    with pytest.raises(TypeError):
        RibbonFilter.extra = 1  # type: ignore[attr-defined]
    f = RibbonFilter([1])
    for attr in ("fp_bits", "size_in_bytes", "bits_per_key"):
        with pytest.raises(AttributeError):
            setattr(f, attr, 1)
    with pytest.raises(AttributeError):
        f.new_attribute = 1  # type: ignore[attr-defined]


def test_module_surface() -> None:
    assert sorted(pyribbon.__all__) == [
        "ConstructionError",
        "FormatError",
        "Key",
        "RibbonError",
        "RibbonFilter",
        "__version__",
    ]
    assert RibbonFilter.__module__ == "pyribbon"
    assert FormatError.__module__ == "pyribbon" and ConstructionError.__module__ == "pyribbon"
