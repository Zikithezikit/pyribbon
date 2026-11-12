"""Pure-Python reference implementation of the pyribbon filter spec (DESIGN.md sections 3-5).

It exists to cross-check the C core: the two implementations are written separately from the same spec and must
agree byte for byte. It is slow and used only for small sets in tests. XXH3 comes from the ``xxhash`` PyPI package,
an independent implementation used as the oracle for the vendored C header.

Run ``python tests/spec_reference.py`` to regenerate ``core/tests/vectors.h`` (the C known-answer vectors).
"""

from __future__ import annotations

import pathlib
import struct

import xxhash

MASK = (1 << 64) - 1
GAMMA = 0x9E3779B97F4A7C15
TAG_STR = 0x6A09E667F3BCC908
TAG_INT = 0xBB67AE8584CAA73B
TAG_BIGINT = 0x3C6EF372FE94F82B
KIND_BYTES, KIND_STR, KIND_BIGINT = 0, 1, 2
MAGIC = b"PYRIBBON"
HEADER_SIZE = 64
MAX_ROWS = 1 << 40
OVERHEAD_PPM = [
    66000,
    54000,
    54000,
    53000,
    58000,
    64000,
    71000,
    78000,
    87000,
    95000,
    101000,
    109000,
    115000,
    125000,
    134000,
    139000,
    148000,
    155000,
]


class ReferenceError(Exception):
    """Raised with the name of the equivalent C status (e.g. ``"CONSTRUCT"``, ``"FORMAT"``)."""

    def __init__(self, status: str) -> None:
        """Store the status name."""
        super().__init__(status)
        self.status = status


def mix64(z: int) -> int:
    """Return the SplitMix64 finalizer of ``z``."""
    z &= MASK
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & MASK
    return z ^ (z >> 31)


def xxh3(data: bytes) -> int:
    """Return XXH3-64 of ``data`` (seed 0)."""
    return xxhash.xxh3_64_intdigest(data)


def _seed_offset(seed: int) -> int:
    return mix64((seed + GAMMA) & MASK)


def hash_bytes(data: bytes, seed: int, kind: int) -> int:
    """Return the master hash of a byte key (DESIGN.md section 3.1)."""
    h0 = xxh3(data)
    if kind == KIND_STR:
        h0 ^= TAG_STR
    elif kind == KIND_BIGINT:
        h0 ^= TAG_BIGINT
    return mix64((h0 + _seed_offset(seed)) & MASK)


def hash_i64(value: int, seed: int) -> int:
    """Return the master hash of an int in [-2**63, 2**63)."""
    return mix64((((value & MASK) ^ TAG_INT) + _seed_offset(seed)) & MASK)


def hash_int(value: int, seed: int) -> int:
    """Return the master hash of any int: int64 by value, anything else as length ``bit_length // 8 + 1`` bytes."""
    if -(1 << 63) <= value < (1 << 63):
        return hash_i64(value, seed)
    encoded = value.to_bytes(value.bit_length() // 8 + 1, "little", signed=True)
    return hash_bytes(encoded, seed, KIND_BIGINT)


def hash_key(key: object, seed: int) -> int:
    """Return the master hash of a Python key (DESIGN.md section 3.1)."""
    if isinstance(key, int):
        return hash_int(key, seed)
    if isinstance(key, str):
        return hash_bytes(key.encode("utf-8"), seed, KIND_STR)
    if isinstance(key, (bytes, bytearray, memoryview)):
        return hash_bytes(bytes(key), seed, KIND_BYTES)
    raise TypeError(type(key).__name__)


def derive(h: int, attempt: int, num_rows: int, r: int) -> tuple[int, int, int]:
    """Return ``(start, coeff, fp)`` for master hash ``h`` (DESIGN.md section 3.2)."""
    state = h ^ mix64(((attempt + 1) * GAMMA) & MASK)
    z0 = mix64((state + GAMMA) & MASK)
    z1 = mix64((state + 2 * GAMMA) & MASK)
    z2 = mix64((state + 3 * GAMMA) & MASK)
    return (z0 * (num_rows - 63)) >> 64, z1 | 1, z2 >> (64 - r)


def _trunc_div(a: int, b: int) -> int:
    """Integer division truncating toward zero, as C does."""
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b > 0) else -q


