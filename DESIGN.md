# DESIGN (v0.1, approved 2026-11-12)

Status: approved on 2026-11-12; implementation in progress. Evidence and citations are in RESEARCH.md.
`R§n` points to a section of RESEARCH.md; a plain `§n` points inside this file. Resolved decisions are listed in §15.

## 0. Phase 0 record

* Name. `https://pypi.org/pypi/pyribbon/json` returned HTTP 404 on 2026-11-12, and a grep of the full PyPI simple
  index (938,319 projects) for "ribbon" found 21 unrelated names, none `pyribbon`. The name is free today;
  re-check at upload time (PyPI names can be taken at any moment). The unrelated GitHub project called pyribbon
  (a Sonus/Ribbon SBC REST client) is not on PyPI under that name. Decided 2026-11-12: keep `pyribbon`.
* Gap. No Python ribbon-filter package or BuRR wrapper found on PyPI or GitHub. Ribbon implementations exist in
  Rust (`pleat`, `ribbon-filter`), Go (`ribbonGo`), C++ (RocksDB, `fastfilter_cpp`, `lorenzhs/BuRR`) (R§10).
* Corrections to the brief. (1) `pyxorfilter` exists but is unusable on Python 3.13/3.14 (no wheel, broken
  sdist, breaks with xxhash 4.x, `in` loops forever); its maintained successor is `pyfusefilter`, which the benchmark
  uses instead (R§12). (2) "A fastfilter_cpp fork with BuRR" is `lorenzhs/fastfilter_cpp`, which pulls the BuRR
  code from the separate `lorenzhs/BuRR` repo. (3) "Balanced" ribbon is a real variant but exists only in the Ribbon
  paper, as experimental, with details left to code (R§2).

## 1. v0.1 scope

Variant: standard ribbon, width w = 64, integer fingerprint bits r = 1..32, interleaved column layout.

Why standard: FP = 2^-r *exactly* (the fingerprint is independent of the equations), which is what the requirement
"measured FPR matches 2^-r" and "retry with a new seed on failure" both assume (R§2, R§5). Homogeneous ribbon never
fails but gives FP = p + (1-p)·2^-r, can exceed 2^-r, and has undetectable FP variance on small sets (R§2). Standard
ribbon is simpler to prove correct with tests.

Why w = 64: one machine word, shifts and parity are single instructions, and the authors advise 32 or 64 on 64-bit
machines (R§3). Decided 2026-11-12 after a measurement (`benchmarks/research/`, a simulation of the paper's
elimination, i7-7700): overhead needed for 95% per-attempt success, w = 64 vs w = 128:

| slots `m` | 2^10 | 2^14 | 2^17 | 2^20 | 2^22 |
|---|---:|---:|---:|---:|---:|
| w = 64 | 4.7% | 6.9% | 9.6% | 11.5% | 12.7% |
| w = 128 | 2.2% | 2.7% | 3.7% | 4.6% | 5.5% |

(These agree with [R Table 1] and RocksDB's tables where they overlap: 4.7% vs 4.9% at 2^10, 3.8% vs 3.8% at 50%
success and 2^14. RocksDB's extrapolation past 2^17 overstates the w = 64 overhead: ~14% predicted vs 12.7% measured
at 2^22.) At r = 8 and n = 1e6, w = 64 costs about 9.0 bits/key against Fuse8's 9.04 (pyfusefilter, measured by the
benchmark harness on a loaded machine), and 8.8 against 9.51 at n = 1e5. Ribbon with w = 64 therefore wins on space at
small and medium n and is level with Fuse at n = 1e6 and beyond. w = 128 would save a further ~6% of bits per key, but
its insertion was 2-3x slower in my naive generic code, and it needs a two-word core with 128-bit shifts in the query.
That is not worth it for v0.1. w = 128 and hard sharding lead the roadmap, and the format already carries the width, so
adding them is not a format break. Caveat for the README: the space advantage over Fuse is single-digit percent at large n.

Deferred to the roadmap (§13): BuRR, Balanced, homogeneous, w = 128, sharding, SIMD, parallel build, fractional r,
smash, free-threaded wheels.

## 2. Parameters

