"""Loading serialized filters is a trust boundary: truncation, bit flips, hostile headers, differential fuzzing.

Every rejection must be a ``FormatError`` (never a crash, hang or over-read), and the decision to accept or reject
must be exactly the one made by ``spec_reference.parse``, the independent pure-Python implementation of the loader
rules. When both reject, the C error message must name the same status as the reference.
"""

from __future__ import annotations

import array
import mmap
import random
import struct
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import spec_reference as ref
from hypothesis import given
from hypothesis import settings as hsettings
from hypothesis import strategies as st

from pyribbon import FormatError, RibbonFilter

HEADER = 64
STATUS_TEXT = {
    "TRUNCATED": "buffer too short",
    "MAGIC": "bad magic",
    "VERSION": "unsupported format version",
    "FORMAT": "inconsistent or unsupported header",
    "CHECKSUM": "checksum mismatch",
}
# header layout (DESIGN.md section 5): name -> (offset, size)
FIELDS = {
    "magic": (0, 8),
    "version": (8, 2),
    "header_size": (10, 2),
    "width_log2": (12, 1),
    "fp_bits": (13, 1),
    "hash_id": (14, 1),
    "flags": (15, 1),
    "num_keys": (16, 8),
    "num_rows": (24, 8),
    "seed": (32, 8),
    "attempt": (40, 4),
    "reserved": (44, 4),
    "payload_xxh3": (48, 8),
    "header_xxh3": (56, 8),
}
_SPECS: dict[str, tuple[list[Any], dict[str, Any]]] = {
    "empty": ([], {}),
    "one_r1": ([1], {"fp_bits": 1}),
    "n50_r4": (list(range(50)), {"fp_bits": 4, "seed": 3}),
    "n400_r8": (list(range(400)), {}),
    "n300_r32": (list(range(300)), {"fp_bits": 32, "seed": 2**64 - 1}),
    "n1000_r16": ([f"k{i}" for i in range(1000)], {"fp_bits": 16, "seed": 77}),
}
MEMBERS = {name: keys for name, (keys, _) in _SPECS.items()}
BLOBS: dict[str, bytes] = {name: RibbonFilter(keys, **kw).to_bytes() for name, (keys, kw) in _SPECS.items()}
PROBES: list[Any] = [*range(-60, 60), *(b"probe-%d" % i for i in range(40)), *(f"probe-{i}" for i in range(40))]
assert len(PROBES) == 200


def with_fields(blob: bytes, *, fix_header: bool = True, fix_payload: bool = False, **fields: int | bytes) -> bytes:
    """Overwrite header fields by name, then optionally repair the payload and header checksums."""
    b = bytearray(blob)
    for name, value in fields.items():
        offset, size = FIELDS[name]
        b[offset : offset + size] = value if isinstance(value, bytes) else int(value).to_bytes(size, "little")
    if fix_payload:
        struct.pack_into("<Q", b, 48, ref.xxh3(bytes(b[HEADER:])))
    if fix_header:
        struct.pack_into("<Q", b, 56, ref.xxh3(bytes(b[:56])))
    return bytes(b)