def default_overhead_ppm(n: int) -> int:
    """Mirror of the integer sizing table in ``ribbon.c`` (parts per million)."""
    if n <= 128:
        return OVERHEAD_PPM[0]
    k = n.bit_length() - 1
    base = 1 << k
    rem = n - base
    if k >= 24:
        return OVERHEAD_PPM[17] + 7000 * (k - 24) + 7000 * rem // base
    lo, hi = OVERHEAD_PPM[k - 7], OVERHEAD_PPM[k - 6]
    return lo + _trunc_div((hi - lo) * rem, base)


def default_overhead(n: int) -> float:
    """Return the default overhead as a fraction (the table value in ppm divided by 1e6)."""
    return default_overhead_ppm(n) / 1e6


def _round_up64(x: int) -> int:
    return (x + 63) & ~63


def initial_rows(n: int, eps: float) -> int:
    """Return the initial row count for ``n`` keys at overhead ``eps`` (a fraction, rounded to whole ppm)."""
    scaled = n * (1_000_000 + int(eps * 1e6 + 0.5))
    m = -(-scaled // 1_000_000)
    return max(_round_up64(m), 128)


def grow_rows(m: int) -> int:
    """Return the row count after one growth step."""
    return _round_up64(m + max(m // 64, 64))


def _insert(coeff: list[int], res: list[int], i: int, c: int, b: int) -> bool:
    while True:
        stored = coeff[i]
        if stored == 0:
            coeff[i], res[i] = c, b
            return True
        c ^= stored
        b ^= res[i]
        if c == 0:
            return b == 0
        j = (c & -c).bit_length() - 1
        i += j
        c >>= j


def build(
    hashes: list[int], r: int = 8, seed: int = 0, overhead: float | None = None, max_attempts: int = 32
) -> tuple[int, int, bytes]:
    """Build a filter; return ``(num_rows, attempt, payload)``. Raise ``ReferenceError("CONSTRUCT")`` on failure."""
    n = len(hashes)
    if n == 0:
        return 0, 0, b""
    eps = default_overhead(n) if overhead is None or overhead < 0 else overhead
    rows = initial_rows(n, eps)
    for attempt in range(max_attempts):
        if attempt >= 2:
            rows = grow_rows(rows)
        coeff = [0] * rows
        res = [0] * rows
        if all(_insert(coeff, res, *derive(h, attempt, rows, r)) for h in hashes):
            return rows, attempt, _back_substitute(coeff, res, rows, r)
    raise ReferenceError("CONSTRUCT")


def _back_substitute(coeff: list[int], res: list[int], rows: int, r: int) -> bytes:
    st = [0] * r
    out = bytearray((rows // 64) * r * 8)
    for i in range(rows - 1, -1, -1):
        c, b = coeff[i], res[i]
        for j in range(r):
            st[j] = (st[j] << 1) & MASK
            st[j] |= (bin(st[j] & c).count("1") & 1) ^ ((b >> j) & 1)
        if i % 64 == 0:
            base = (i // 64) * r * 8
            for j in range(r):
                out[base + 8 * j : base + 8 * j + 8] = struct.pack("<Q", st[j])
    return bytes(out)


def serialize(num_keys: int, num_rows: int, r: int, seed: int, attempt: int, payload: bytes) -> bytes:
    """Return the serialized filter (DESIGN.md section 5)."""
    h = bytearray(HEADER_SIZE)
    h[0:8] = MAGIC
    struct.pack_into("<HHBBBB", h, 8, 1, HEADER_SIZE, 6, r, 1, 0)
    struct.pack_into("<QQQI", h, 16, num_keys, num_rows, seed, attempt)
    struct.pack_into("<Q", h, 48, xxh3(payload))
    struct.pack_into("<Q", h, 56, xxh3(bytes(h[:56])))
    return bytes(h) + payload


def parse(buf: bytes, verify: bool = True) -> dict[str, int]:
    """Validate ``buf`` exactly like ``rb_from_buffer``; raise ``ReferenceError`` with the status name."""
    if len(buf) < HEADER_SIZE:
        raise ReferenceError("TRUNCATED")
    if buf[:8] != MAGIC:
        raise ReferenceError("MAGIC")
    version, header_size, width_log2, r, hash_id, flags = struct.unpack_from("<HHBBBB", buf, 8)
    num_keys, rows, seed, attempt = struct.unpack_from("<QQQI", buf, 16)
    (reserved,) = struct.unpack_from("<I", buf, 44)
    payload_xxh3, header_xxh3 = struct.unpack_from("<QQ", buf, 48)
    if version != 1:
        raise ReferenceError("VERSION")
    if header_size != HEADER_SIZE:
        raise ReferenceError("FORMAT")
    if header_xxh3 != xxh3(buf[:56]):
        raise ReferenceError("CHECKSUM")
    if width_log2 != 6 or hash_id != 1 or flags != 0 or reserved != 0:
        raise ReferenceError("FORMAT")
    if not 1 <= r <= 32:
        raise ReferenceError("FORMAT")
    if rows != 0 and (rows % 64 != 0 or rows < 128 or rows > MAX_ROWS):
        raise ReferenceError("FORMAT")
    if (rows == 0) != (num_keys == 0) or num_keys > rows:
        raise ReferenceError("FORMAT")
    payload_len = (rows // 64) * r * 8
    have = len(buf) - HEADER_SIZE
    if have < payload_len:
        raise ReferenceError("TRUNCATED")
    if have > payload_len:
        raise ReferenceError("FORMAT")
    if verify and payload_xxh3 != xxh3(buf[HEADER_SIZE:]):
        raise ReferenceError("CHECKSUM")
    return {"num_keys": num_keys, "num_rows": rows, "fp_bits": r, "seed": seed, "attempt": attempt}


def contains(buf: bytes, h: int) -> bool:
    """Query a serialized filter (already validated by ``parse``)."""
    meta = parse(buf, verify=False)
    rows, r = meta["num_rows"], meta["fp_bits"]
    if rows == 0:
        return False
    start, coeff, fp = derive(h, meta["attempt"], rows, r)
    for j in range(r):
        bit = 0
        for k in range(64):
            if (coeff >> k) & 1:
                row = start + k
                word = struct.unpack_from("<Q", buf, HEADER_SIZE + ((row >> 6) * r + j) * 8)[0]
                bit ^= (word >> (row & 63)) & 1
        if bit != (fp >> j) & 1:
            return False
    return True


# ---------------------------------------------------------------------------------------------------------------
# C known-answer vectors


def _c_bytes(b: bytes) -> str:
    return "{" + ", ".join(f"0x{x:02x}" for x in b) + "}" if b else "{0}"


def generate_vectors() -> str:
    """Return the text of ``core/tests/vectors.h``."""
    assert mix64(GAMMA) == 0xE220A8397B1DCDAF  # published SplitMix64 reference output for seed 0
    out = ["/* Generated by tests/spec_reference.py. Do not edit. */", "#ifndef VECTORS_H", "#define VECTORS_H", ""]
    out.append("typedef struct { const unsigned char *data; unsigned long len; unsigned long long xxh3; } vec_xxh3;")
    msgs = [b"", b"a", b"abc", b"hello world", bytes(range(16)), bytes(range(17)), bytes(i % 251 for i in range(128)),
            bytes(i % 251 for i in range(129)), bytes(i % 251 for i in range(240)), bytes(i % 251 for i in range(241)),
            bytes(i % 251 for i in range(1000)), "ünïcödé ключ 鍵".encode()]  # fmt: skip
    for i, m in enumerate(msgs):
        out.append(f"static const unsigned char vec_msg{i}[] = {_c_bytes(m)};")
    out.append("static const vec_xxh3 vec_xxh3_tbl[] = {")
    for i, m in enumerate(msgs):
        out.append(f"  {{vec_msg{i}, {len(m)}ul, 0x{xxh3(m):016x}ull}},")
    out.append("};")
    out.append("typedef struct { int kind; unsigned msg; unsigned long long seed; unsigned long long hash; } vec_hash;")
    out.append("static const vec_hash vec_hash_tbl[] = {")
    for kind in (KIND_BYTES, KIND_STR, KIND_BIGINT):
        for seed in (0, 0x123456789ABCDEF0):
            for i in (0, 1, 3, 6, 11):
                out.append(f"  {{{kind}, {i}u, 0x{seed:x}ull, 0x{hash_bytes(msgs[i], seed, kind):016x}ull}},")
    out.append("};")
    out.append("typedef struct { long long value; unsigned long long seed; unsigned long long hash; } vec_i64;")
    out.append("static const vec_i64 vec_i64_tbl[] = {")
    for v in (0, 1, -1, 42, 2**63 - 1, -(2**63), 1234567890123):
        for seed in (0, 7):
            lit = "(-9223372036854775807ll - 1)" if v == -(2**63) else f"{v}ll"  # INT64_MIN has no literal in C
            out.append(f"  {{{lit}, {seed}ull, 0x{hash_i64(v, seed):016x}ull}},")
    out.append("};")
    out.append("typedef struct { unsigned long long h; unsigned attempt; unsigned long long rows; unsigned r; "
               "unsigned long long start; unsigned long long coeff; unsigned fp; } vec_derive;")  # fmt: skip
    out.append("static const vec_derive vec_derive_tbl[] = {")
    cases = [(0, 0, 128, 1), (1, 0, 128, 8), (0xFFFFFFFFFFFFFFFF, 3, 1024, 32), (0x0123456789ABCDEF, 31, 4096, 8),
             (hash_i64(5, 0), 0, 192, 16), (hash_i64(6, 9), 1, 1 << 20, 7), (0x8000000000000000, 0, 64 * 1000, 24)]  # fmt: skip
    for h, a, rows, r in cases:
        s, c, fp = derive(h, a, rows, r)
        out.append(f"  {{0x{h:x}ull, {a}u, {rows}ull, {r}u, {s}ull, 0x{c:x}ull, {fp}u}},")
    out.append("};")
    out.append("typedef struct { unsigned long long n; unsigned long long ppm; } vec_ppm;")
    out.append("static const vec_ppm vec_ppm_tbl[] = {")
    ns = [1, 100, 128, 129, 130, 1000, 4097, 12345, 99999, 100000, 1000000, 1500000, 2**24 - 1, 2**24, 2**24 + 12345,
          2**26 + 7, 10**9, 2**37 + 5]  # fmt: skip
    for n in ns:
        out.append(f"  {{{n}ull, {default_overhead_ppm(n)}ull}},")
    out.append("};")
    # whole-filter vectors: C must reproduce the serialized bytes exactly
    out.append("typedef struct { unsigned n; unsigned r; unsigned long long seed; double overhead; "
               "unsigned attempt; unsigned long long rows; const unsigned char *bytes; unsigned long len; } vec_filter;")  # fmt: skip
    out.append("/* keys are rb_hash_i64(i, seed) for i in [0, n) */")
    specs = [(200, 8, 0, 0.05), (1000, 12, 77, 0.06), (63, 1, 5, 0.0), (500, 32, 1, 0.07), (300, 8, 3, 0.0)]
    for idx, (n, r, seed, ov) in enumerate(specs):
        hs = [hash_i64(i, seed) for i in range(n)]
        rows, attempt, payload = build(hs, r, seed, ov, 32)
        blob = serialize(n, rows, r, seed, attempt, payload)
        out.append(f"static const unsigned char vec_filter{idx}[] = {_c_bytes(blob)};")
    out.append("static const vec_filter vec_filter_tbl[] = {")
    for idx, (n, r, seed, ov) in enumerate(specs):
        hs = [hash_i64(i, seed) for i in range(n)]
        rows, attempt, payload = build(hs, r, seed, ov, 32)
        blob = serialize(n, rows, r, seed, attempt, payload)
        out.append(f"  {{{n}u, {r}u, {seed}ull, {ov}, {attempt}u, {rows}ull, vec_filter{idx}, {len(blob)}ul}},")
    out.append("};")
    out += ["", "#endif", ""]
    return "\n".join(out)


def write_fuzz_corpus(directory: pathlib.Path) -> None:
    """Write a few valid serialized filters as the fuzzing seed corpus."""
    directory.mkdir(parents=True, exist_ok=True)
    for name, n, r in (("empty", 0, 8), ("n50_r4", 50, 4), ("n400_r8", 400, 8), ("n1000_r16", 1000, 16)):
        hs = [hash_i64(i, 1) for i in range(n)]
        rows, attempt, payload = build(hs, r, 1)
        (directory / f"{name}.bin").write_bytes(serialize(n, rows, r, 1, attempt, payload))


if __name__ == "__main__":
    root = pathlib.Path(__file__).resolve().parent.parent
    target = root / "core" / "tests" / "vectors.h"
    target.write_text(generate_vectors())
    write_fuzz_corpus(root / "core" / "fuzz" / "corpus")
    print(f"wrote {target} and core/fuzz/corpus/")