| Parameter | Default | Range | Justification |
|---|---|---|---|
| width `w` | 64 | fixed (stored in header as `width_log2`) | §1 |
| `fp_bits` r | 8 | 1..32 | FP ≈ 2^-r. 8 matches Xor8/Fuse8 (0.39%) for like-for-like benchmarks; ≤ 32 keeps the per-slot result in a `uint32_t` |
| rows `m` | `roundup64(ceil(n·(1+ε(n))))`, min 128 | multiple of 64 | the interleaved layout needs `m % 64 == 0`; `m ≥ 2w` so that the number of start positions `m-w+1 > w` and every window has a following block (R§9) |
| overhead ε(n) | table at n = 2^7..2^24 interpolated linearly in n (6.6% at 2^7, 5.3% at 2^10, 9.5% at 2^16, 12.5% at 2^20, 15.5% at 2^24); above 2^24 +0.7 pp per doubling | `overhead=` override | measured with the real derivation and insertion code (`make calibrate`, `core/tools/overhead_table.py`): 3rd percentile of the fill at first failure, i.e. 97% per-attempt success, expected attempts ≈ 1.03. Above 2^24 slots it is extrapolated from the measured slope and unmeasured. |
| `max_attempts` | 32 | 1..255 | with 5% per-attempt failure, 32 attempts is far below any realistic failure rate; RocksDB uses 256 with a Bloom fallback (R§9); we raise instead |
| retry policy | new seed every attempt; from the 3rd attempt also grow `m` by `(w+1)/w` | | reseeding is the primary mechanism; growth is the paper's alternative [R p9] and guarantees termination even if the fit is wrong for some `n` (R§5) |
| `seed` | 0 | 0..2^64-1 | user domain separation; stored in the header |

Validation (`make ovh-sweep`, real library, an independent key range per trial; 4000 trials for n <= 1000, 1500 for
3e3-1e4, 300 for 1e5, 60 for 1e6): per-attempt failure at the default overhead is 0.0% (n=100), 0.85% (300), 0.10% (1e3),
1.8% (3e3), 2.1% (1e4), 3.3% (1e5), 3.3% (1e6); mean attempts <= 1.033; so the acceptance bound (failure <= 7%, mean attempts
<= 1.1) holds at every size. Resulting size at r = 8 is 8.70 / 8.60 / 8.79 / 8.99 bits/key, payload only. The 64-byte header adds
512/n bits per key, so `bits_per_key` reads 9.22 at n = 1e3, 8.65 at 1e4, 8.79 at 1e5, 8.99 at 1e6. Tiny sets are padded to
the 128-row minimum: 10.24 bits/key payload, 15.4 with header at n = 100. Two measurement pitfalls were found along the way,
and both are fixed:
(1) the first version mixed the seed into the key hash by XOR, so dense integer keys gave overlapping hash sets for nearby
seeds (`seed=1` rebuilt almost the filter of `seed=0`); (2) trials that re-use the same keys share hash values and are
correlated, which had inflated one failure-rate estimate to 12% against 4% for independent trials.

On failure the build raises `ConstructionError` after `max_attempts`; a filter that did not pass banding is
never returned. `n = 0` produces a valid empty filter (header only, `num_rows = 0`, every query false).

## 3. Hashing (key → bytes → 64 bits → ribbon coordinates)

Python's built-in `hash()` is never used (randomized per process; breaks saved filters).

### 3.1 Key to master hash `H` (hash id 1, frozen by spec; any change bumps `hash_id`)