def hand_built(
    rows: int, r: int, num_keys: int = 1, seed: int = 5, attempt: int = 0, payload: bytes | None = None
) -> bytes:
    """A syntactically valid filter with an arbitrary payload (its answers mean nothing; its header is valid)."""
    if payload is None:
        payload = random.Random(rows * 33 + r).randbytes(rows // 64 * r * 8)
    return ref.serialize(num_keys, rows, r, seed, attempt, payload)


def c_outcome(buf: Any, verify: bool = True) -> tuple[str | None, RibbonFilter | None]:
    """Load with the C extension: ``(status name, None)`` on rejection, ``(None, filter)`` on success."""
    try:
        return None, RibbonFilter.from_buffer(buf, verify=verify)
    except FormatError as exc:
        text = str(exc)
        names = [name for name, fragment in STATUS_TEXT.items() if fragment in text]
        assert len(names) == 1, f"unrecognised or ambiguous FormatError message: {text!r}"
        return names[0], None


def ref_outcome(buf: bytes, verify: bool = True) -> tuple[str | None, dict[str, int] | None]:
    try:
        return None, ref.parse(buf, verify)
    except ref.ReferenceError as exc:
        return exc.status, None


def exercise(f: RibbonFilter, buf: bytes, meta: dict[str, int], ref_probes: int = 2) -> None:
    """An accepted filter must be self-consistent and survive queries, whatever bytes its payload holds."""
    assert f.fp_bits == meta["fp_bits"]
    assert f.size_in_bytes == len(buf) and f.to_bytes() == buf
    if meta["num_keys"] <= 2**63 - 1:
        assert len(f) == meta["num_keys"]
    else:
        with pytest.raises(OverflowError):
            len(f)
    answers = [p in f for p in PROBES]
    assert f.contains_many(PROBES) == answers
    if meta["num_rows"] == 0:
        assert not any(answers)
    for p in PROBES[:: max(1, len(PROBES) // ref_probes)]:
        assert (p in f) == ref.contains(buf, ref.hash_key(p, meta["seed"]))


def check_agreement(buf: bytes, verify: bool = True, ref_probes: int = 2) -> str | None:
    """Assert the C loader and the reference loader take the same decision; return the shared status (None = accepted)."""
    c_status, f = c_outcome(buf, verify)
    r_status, meta = ref_outcome(buf, verify)
    assert c_status == r_status, f"C says {c_status}, reference says {r_status}"
    if f is not None:
        assert meta is not None
        exercise(f, buf, meta, ref_probes)
    return c_status


# ---------------------------------------------------------------------------------------------------------------
# (a) truncation, extension


@pytest.mark.parametrize("name", sorted(BLOBS))
@pytest.mark.parametrize("verify", [True, False])
def test_every_truncation_is_rejected(name: str, verify: bool) -> None:
    blob = BLOBS[name]
    for length in range(len(blob)):
        status, f = c_outcome(blob[:length], verify)
        assert (status, f) == ("TRUNCATED", None), f"length {length}"
    assert c_outcome(blob, verify)[0] is None  # the untruncated blob is fine, so the loop above is not vacuous


@pytest.mark.parametrize("name", sorted(BLOBS))
@pytest.mark.parametrize("verify", [True, False])
def test_trailing_bytes_are_rejected(name: str, verify: bool) -> None:
    blob = BLOBS[name]
    for extra in (1, 2, 7, 8, 63, 64, 65, 1000):
        for tail in (b"\x00", b"\xff", b"\xa5"):
            assert c_outcome(blob + tail * extra, verify) == ("FORMAT", None)


@pytest.mark.parametrize("name", sorted(BLOBS))
def test_every_truncation_agrees_with_the_reference(name: str) -> None:
    blob = BLOBS[name]
    for length in range(0, len(blob) + 1, 1 if len(blob) < 600 else 7):
        assert check_agreement(blob[:length], ref_probes=1) == (None if length == len(blob) else "TRUNCATED")


# ---------------------------------------------------------------------------------------------------------------
# (b) header bit flips


def _flip(blob: bytes, bit: int) -> bytes:
    b = bytearray(blob)
    b[bit // 8] ^= 1 << (bit % 8)
    return bytes(b)


def _expected_header_flip_status(bit: int) -> str:
    """The loader checks magic, then version, then header_size, then the checksum, before any other field."""
    if bit < 64:
        return "MAGIC"
    if bit < 80:
        return "VERSION"
    if bit < 96:
        return "FORMAT"
    return "CHECKSUM"  # every other header bit is covered by header_xxh3 (or is that checksum itself)


@pytest.mark.parametrize("name", sorted(BLOBS))
@pytest.mark.parametrize("verify", [True, False])
def test_every_single_bit_flip_in_the_header_is_rejected(name: str, verify: bool) -> None:
    blob = BLOBS[name]
    for bit in range(HEADER * 8):
        flipped = _flip(blob, bit)
        assert flipped != blob
        assert c_outcome(flipped, verify)[0] == _expected_header_flip_status(bit), f"bit {bit}"
        assert ref_outcome(flipped, verify)[0] == _expected_header_flip_status(bit), f"bit {bit}"


# ---------------------------------------------------------------------------------------------------------------
# (c) payload bit flips


@pytest.mark.parametrize("name", [n for n in sorted(BLOBS) if len(BLOBS[n]) > HEADER])
def test_payload_bit_flips_fail_verification_but_stay_memory_safe_without_it(name: str) -> None:
    blob = BLOBS[name]
    rng = random.Random(1)
    every = range(HEADER * 8, len(blob) * 8)
    # every bit of a small payload; for the larger ones the first and last 64 bits plus a random sample
    bits = list(every) if len(every) <= 4096 else sorted({*every[:64], *every[-64:], *rng.sample(every, 2500)})
    sample = set(rng.sample(bits, min(len(bits), 25)))
    changed = 0
    probes = [*MEMBERS[name], *PROBES]
    baseline = [True] * len(MEMBERS[name]) + [p in RibbonFilter.from_buffer(blob) for p in PROBES]
    for bit in bits:
        flipped = _flip(blob, bit)
        assert c_outcome(flipped, True) == ("CHECKSUM", None)
        status, f = c_outcome(flipped, False)  # header intact, so it loads and every query must run
        assert status is None and f is not None and f.to_bytes() == flipped
        answers = f.contains_many(probes)
        assert answers == [p in f for p in probes]
        changed += answers != baseline
        if bit in sample:  # a corrupted payload is still read exactly as the spec says
            assert check_agreement(flipped, verify=False, ref_probes=25) is None
    assert changed > len(bits) // 20  # corruption does change answers (otherwise the loop proves nothing)


def test_payload_flips_on_a_member_set_can_only_hurt_members_not_crash() -> None:
    blob = RibbonFilter(range(400)).to_bytes()
    lost = 0
    for bit in range(HEADER * 8, len(blob) * 8, 7):
        f = RibbonFilter.from_buffer(_flip(blob, bit), verify=False)
        lost += not all(f.contains_many(range(400)))
    assert lost > 0  # no checksum, no protection: corruption does produce false negatives, as documented


# ---------------------------------------------------------------------------------------------------------------
# (d) hostile headers with a repaired header checksum

_BASE = hand_built(256, 8, num_keys=100)  # a valid filter: 256 rows x 8 bits = 256 payload bytes
_FIELD_CASES: list[tuple[str, dict[str, int | bytes], str]] = [
    ("rows 2**40 on a tiny buffer", {"num_rows": 2**40}, "TRUNCATED"),
    ("rows 2**40-64", {"num_rows": 2**40 - 64}, "TRUNCATED"),
    ("rows 2**32", {"num_rows": 2**32}, "TRUNCATED"),
    ("rows 2**33", {"num_rows": 2**33}, "TRUNCATED"),
    ("rows 2**40+64", {"num_rows": 2**40 + 64}, "FORMAT"),
    ("rows 2**40+1", {"num_rows": 2**40 + 1}, "FORMAT"),
    ("rows 2**41", {"num_rows": 2**41}, "FORMAT"),
    ("rows 2**63", {"num_rows": 2**63}, "FORMAT"),
    ("rows 2**63+64", {"num_rows": 2**63 + 64}, "FORMAT"),
    ("rows 2**64-64", {"num_rows": 2**64 - 64}, "FORMAT"),
    ("rows 2**64-128", {"num_rows": 2**64 - 128}, "FORMAT"),
    ("rows 2**64-1", {"num_rows": 2**64 - 1}, "FORMAT"),
    *(
        (f"rows {rows} not a multiple of 64", {"num_rows": rows}, "FORMAT")
        for rows in (1, 63, 65, 127, 129, 191, 255, 257)
    ),
    ("rows 64 (below 128)", {"num_rows": 64}, "FORMAT"),
    ("rows 128 leaves trailing bytes", {"num_rows": 128}, "FORMAT"),
    ("rows 320 needs more payload", {"num_rows": 320}, "TRUNCATED"),
    ("rows 0 with num_keys != 0", {"num_rows": 0}, "FORMAT"),
    ("rows 0, no keys, payload still attached", {"num_rows": 0, "num_keys": 0}, "FORMAT"),
    *((f"fp_bits {r}", {"fp_bits": r}, "FORMAT") for r in (0, 33, 64, 128, 255)),
    ("fp_bits 7 leaves trailing bytes", {"fp_bits": 7}, "FORMAT"),
    ("fp_bits 9 needs more payload", {"fp_bits": 9}, "TRUNCATED"),
    ("fp_bits 32, rows 2**40", {"fp_bits": 32, "num_rows": 2**40}, "TRUNCATED"),
    *((f"width_log2 {w}", {"width_log2": w}, "FORMAT") for w in (0, 5, 7, 8, 255)),
    *((f"hash_id {h}", {"hash_id": h}, "FORMAT") for h in (0, 2, 255)),
    *((f"flags {fl:#x}", {"flags": fl}, "FORMAT") for fl in (1, 2, 0x80, 255)),
    *((f"reserved {rv:#x}", {"reserved": rv}, "FORMAT") for rv in (1, 0x100, 2**31, 2**32 - 1)),
    *((f"header_size {hs}", {"header_size": hs}, "FORMAT") for hs in (0, 1, 63, 65, 128, 0xFFFF)),
    *((f"version {v}", {"version": v}, "VERSION") for v in (0, 2, 255, 256, 0xFFFF)),
    *(
        (f"magic {m!r}", {"magic": m}, "MAGIC")
        for m in (b"PYRIBBOn", b"\x00" * 8, b"pyribbon", b"XYRIBBON", b"PYRIBBOM")
    ),
    ("bad version beats bad header_size", {"version": 9, "header_size": 9}, "VERSION"),
    ("bad magic beats bad version", {"magic": b"NOTMAGIC", "version": 9}, "MAGIC"),
    ("bad fp_bits and bad rows", {"fp_bits": 0, "num_rows": 3}, "FORMAT"),
]


@pytest.mark.parametrize("verify", [True, False])
@pytest.mark.parametrize(("fields", "status"), [(f, s) for _, f, s in _FIELD_CASES], ids=[c[0] for c in _FIELD_CASES])
def test_hostile_header_is_rejected_with_the_right_status(
    fields: dict[str, int | bytes], status: str, verify: bool
) -> None:
    hostile = with_fields(_BASE, **fields)
    assert c_outcome(hostile, verify) == (status, None)
    assert check_agreement(hostile, verify) == status


@pytest.mark.parametrize("field", [f for f in FIELDS if f not in ("magic", "header_xxh3")])  # magic is checked first
def test_changing_any_field_without_repairing_the_checksum_is_a_checksum_error(field: str) -> None:
    offset, size = FIELDS[field]
    bad = bytearray(_BASE)
    bad[offset] ^= 0x10
    status = {"version": "VERSION", "header_size": "FORMAT"}.get(field, "CHECKSUM")
    for verify in (True, False):
        assert c_outcome(bytes(bad), verify)[0] == status
        assert check_agreement(bytes(bad), verify) == status


def test_wrong_payload_checksum_is_caught_only_when_verifying() -> None:
    bad = with_fields(_BASE, payload_xxh3=0)
    assert c_outcome(bad, True) == ("CHECKSUM", None)
    assert check_agreement(bad, verify=True) == "CHECKSUM"
    assert check_agreement(bad, verify=False) is None
    assert c_outcome(with_fields(_BASE, payload_xxh3=0, fix_payload=True))[0] is None  # repairing it makes it valid


def test_bad_rows_beat_a_bad_payload_checksum() -> None:
    assert check_agreement(with_fields(_BASE, num_rows=3, payload_xxh3=1), verify=True) == "FORMAT"


_VALID_CASES: list[tuple[str, bytes]] = [
    ("untouched", _BASE),
    *((f"num_keys {v}", with_fields(_BASE, num_keys=v)) for v in (0, 1, 2**32, 2**63 - 1, 2**63, 2**64 - 1)),
    *((f"seed {v}", with_fields(_BASE, seed=v)) for v in (0, 1, 2**63, 2**64 - 1)),
    *((f"attempt {v}", with_fields(_BASE, attempt=v)) for v in (1, 31, 255, 2**31, 2**32 - 1)),
    ("128 rows, 32 bits", hand_built(128, 32)),
    ("192 rows, 1 bit", hand_built(192, 1)),
    ("2**17 rows, 5 bits", hand_built(2**17, 5)),
    ("2**20 rows, 1 bit", hand_built(2**20, 1)),
    ("empty filter", hand_built(0, 8, num_keys=0)),
    ("empty filter, odd seed and attempt", hand_built(0, 32, num_keys=0, seed=2**64 - 1, attempt=2**32 - 1)),
    ("rows set but num_keys 0 is informational only", with_fields(_BASE, num_keys=0)),
]


@pytest.mark.parametrize("verify", [True, False])
@pytest.mark.parametrize("blob", [b for _, b in _VALID_CASES], ids=[n for n, _ in _VALID_CASES])
def test_valid_hand_built_headers_are_accepted_and_queryable(blob: bytes, verify: bool) -> None:
    assert (
        check_agreement(blob, verify, ref_probes=6) is None
    )  # also proves the hostile cases are one field away from valid


@pytest.mark.parametrize("r", [1, 8, 32])
def test_a_single_block_filter_is_rejected_even_with_a_consistent_payload(r: int) -> None:
    """rows=64 has the right payload length for its header, so only the 'at least two blocks' rule can reject it."""
    rows = 64
    blob = ref.serialize(10, rows, r, 5, 0, bytes(rows // 64 * r * 8))
    assert len(blob) == HEADER + rows // 64 * r * 8
    for verify in (True, False):
        assert c_outcome(blob, verify) == ("FORMAT", None)
        assert check_agreement(blob, verify) == "FORMAT"


def test_empty_filter_with_payload_or_keys_is_rejected() -> None:
    assert c_outcome(hand_built(0, 8, num_keys=0) + b"\x00")[0] == "FORMAT"
    assert c_outcome(with_fields(hand_built(0, 8, num_keys=0), num_keys=1))[0] == "FORMAT"


def test_huge_row_count_on_a_tiny_buffer_raises_immediately() -> None:
    for r in (1, 8, 32):
        hostile = with_fields(hand_built(128, r), num_rows=2**40)
        assert len(hostile) < 1000
        assert c_outcome(hostile, False) == ("TRUNCATED", None)
        assert c_outcome(hostile, True) == ("TRUNCATED", None)  # and no attempt to checksum 2**42 bytes


# ---------------------------------------------------------------------------------------------------------------
# (e) differential fuzzing against the reference loader

_LIKELY = [0, 1, 2, 3, 6, 7, 8, 31, 32, 33, 63, 64, 65, 127, 128, 129, 191, 192, 255, 256, 257, 320, 384, 512, 1 << 16]
_LIKELY += [1 << 20, (1 << 32) - 64, 1 << 32, (1 << 40) - 64, 1 << 40, (1 << 40) + 64, (1 << 63) - 64, 1 << 63]


def interesting_value(rng: random.Random, size: int, current: int) -> int:
    top = (1 << (8 * size)) - 1
    pool = [*_LIKELY, top, top - 1, top - 63, top - 64, 1 << (8 * size - 1), (1 << (8 * size - 1)) - 1]
    pool += [current + 1, current - 1, current * 2, current // 2, current ^ 1, current ^ 64, current + 64]
    return rng.choice(pool) & top


def mutate(rng: random.Random, blob: bytes) -> bytes:
    """Bit flips, byte sets, truncation, extension, header-field overwrites, then optional checksum/length repairs."""
    b = bytearray(blob)
    for _ in range(rng.choice([1, 1, 1, 2, 3])):
        op = rng.randrange(8)
        if op == 0 and b:
            for _ in range(rng.choice([1, 1, 2, 3])):
                b[rng.randrange(len(b))] ^= 1 << rng.randrange(8)
        elif op == 1 and b:
            b[rng.randrange(len(b))] = rng.choice([0, 0xFF, 0x80, 0x7F, 1, rng.randrange(256)])
        elif op == 2:
            n = len(b)
            del b[
                min(
                    n, rng.choice([0, 1, 7, 8, 55, 56, 63, 64, 65, max(n - 1, 0), max(n - 8, 0), rng.randrange(n + 1)])
                ) :
            ]
        elif op == 3:
            count = rng.choice([1, 2, 8, 63, 64, rng.randrange(1, 200)])
            b += bytes(count) if rng.random() < 0.5 else rng.getrandbits(8 * count).to_bytes(count, "little")
        elif op == 7 and len(b) > HEADER:
            n = len(b) - HEADER
            b[HEADER:] = rng.getrandbits(8 * n).to_bytes(n, "little")
        elif len(b) >= HEADER:
            offset, size = FIELDS[rng.choice(list(FIELDS))]
            current = int.from_bytes(b[offset : offset + size], "little")
            b[offset : offset + size] = interesting_value(rng, size, current).to_bytes(size, "little")
    if len(b) >= HEADER:
        rows, r = struct.unpack_from("<Q", b, 24)[0], b[13]
        if rng.random() < 0.35 and rows % 64 == 0 and rows <= 1024 and 1 <= r <= 32:
            want = rows // 64 * r * 8  # make the payload as long as the (possibly mutated) header demands
            payload = bytes(b[HEADER : HEADER + want])
            payload += rng.getrandbits(8 * (want - len(payload))).to_bytes(want - len(payload), "little")
            b[HEADER:] = payload
        if rng.random() < 0.3:
            struct.pack_into("<Q", b, 48, ref.xxh3(bytes(b[HEADER:])))
        if rng.random() < 0.5:
            struct.pack_into("<Q", b, 56, ref.xxh3(bytes(b[:56])))
    return bytes(b)


def run_differential_fuzz(iterations: int, seed: int) -> Counter[str]:
    rng = random.Random(seed)
    names = sorted(BLOBS)
    outcomes: Counter[str] = Counter()
    for _ in range(iterations):
        base = BLOBS[rng.choice(names)]
        blob = mutate(rng, base)
        status = check_agreement(blob, True, ref_probes=2 if rng.random() < 0.9 else 8)
        outcomes[status or ("ACCEPTED" if blob == base else "ACCEPTED_MUTATED")] += 1
        check_agreement(blob, False, ref_probes=1)  # without payload verification the decision may differ: compare too
    return outcomes


def _assert_fuzz_coverage(outcomes: Counter[str], iterations: int) -> None:
    for status in STATUS_TEXT:  # every rejection class was exercised, and mutated blobs were accepted too
        assert outcomes[status] >= iterations // 1000, (status, outcomes)
    assert outcomes["ACCEPTED_MUTATED"] >= iterations // 100, outcomes


def test_differential_fuzz_against_the_reference_loader() -> None:
    iterations = 120_000
    outcomes = run_differential_fuzz(iterations, seed=20261112)
    _assert_fuzz_coverage(outcomes, iterations)


@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_differential_fuzz_long(seed: int) -> None:
    iterations = 400_000
    _assert_fuzz_coverage(run_differential_fuzz(iterations, seed), iterations)


@given(rng=st.randoms(use_true_random=False), name=st.sampled_from(sorted(BLOBS)))
@hsettings(max_examples=1500)
def test_differential_fuzz_hypothesis(rng: random.Random, name: str) -> None:
    blob = mutate(rng, BLOBS[name])
    for verify in (True, False):
        check_agreement(blob, verify, ref_probes=1)


@given(data=st.binary(max_size=300))
def test_arbitrary_bytes_are_rejected_like_the_reference(data: bytes) -> None:
    assert check_agreement(data) is not None  # random bytes never carry the magic: always rejected


@given(
    rows=st.integers(0, 2**64 - 1) | st.sampled_from([0, 64, 128, 192, 2**40, 2**40 + 64, 2**64 - 64]),
    r=st.integers(0, 255),
    extra=st.integers(0, 40),
    num_keys=st.integers(0, 2**64 - 1) | st.just(0),
)
def test_arbitrary_valid_checksummed_headers_agree(rows: int, r: int, extra: int, num_keys: int) -> None:
    base = hand_built(128, 8)
    blob = with_fields(base + bytes(extra), num_rows=rows, fp_bits=r, num_keys=num_keys)
    check_agreement(blob, True, ref_probes=1)


# ---------------------------------------------------------------------------------------------------------------
# (f) odd buffers


def _all_members(f: RibbonFilter) -> bool:
    return all(i in f for i in range(400))


def test_from_buffer_at_every_odd_offset_of_a_larger_buffer() -> None:
    blob = BLOBS["n400_r8"]
    for offset in range(1, 17):
        big = bytes([0xEE]) * offset + blob + bytes([0xDD]) * (offset + 3)
        f = RibbonFilter.from_buffer(memoryview(big)[offset : offset + len(blob)])  # payload is not 8-byte aligned
        assert _all_members(f)
        assert f.to_bytes() == blob
        assert c_outcome(memoryview(big)[offset : offset + len(blob) + 1])[0] == "FORMAT"
        assert c_outcome(memoryview(big)[offset - 1 : offset + len(blob)])[0] == "MAGIC"


def test_from_buffer_survives_its_source_going_out_of_scope() -> None:
    blob = bytes(BLOBS["n400_r8"])
    owner = bytearray(b"\x00" * 5 + blob)
    f = RibbonFilter.from_buffer(memoryview(owner)[5:])
    del owner  # the filter keeps the buffer alive: the memoryview slice holds the bytearray
    assert _all_members(f)


@pytest.mark.parametrize(
    "wrap", [bytes, bytearray, memoryview, lambda b: array.array("B", b), lambda b: memoryview(b).cast("B")]
)
def test_from_buffer_buffer_types(wrap: Any) -> None:
    blob = BLOBS["n400_r8"]
    for verify in (True, False):
        assert _all_members(RibbonFilter.from_buffer(wrap(blob), verify=verify))


def test_from_buffer_wide_item_buffers_are_raw_bytes() -> None:
    blob = BLOBS["n400_r8"]
    assert len(blob) % 8 == 0
    for code in "HIQ":
        data = array.array(code)
        data.frombytes(blob)
        assert _all_members(RibbonFilter.from_buffer(data))
        assert _all_members(RibbonFilter.from_buffer(memoryview(data)))


def test_from_buffer_two_dimensional_c_contiguous_view_is_accepted() -> None:
    blob = BLOBS["n400_r8"]
    assert _all_members(RibbonFilter.from_buffer(memoryview(blob).cast("B", shape=[len(blob) // 8, 8])))


@pytest.mark.parametrize("access", [mmap.ACCESS_READ, mmap.ACCESS_COPY, mmap.ACCESS_WRITE])
@pytest.mark.parametrize("verify", [True, False])
def test_from_buffer_mmap_modes(tmp_path: Path, access: int, verify: bool) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(BLOBS["n400_r8"])
    with path.open("r+b") as fh, mmap.mmap(fh.fileno(), 0, access=access) as mm:
        f = RibbonFilter.from_buffer(mm, verify=verify)
        assert _all_members(f)
        del f


def test_from_buffer_mmap_with_trailing_data_needs_a_slice(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    path.write_bytes(BLOBS["n400_r8"] + b"junk")
    with path.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        assert c_outcome(mm)[0] == "FORMAT"
        view = memoryview(mm)[: len(BLOBS["n400_r8"])]
        f = RibbonFilter.from_buffer(view)
        assert _all_members(f)
        del f, view


def test_from_buffer_empty_buffers() -> None:
    for empty in (b"", bytearray(), memoryview(b""), array.array("B")):
        assert c_outcome(empty) == ("TRUNCATED", None)
        assert c_outcome(empty, verify=False) == ("TRUNCATED", None)


def test_from_buffer_non_contiguous_views_raise_buffer_error() -> None:
    blob = BLOBS["n400_r8"]
    stepped = memoryview(blob + blob)[::2]
    two_d = memoryview(blob).cast("B", shape=[len(blob) // 8, 8])
    for bad in (stepped, memoryview(blob)[::-1], memoryview(blob)[1::3], two_d.cast("B")[::5]):
        with pytest.raises(BufferError):
            RibbonFilter.from_buffer(bad)


@pytest.mark.parametrize("bad", ["text", 5, None, [1, 2], 1.5, object()])
def test_from_buffer_rejects_non_buffers_with_type_error(bad: object) -> None:
    with pytest.raises(TypeError):
        RibbonFilter.from_buffer(bad)  # type: ignore[arg-type]


def test_from_buffer_argument_handling() -> None:
    blob = BLOBS["n400_r8"]
    with pytest.raises(TypeError):
        RibbonFilter.from_buffer(blob, False)  # type: ignore[misc]  # verify is keyword-only
    with pytest.raises(TypeError):
        RibbonFilter.from_buffer()  # type: ignore[call-arg]
    assert _all_members(RibbonFilter.from_buffer(buffer=blob, verify=True))


def test_failed_loads_release_the_buffer() -> None:
    data = bytearray(BLOBS["n400_r8"])
    for corrupt in (lambda d: d.__setitem__(0, 0), lambda d: d.__setitem__(-1, d[-1] ^ 1), lambda d: d.append(0)):
        probe = bytearray(data)
        corrupt(probe)
        with pytest.raises(FormatError):
            RibbonFilter.from_buffer(probe)
        probe.append(0)  # would raise BufferError if the failed load had leaked its buffer export
    f = RibbonFilter.from_buffer(data)
    with pytest.raises(BufferError):
        data.append(0)
    del f
    data.append(0)