| Key type | Rule |
|---|---|
| `bytes`, `bytearray`, `memoryview` (C-contiguous) | payload bytes `P`; `h0 = XXH3_64bits(P)` (seed 0, default secret). A `memoryview` is treated as raw bytes regardless of its format. |
| `str` | UTF-8 bytes (strict; a lone surrogate raises `UnicodeEncodeError`); `h0 = XXH3_64bits(P) ^ TAG_STR` |
| `int` (or anything with `__index__`) in `[-2^63, 2^63)` | `h0 = (uint64_t)value ^ TAG_INT` (two's complement of the numeric value; no byte order involved) |
| any other `int` | `P` = little-endian two's complement of exactly `value.bit_length() // 8 + 1` bytes (one canonical encoding per value); `h0 = XXH3_64bits(P) ^ TAG_BIGINT` |
| anything else (`float`, `None`, tuples, ...) | `TypeError`. No implicit `str()`: `51` and `"51"` are different keys and floats are not keys |

`TAG_STR = 0x6a09e667f3bcc908`, `TAG_INT = 0xbb67ae8584caa73b`, `TAG_BIGINT = 0x3c6ef372fe94f82b` (SHA-512 initial
values, chosen as nothing-up-my-sleeve), and the bytes tag is 0. So `b"a"`, `"a"` and `97` are distinct keys. Then
`H = mix64(h0 + mix64(seed + GAMMA))`. The seed is pre-mixed and added. An earlier draft XORed it into `h0`; a
measurement showed that for dense integer keys the hash values then overlap across nearby seeds (`{i ^ seed}` is nearly the same set), so
`seed=1` rebuilt almost the same filter as `seed=0` and trial outcomes were correlated. A random 64-bit offset makes every seed an
independent hash universe.

`mix64` is the SplitMix64 finalizer (Vigna; public domain) and `GAMMA = 0x9e3779b97f4a7c15`:
`z = (z ^ z>>30)·0xbf58476d1ce4e5b9; z = (z ^ z>>27)·0x94d049bb133111eb; return z ^ z>>31`.

* XXH3-64 is vendored (`xxhash.h`, BSD-2-Clause, notice shipped in sdist and wheels) with
  `XXH_FORCE_MEMORY_ACCESS=0` (the default mode let GCC miscompile in BuRR's experience, R§10), scalar mode, fixed seed.
  Why XXH3: the only candidate with a written output-stability promise, a spec, in-repo test vectors, and
  byte-order-independent output (R§11). Fallback if you object to a 7.5k-line vendored header: SipHash-2-4 (CC0, 185
  lines, ~5x slower on short keys per third-party numbers).
* The int path is defined on the numeric value and `mix64` is a bijection, so distinct int64 keys never collide in `H`.
* Distinct bytes/str keys collide in `H` with probability ≈ n²/2^65 (0.027 expected colliding pairs at n = 1e9). A
  collision, like a duplicate key, yields identical equations; standard ribbon accepts these as redundant (R§4), so it
  costs nothing but one possible false positive.

### 3.2 `H` to ribbon coordinates (independent 64-bit words, own derivation)

RocksDB-style designs stretch one 64-bit hash into the start, the coefficient row and the fingerprint with a
multiplication, and for w = 128 only 64 bits of entropy back a 128-bit row (R§9). A bare multiply has no avalanche
(measured: max deviation 0.5, R§11). We use independent words instead:

```
salt_a = mix64((a + 1) * GAMMA)            # a = attempt index, stored in the header
S      = H ^ salt_a
z0 = mix64(S + 1*GAMMA);  z1 = mix64(S + 2*GAMMA);  z2 = mix64(S + 3*GAMMA)
start  = mulhi64(z0, m - 63)               # floor(z0 * (m-w+1) / 2^64), in [0, m-64]
coeff  = z1 | 1                            # bit 0 forced to 1 (the row at `start`), [R p3]
fp     = z2 >> (64 - r)                    # top r bits
```

The seed is mixed *after* `H` is already a full-avalanche value, so retries are not correlated the way "add the seed
to the key before hashing" is (R§11). XXH3's own seed argument is not used (weak in third-party SMHasher3 runs, R§11).
The builder hashes each key once into a `uint64_t H[n]` array (8 bytes/key of temporary memory) and every retry
recomputes only the cheap derivation. Clean-room note: this derivation is my construction from the papers' requirements
(R§6: fastrange on high bits, forced low coefficient bit, independent fingerprint); it uses none of RocksDB's constants.

## 4. C core

C11, no dependencies besides the vendored `xxhash.h`, no global state, no atomics, no `malloc` inside queries,
no VLAs. Layout: `core/include/ribbon.h`, `core/src/*.c`, `core/tests/*.c`, `core/fuzz/`, `core/vendor/`. Builds and
tests with `make -C core test` and no Python.

```c
typedef struct rb_filter rb_filter;                 /* opaque */
typedef enum {
  RB_OK = 0, RB_E_INVALID_ARG, RB_E_NOMEM, RB_E_CONSTRUCT /* all attempts failed */,
  RB_E_TOO_LARGE, RB_E_TRUNCATED, RB_E_MAGIC, RB_E_VERSION, RB_E_FORMAT, RB_E_CHECKSUM
} rb_status;
typedef enum { RB_KEY_BYTES = 0, RB_KEY_STR = 1, RB_KEY_BIGINT = 2 } rb_key_kind;
typedef struct { uint32_t fp_bits; uint32_t max_attempts; double overhead; /* <0: auto */ uint64_t seed; } rb_params;
typedef struct { uint32_t attempts; uint64_t num_rows; } rb_build_info;

rb_params rb_params_default(void);
const char *rb_strerror(rb_status status);
uint64_t  rb_hash_bytes(const void *data, size_t len, uint64_t seed, rb_key_kind kind);   /* section 3.1 */
uint64_t  rb_hash_i64(int64_t value, uint64_t seed);
double    rb_default_overhead(uint64_t n);   /* the sizing table, section 2 */

rb_status rb_build(const uint64_t *key_hashes, size_t n, const rb_params *p, rb_filter **out, rb_build_info *info);
rb_status rb_from_buffer(const void *buf, size_t len, int verify_payload, rb_filter **out); /* zero copy: caller keeps buf alive */
void      rb_free(rb_filter *f);
int       rb_contains(const rb_filter *f, uint64_t key_hash);
void      rb_contains_many(const rb_filter *f, const uint64_t *hashes, size_t n, uint8_t *out);
size_t    rb_serialized_size(const rb_filter *f);
rb_status rb_serialize(const rb_filter *f, void *dst, size_t cap);
/* accessors: rb_num_keys, rb_num_rows, rb_fp_bits, rb_seed */
```

* The core takes key hashes as input. Hashing is a separate step, so the Python layer can hash Python objects and
  call the core on a `uint64_t` array.
* `rb_filter` copies every header field into the struct at load time and never re-reads the header from the
  buffer. Only payload words are read, at offsets computed from the validated struct; so a buffer mutated after
  loading can give wrong answers but cannot cause an out-of-bounds read (no time-of-check/time-of-use hole).
* Build. One array of 16-byte slots `{uint64_t coeff; uint32_t res}` (one cache line per insertion), empty slot = `coeff == 0`.
  Keys are processed in chunks of 16: the equations of a chunk are derived and their slots prefetched first, then inserted in
  arrival order, so the result is identical to one-at-a-time insertion (the byte-for-byte vectors prove it).
  Per key: `i = start; c = coeff; b = fp`; loop { if slot `i` empty, store, done; `c ^= coeff[i]; b ^= res[i]`; if
  `c == 0`: redundant if `b == 0`, else failure; `j = ctz(c); i += j; c >>= j` } (R§4). `c` always has bit 0 set before
  the XOR and `c != 0` before `ctz`, so `1 ≤ j ≤ 63` and no shift reaches the type width. No pre-sort (R§4).
  Back-substitution runs `i = m-1 .. 0`, keeps one 64-bit running word per column, and writes the interleaved layout
  directly, one flushed block of `r` words per 64 rows (R§4).
* Query. `s = start`, `blk = s >> 6`, `off = s & 63`; for each column `j < r`: the result bit is
  `parity(W[blk][j] & (c << off)) ^ parity(W[blk+1][j] & (c >> (64 - off)))` (coefficient bit `k` selects row `s+k`; the
  second term covers the bits that spill into the next block), with the second term skipped when `off == 0` (a shift by 64 is undefined behaviour). Early exit at the first mismatching
  column. The last start is `m-64`, i.e. `off == 0` on the last block, so `blk+1` always exists when `off > 0`: no
  read beyond the buffer (R§9).
* Portable bit ops live in one internal header: `ctz64`, `parity64`, `mulhi64`, `load_le64`/`store_le64`. Selection by
  `#if`: GCC/Clang builtins (`__builtin_ctzll`, `__builtin_parityll`, `unsigned __int128`); MSVC (`_BitScanForward64`
  on x64/ARM64, `_umul128` on x64, `__umulh` on ARM64; no `__popcnt64`, since parity folds with XORs and needs no
  POPCNT); and pure-C fallbacks (de Bruijn `ctz`, XOR-fold parity, 32x32 split multiply). The fallbacks are compiled
  and tested on Linux by forcing `-DRB_PORTABLE=1`. All integers are `uint64_t`/`uint32_t`, never `long` (32-bit on
  Win64). `load_le64` is `memcpy` plus a byte swap on big-endian hosts, so no unaligned or endianness assumption.
* Warnings: `-std=c11 -Wall -Wextra -Wconversion -Wshadow -Wcast-align -Wstrict-prototypes -Wmissing-prototypes -Werror`.
* Sizing is integer arithmetic. The overhead table is stored in parts per million and interpolated with integer division, a
  user `overhead=` is rounded once to whole ppm, and the row count is `ceil(n·(1e6 + ppm) / 1e6)`: no floating-point
  contraction on any platform can change a row count, so the same keys, parameters and seed give the same bytes everywhere
  (the Python reference mirrors the integer code and the byte-for-byte vectors cover it). `n ≤ RB_MAX_KEYS = 2^38` and
  `ppm ≤ 4e6` keep `n·(1e6 + ppm)` below 2^61; rows above 2^39 are `RB_E_TOO_LARGE`. `rb_build` leaves `*info` untouched on failure.

## 5. Serialization (format v1, little-endian, all fields explicit)

| Offset | Size | Field | Notes |
|---:|---:|---|---|
| 0 | 8 | magic | `"PYRIBBON"` |
| 8 | 2 | `version` | 1; a reader rejects other versions (`RB_E_VERSION`) |
| 10 | 2 | `header_size` | 64 |
| 12 | 1 | `width_log2` | 6 |
| 13 | 1 | `fp_bits` | 1..32 |
| 14 | 1 | `hash_id` | 1 (§3) |
| 15 | 1 | `flags` | 0; reserved bits must be zero |
| 16 | 8 | `num_keys` | inputs counted, duplicates included; never used for addressing, but validated: 0 iff `num_rows == 0`, and ≤ `num_rows` (every filter `rb_build` makes has `num_rows ≥ num_keys`) |
| 24 | 8 | `num_rows` | 0, or a multiple of 64 in [128, 2^40] |
| 32 | 8 | `seed` | user seed |
| 40 | 4 | `attempt` | seed index that succeeded |
| 44 | 4 | reserved | 0 |
| 48 | 8 | `payload_xxh3` | XXH3-64 of the payload |
| 56 | 8 | `header_xxh3` | XXH3-64 of bytes 0..55 |
| 64 | `num_rows/64·r·8` | payload | for block `k`, `r` words; word `j` holds column `j` for rows `64k..64k+63`, row `64k+i` at bit `i` |

Loader rules (the input is untrusted), checked in this order (the first failure decides the status, and
`tests/spec_reference.py` mirrors the order): (1) `len ≥ 64`, else TRUNCATED; (2) magic (MAGIC), version (VERSION),
`header_size == 64` (FORMAT); (3) `header_xxh3` matches (CHECKSUM); (4) `width_log2 == 6`, `hash_id == 1`, `flags == 0`,
reserved `== 0`, `fp_bits` in 1..32 (FORMAT); (5) `num_rows` is 0 or a multiple of 64 in [128, 2^40] (FORMAT); (6) `num_keys`
is 0 iff `num_rows == 0`, and `num_keys ≤ num_rows` (FORMAT; this keeps `len()` of a loaded filter meaningful);
(7) `payload_len = num_rows/64·r·8` (at most 2^42, so it cannot overflow 64 bits given rule 5), the buffer holds fewer
bytes (TRUNCATED) or more (FORMAT: slice a memoryview to embed a filter in a larger buffer) than `64 + payload_len`;
(8) if `verify_payload`, `payload_xxh3` matches (CHECKSUM; reads every byte once). `from_buffer(verify=False)` skips only
rule 8, which keeps an mmapped filter lazy; rules 1-7 are O(1) and always run, so even the unverified path cannot read out of
bounds. The loader copies the 64 header bytes into a local buffer first and parses only that copy, so a concurrent writer to
the buffer cannot make validation and use see different header values. Payload corruption under `verify=False` can only change
query answers (`attempt` is also taken as-is). The checksum detects accidents, not tampering (it is not a MAC), and a file
truncated by another process while memory-mapped faults on access (SIGBUS), which no library can prevent.

Zero copy: a loaded filter keeps a pointer into the caller's buffer; the payload is read with `load_le64`, so the same
file works on little- and big-endian hosts without a conversion pass. Nothing is allocated per query.

## 6. Python binding

Recommendation: a thin hand-written CPython C extension, built with setuptools, limited API (abi3, floor 3.11) for
3.11+ and the same source built non-limited for 3.10 (R§12). Why: the same per-call cost as the full API and
the best of the three options measured (a trivial call costs 32-34 ns vs 41 Cython `def` vs 175-267 cffi, R§12); zero runtime
dependencies; build dependencies are setuptools and a C compiler; an sdist builds with only `cc`. Cython and cffi are
rejected partly on speed; they also add a build or runtime dependency without a measured gain, and cffi
cannot define `__contains__` as a type slot. meson-python is rejected (needs a VCS checkout for sdist, breaks on 3.10
and 3.14t); scikit-build-core is the runner-up if CMake is ever wanted.

* Python 3.10. `Py_buffer` entered the stable ABI in 3.11, so 3.10 gets its own non-limited wheel from the same
  source (about 10 lines of conditional logic in `setup.py`). 3.10 reached end of life on 2026-10-01, but it is kept (decided
  2026-11-12) after checking pypistats (past month): 3.10 is still 12.8% of numpy's downloads and 16.7% of cryptography's.
  The cost is one extra wheel per platform; dropping it later removes that wheel and the conditional.
* Free-threaded (3.14t) has no abi3, and `Py_MOD_GIL_NOT_USED` is not declared before testing: v0.1 skips
  `*t-*` wheels, so a free-threaded interpreter builds from the sdist and re-enables the GIL on import. Roadmap item.
* GIL. Single-key `__contains__` never releases the GIL (the save/restore costs more than the ~30 ns of work, R§12).
  `build` hashes keys with the GIL held (it touches Python objects; the integer-buffer path below hashes without it), then releases the GIL for banding and back
  substitution (pure C, can take seconds). `contains_many` hashes into a temporary array with the GIL held and
  releases it for the probe loop when the batch is ≥ 1024 keys (an untuned threshold; a 4-thread test shows about 1.7x
  the single-thread time, against about 4x with the GIL held). Between the
  macros the code touches no Python object, refcount, `PyErr_*` or `PyMem_*` allocator (R§12).
* Thread safety. An immutable filter is safe to query from many threads at once: no field is written after
  construction, there is no lazy state, and the core has no globals. Concurrent builds are independent. `free` of the last
  reference cannot race a running query, because a query holds a reference. The docs state this, and
  `tests/test_concurrency.py` exercises it (8 threads on one shared filter; concurrent builds; GIL-release checks).
* Buffers. `from_buffer` calls `PyObject_GetBuffer(PyBUF_SIMPLE)` once and holds the `Py_buffer` until
  deallocation. Accepted: any C-contiguous buffer (`bytes`, `mmap`, `memoryview`, `bytearray`). While a filter exists,
  Python blocks resizing a `bytearray` and closing an `mmap` (`BufferError`, R§12), but in-place writes to a
  `bytearray` or a writable `mmap` are not blocked and would silently change query answers (memory-safe, but
  false negatives are possible). The docs say "do not mutate the buffer"; a read-only source (`bytes`, `mmap.ACCESS_READ`) is the
  recommended path. Writable buffers are not rejected, because the default `mmap` mode is writable.
* Length hints. `__len__` of `keys` is only a hint: it may lie or be astronomically large (`range(2**61)`), so the
  preallocation is capped at 2^20 keys and growth is geometric; a `__len__` that raises `TypeError` means "unsized" and is
  ignored, any other exception (including `KeyboardInterrupt`) propagates. An uncapped `hint * 8` once wrapped to 0 bytes and
  corrupted the heap (found by the independent review; regression-tested with hints up to 2^63-1).
* `int` subclasses are hashed by value: the bigint encoding runs on the exact `int` (`PyNumber_Index`), so a subclass that
  overrides `bit_length` or `to_bytes` cannot change a key's hash.
* Subinterpreters. The module keeps all state in per-module state and has no mutable globals, but the abi3 wheel targets the
  3.11 limited API, where the `Py_mod_multiple_interpreters` slot does not exist: isolated (own-GIL) subinterpreters on 3.12+
  refuse the import; shared-GIL subinterpreters work (sanitizer-clean). Exception types fall back to `RuntimeError` if a
  filter outlives module teardown.
* GC. A filter made by `from_buffer` holds a reference to the buffer's owner, which could refer back to it, so the type is
  GC-tracked (traverse + clear, like `memoryview`). `tp_clear` frees the core filter *before* releasing the buffer and leaves
  the object in a released state in which every method raises `ValueError`. Found by the leak tests.
* Key arrays. A 1-D C-contiguous buffer of integers (`array.array`, numpy) passed as `keys` is treated as an array of int
  keys and hashed in C without the GIL, with exactly the hashes the same ints would get one by one (uint64 values >= 2^63 take
  the bigint encoding). Non-contiguous, multi-dimensional, big-endian-format or float buffers fall back to plain iteration (and so to
  its errors). `str`, `bytes`, `bytearray` and `memoryview` passed as `keys` raise `TypeError`: iterating one key's characters
  or bytes is almost always a bug. The benchmark reports both batch variants (`docs/benchmark.md`).
* Types. Ship `py.typed` and `_ribbon.pyi` (stubs for the C module), checked with `mypy.stubtest` in CI so the stubs
  cannot drift from the compiled module.

## 7. Python API (immutable filter; names decided by me as best practice, approved 2026-11-12)

```python
class RibbonFilter:
    def __init__(
        self,
        keys: Iterable[Key],
        *,
        fp_bits: int = 8,
        seed: int = 0,
        overhead: float | None = None,
        max_attempts: int = 32,
    ) -> None: ...
    def __contains__(self, key: Key) -> bool: ...
    def contains_many(self, keys: Iterable[Key]) -> list[bool]: ...
    def __len__(self) -> int: ...  # number of keys supplied; duplicates are counted
    def to_bytes(self) -> bytes: ...
    @classmethod
    def from_buffer(cls, buffer: Buffer, *, verify: bool = True) -> RibbonFilter: ...  # zero copy
    @property
    def size_in_bytes(self) -> int: ...  # len(to_bytes()), header included
    @property
    def bits_per_key(self) -> float: ...  # 8 * size_in_bytes / len(self); 0.0 for an empty filter
    @property
    def fp_bits(self) -> int: ...
    def __repr__(self) -> str: ...  # RibbonFilter(keys=1000, fp_bits=8, size_in_bytes=1146)
    def __reduce__(self) -> ...: ...  # pickle and copy work: rebuilt from to_bytes()


Key = bytes | bytearray | memoryview | str | int  # §3.1


class RibbonError(Exception): ...


class ConstructionError(RibbonError): ...  # all attempts failed


class FormatError(RibbonError, ValueError): ...  # bad/truncated/corrupt serialized data
```

Notes: there is no `add` or `remove` (the structure is static); `__contains__` on `bool` is an `int`. `len()` counts
supplied keys because deduplicating would need a sort, so `bits_per_key` includes any duplicates in its denominator.
Builds are deterministic and independent of the order of the keys (the set of pivots and the zero-free-variables
solution are order-invariant; property-tested, including builds that needed retries). Single-pass iterables are
supported (the keys are hashed as they stream into the temporary array; a `__len__` lets the array be preallocated).
`from_buffer` copies nothing and raises `FormatError` (never crashes) on bad input. Errors for wrong key types are
`TypeError`; for out-of-range arguments `ValueError`.

## 8. Packaging

* Python ≥ 3.10; MIT licence, confirmed (`license-files = ["LICENSE", "LICENSES/*"]`); `src/pyribbon/`
  layout and `[tool.ruff]`/`[tool.mypy]` blocks matching your other repos; `dependencies = []`.
* Build backend setuptools ≥ 77; `MANIFEST.in` puts `core/` (including the Makefile and vendored header) in the sdist,
  so `pip install` from the sdist needs only a C compiler.
* Wheels via cibuildwheel 4.x: `skip = "*-win32 *-manylinux_i686 *-musllinux_i686 *t-*"`; macOS `x86_64` (on the Intel runner)
  and `arm64` (on the Apple Silicon runner, cibuildwheel's default `auto` per runner);
  Windows `AMD64` only (ARM64 is untested); manylinux_2_28 and musllinux_1_2. Result per platform:
  a `cp310` wheel and a `cp311-abi3` wheel (R§12). Wheel tests run `pytest` against the installed wheel. Sanitizer
  builds run as a separate CI job on a plain runner, outside cibuildwheel. Verified in CI on 2026-11-12: the wheels build and pass the
  test suite on Linux x86-64 and ARM (manylinux_2_28 and musllinux_1_2), macOS Intel and Apple silicon, and Windows x64.
* Releases: `release.yml` runs the full tests, builds the sdist and the wheels, and publishes to PyPI (secret
  `PYPI_API_TOKEN`) and to GitHub releases when a `v*` tag is pushed. Only the `publish` job can publish, and it runs only for a
  push event on a `v*` tag; a manual run is a dry run, even from a tag. `tests/test_release_workflow.py` enforces that and
  checks that no other workflow can publish. No tag has been pushed and nothing is on PyPI.

## 9. Repository layout and `make` targets

```
core/{include,src,tests,tools,fuzz,vendor}   C library, C unit tests, calibration/report tools, loader fuzz harness; own Makefile
src/pyribbon/{__init__.py,_ribbon.c,_ribbon.pyi,py.typed}
tests/ (pytest + hypothesis + spec_reference.py)   examples/ (numbered scripts, run by a test)   benchmarks/ (bench.py, research/)   docs/ (generated results)
Makefile pyproject.toml setup.py MANIFEST.in LICENSE README.md CHANGELOG.md RESEARCH.md DESIGN.md
```

`make`: `venv` · `install-dev` · `test` (C unit + pytest) · `lint` (ruff check + format check) · `docstyle` · `typecheck`
(mypy strict + stubtest) · `check` (lint, docstyle, typecheck, test) · `c-test` · `c-asan` · `c-portable` · `c-fuzz` ·
`ovh-sweep` / `calibrate` (the sizing table) · `fpr-report` / `stats` (measured false-positive rates and failure rates,
`docs/measurements.md`) · `bench` (writes `docs/benchmark.png`, `.md` and `.json`) · `build` (sdist, wheel, `twine check`) · `clean`. Docstring checks use ruff's `D` rules
with `convention = "google"` (the same rules as your `pydocstyle --convention=google`, one tool fewer).

## 10. Testing and evidence plan (maps to your requirements)

All rows are implemented (`tests/`, `core/tests/`, `core/tools/`); results are in `docs/measurements.md` and `docs/benchmark.md`.

| Requirement | How |
|---|---|
| No false negatives | Hypothesis for n from 0 to a few thousand (boundaries 0, 1, 63, 64, 65, 127, 128, 129 forced), all key types, `fp_bits` 1..32, seeds, duplicates; fixed parametrized tests at n = 1e5 and 1e6; C tests with fixed seeds; same keys through `contains` and `contains_many` |
| Measured FPR ≈ 2^-r | for r ∈ {1,4,8,12,16}: ≥ 1e8 disjoint negative probes for r ≥ 8 (≥ 1e7 for r < 8), assert the count lies within 5σ of the binomial mean; test structured keys (sequential ints, short strings, bit patterns) as well as random; report every number |
| Construction behavior | measure failure rate vs `overhead` for n ∈ {1e2..1e7} (thousands of trials at small n), fit and *replace* ε(n) if §2's formula misses its acceptance bound; failure raises `ConstructionError` (forced by `overhead=0.0, max_attempts=1`); duplicates and the empty set |
| Hash and derivation | XXH3 outputs checked against the `xxhash` PyPI package as a test oracle (dev dependency only); known-answer vectors for `H` and `(start, coeff, fp)` committed as the format spec; avalanche test on the derivation words |
| Serialization | round-trip; every truncation length; single-bit flips over the header (must be rejected, by a field rule or the checksum); a differential fuzz of the loader against the independent Python reference (accept/reject decision and error class agree on every mutant); payload flips with `verify=True` (rejected) and `verify=False` (still memory-safe); hand-crafted hostile headers (huge `num_rows`, overflowing sizes); libFuzzer on `rb_from_buffer` + `rb_contains` under ASan/UBSan; the same corpus run under pytest |
| Sanitizers, warnings | ASan/UBSan for the C tests and the extension in a separate CI job; `-Werror` set above; forced `RB_PORTABLE=1` build |
| Memory | build/free and load/free in a loop, assert RSS growth under a threshold; ASan leak check on the C tests |
| Concurrency | threads querying one filter (`contains` and `contains_many`), results compared to a single-thread run; threads building different filters; GIL-release timing check |

## 11. Benchmarks (`make bench` reproduces everything)

* Compare against `pyfusefilter` Xor8, Xor16, Fuse8, Fuse16 (in place of the unusable `pyxorfilter`, R§12) and
  `rbloom` as the Bloom baseline: maintained, native Rust, MIT, abi3 wheels on 3.10-3.14, a settable FPR and a readable
  size. A pure-Python Bloom would be a straw man (1.5-13 µs/probe measured). `fastbloom-rs` is an optional second Bloom
  because it alone has a batch query.
* Same keys, same measured FPR: each filter is sized for the same target, then its FPR is *measured* with the same
  negative probes and bits/key is taken at the measured FPR (and reported with it, since fingerprint widths are
  discrete: 8 vs 16 bits, and Bloom is continuous).
* Metrics: bits/key at matched measured FPR; build time; single-query latency; batch throughput; n ∈ {1e3, 1e4, 1e5,
  1e6, 1e7}.
* Method: print CPU, OS, Python, compiler and flags; pin the process to a core; report median and spread over
  ≥ 7 runs; keys pre-generated, so key creation is outside the timed region.
* Fairness caveats (written into the output): `pyfusefilter` hashes keys in Python (`str()` + xxhash) per call and
  has no batch query, so its latency includes that cost (reported both as shipped and, where possible, with the
  per-key Python hashing separated); `rbloom` needs an explicit `hash_func` (ints hash to themselves, `bytes` are
  salted per process); the box runs a `powersave` governor, so absolute numbers are comparable between libraries within
  one run but not across machines.
* Where I expect to lose (to be confirmed or refuted by the data): build time against fuse and Bloom, and
  space against Fuse at n ≥ 1e6 (§1). The README's comparison table will be generated from the benchmark output.

## 12. CI quality gates

Lint (ruff), strict mypy plus stubtest on the typed surface, Google-style docstring checks, pytest on 3.10 to 3.14,
Windows and macOS test jobs, a sanitizer job (ASan + UBSan, C and extension), a C-warnings-as-errors job (`-Werror`, gcc and
clang, forced portable fallback), a loader fuzz job (libFuzzer where available), an sdist-builds-with-plain-cc job, a
cibuildwheel job (build and test, no upload), a benchmark smoke run (`--quick`), and a weekly job for the slow statistical tests. Existing conventions kept: actions/checkout and setup-python, `permissions:
contents: read`.

## 13. Roadmap (not v0.1)

1. w = 128 (two-word core) and/or hard sharding, to flatten the overhead growth at large n (§1), with per-shard
   retry and bounded temporary memory. First roadmap item because it is the main reason to prefer ribbon over fuse at scale.
2. Homogeneous variant (no failure, FP caveats, R§2); fractional `fp_bits` (floor/ceil columns); smash for small `m`.
3. BuRR (0.06-1.4% overhead, but bucket sort, rollback, per-bucket thresholds and 4-layer recursion) and Balanced.
4. SIMD queries (AVX512 POPCNT / 8-bit interleaving), parallel build (bump `w` positions per
   block to cut the system into independent blocks, R§7).
5. Free-threaded wheels and testing (3.14t, 3.15t); abi3t once 3.15 is the floor (also enables isolated subinterpreters); 32-bit and big-endian CI; `bytearray`-safe loading; `memoryview(filter)` zero-copy export.
6. Cache effect of sorted vs random insertion for standard ribbon (not measured in the papers, R§4).

## 14. Risks and open questions

* The sizing table is measured on the real core up to 2^24 slots (n ≈ 1.4e7); above that it is extrapolated at the measured
  slope and unmeasured. The retry-with-growth rule limits the damage, though it does not bound the speed.
* XXH3 is vendored from a 7.5k-line header. Its stability promise and test vectors are taken on trust, and the header has not been audited.
* Build memory: the banding array takes 16 bytes/slot (about 18 bytes/key at the w=64 overhead) plus 8 bytes/key for `H`,
  roughly 26 bytes/key, about 2.6 GB at `n = 1e8`, until sharding exists.
* Never built or run: 32-bit and big-endian machines, Windows ARM, and free-threaded CPython. The local machine has no clang, so
  the libFuzzer build is exercised only in CI; the built-in mutator runs the same harness locally. Windows, macOS, the
  manylinux/musllinux wheels and cibuildwheel itself were first exercised by the CI runs on 2026-11-12, which found and
  fixed four problems (see the commit history).
* An independent review of the C core and the extension found one high-severity extension bug (an overflowing length-hint
  preallocation) and several lower-severity items; all actionable ones are fixed and regression-tested (§6).
* I read RocksDB-derived code through research notes; the implementation derives every step from [R]/[B] (R§9, R§10),
  uses no RocksDB constants and no pleat/ribbonGo test vectors, and cites its sources in code comments.
* Patents on ribbon filters were not searched (R§9).

## 15. Decisions (resolved 2026-11-12)

1. Name `pyribbon`: kept (free on PyPI on 2026-11-12; re-check before any upload).
2. Licence: MIT, plus the BSD-2 xxHash notice for the vendored hash.
3. Public API and names (§7): left to me, "use best practice". Choices: `RibbonFilter`, keyword-only options, `list[bool]`
   from `contains_many`, `TypeError` for unsupported key types (never a silent `False`), `FormatError` that is also a
   `ValueError`, `__repr__`, `__reduce__` so pickle, `copy` and multiprocessing work.
4. Width: w = 64, decided by the width study (§1). w = 128 and sharding lead the roadmap.
5. Python 3.10: kept, decided by the download shares (§6).
6. Benchmark `pyfusefilter` instead of `pyxorfilter`: yes (§0, §11).
