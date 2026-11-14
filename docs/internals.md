# Internals

How pyribbon is built, as the code does it today. The sections are numbered because comments in the source point at them. It
covers the algorithm and its parameters, how a key becomes a hash, the C core, the exact byte layout of a saved filter, the
Python extension, the tests, and what is still missing. The literature behind it is in [research.md](research.md), and `R§n`
below means section n of that file.

## 1. Overview

pyribbon is a standard ribbon filter with width 64, a fingerprint of 1 to 32 bits per key, and the interleaved column layout.

- **Standard, not homogeneous.** The fingerprint of a key is independent of its equations, so the false-positive rate is exactly
  `2**-fp_bits`. That is what the statistical tests measure, and it is what makes "retry with a new seed" a sound way to handle
  a build that cannot be solved (R§2, R§5). A homogeneous ribbon never fails to build, but its false-positive rate can exceed
  `2**-fp_bits` and is hard to check on small sets.
- **Width 64.** A row of the system is one machine word, so shifts and parity are single instructions. A study with a simulation
  of the paper's elimination (`benchmarks/research/`, an i7-7700) measured the overhead needed for a 95% chance that one attempt
  succeeds:

  | slots | 2^10 | 2^14 | 2^17 | 2^20 | 2^22 |
  |---|---:|---:|---:|---:|---:|
  | width 64 | 4.7% | 6.9% | 9.6% | 11.5% | 12.7% |
  | width 128 | 2.2% | 2.7% | 3.7% | 4.6% | 5.5% |

  Width 128 would save about 6% of the bits per key, but it needs a two-word core with 128-bit shifts in the query, and its
  insertion was 2 to 3 times slower in a first implementation. The file format stores the width, so adding it later does not
  break the format.
- **Same bytes everywhere.** The same keys, parameters and seed give the same serialized bytes on every platform. Sizing uses
  integer arithmetic only, and a pure-Python implementation of the format (`tests/spec_reference.py`) produces the same
  bytes as the C core in the tests.

## 2. Parameters

| Parameter | Default | Range | Notes |
|---|---|---|---|
| width | 64 | fixed | Stored in the header as `width_log2`. |
| `fp_bits` (r) | 8 | 1 to 32 | The false-positive rate is about `2**-r`. 8 matches Xor8 and Fuse8. Up to 32 keeps a row's result in a `uint32_t`. |
| rows (m) | see below | multiple of 64, at least 128 | The interleaved layout needs a multiple of 64. At least 128 rows means every start position has a block after it. |
| `overhead` | from a table | 0 to 4 | Extra rows as a fraction of the key count. |
| `max_attempts` | 32 | 1 to 255 | A failed attempt is retried; see below. |
| `seed` | 0 | 0 to 2^64 - 1 | Stored in the header. Different seeds give independent filters. |

**Rows.** `m = roundup64(ceil(n * (1 + overhead)))`, and never fewer than 128. The default overhead comes from a table measured
on the real core (`make calibrate`, `core/tools/overhead_table.py`): for each size from 2^7 to 2^24 keys, the overhead at which
97% of attempts succeed, so the expected number of attempts is about 1.03. The table is stored in parts per million and
interpolated linearly in `n` with integer division. Sample points are 6.6% at 2^7, 5.3% at 2^10, 9.5% at 2^16, 12.5% at 2^20
and 15.5% at 2^24. Above 2^24 the overhead grows by 0.7 percentage points per doubling. That part is extrapolated from the
measured slope and has not been measured. A caller's `overhead` is rounded once to whole parts per million.

**Integer sizing.** The row count is `ceil(n * (1e6 + ppm) / 1e6)`, so no floating-point contraction on any compiler can change
it. `n` is at most `RB_MAX_KEYS = 2^38` and the overhead at most 4e6 ppm, which keeps the product below 2^61. An initial row count
of 2^39 or more is refused with `RB_E_TOO_LARGE`, so growth during retries stays within `RB_MAX_ROWS = 2^40`, the same limit
the loader enforces.

**Retries.** Every attempt uses a new salt (section 3.2). From the third attempt the table also grows, by a factor of
65/64 (`(w + 1) / w`) and by at least one block of 64 rows. Reseeding does most of the work. Growth guarantees that the build ends even if the
table is too tight for some `n`. If all attempts fail, the build raises `ConstructionError`. A filter that did not pass the
elimination is never returned.

**Validation.** `make ovh-sweep` builds with the real library, with an independent key range for every trial (4000 trials up to
1000 keys, 1500 up to 10,000, 300 at 100,000, 60 at a million). The per-attempt failure rate at the default overhead is 0.0% at
n = 100, 0.85% at 300, 0.10% at 1000, 1.8% at 3000, 2.1% at 10,000 and 3.3% at 100,000 and at a million. The mean number of
attempts stays at or below 1.033. At `fp_bits=8` the payload takes 8.70, 8.60, 8.79 and 8.99 bits per key at 1000, 10,000,
100,000 and a million keys. The 64-byte header adds `512 / n` bits per key, and tiny sets are padded to 128 rows.

An empty key set gives a valid filter with `num_rows = 0`: just the header, and every query answers no.

## 3. Hashing

Python's built-in `hash()` is never used, because it differs between processes and would break every saved filter.

### 3.1 From a key to the master hash H

This is hash id 1. Any change to it needs a new hash id.

| Key | Rule |
|---|---|
| `bytes`, `bytearray`, `memoryview` | `h0 = XXH3_64bits(payload bytes)`, with seed 0 and the default secret. A `memoryview` counts as raw bytes whatever its format. |
| `str` | The UTF-8 bytes (strict: a lone surrogate raises `UnicodeEncodeError`). `h0 = XXH3_64bits(bytes) ^ TAG_STR`. |
| `int` in `[-2^63, 2^63)` (numpy integers too) | `h0 = (uint64)value ^ TAG_INT`. This is the two's complement of the value, so no byte order is involved. |
| any other `int` | The little-endian two's complement of exactly `value.bit_length() // 8 + 1` bytes, which is one canonical encoding per value. `h0 = XXH3_64bits(bytes) ^ TAG_BIGINT`. |
| anything else | `TypeError`. There is no implicit `str()`: `51` and `"51"` are different keys, and floats are not keys. |

The tags are the first words of the SHA-512 initial values: `TAG_STR = 0x6a09e667f3bcc908`, `TAG_INT = 0xbb67ae8584caa73b`,
`TAG_BIGINT = 0x3c6ef372fe94f82b`. The tag for bytes is 0. That is why `b"a"`, `"a"` and `97` stay three different keys.

Then `H = mix64(h0 + mix64(seed + GAMMA))`, where `GAMMA = 0x9e3779b97f4a7c15` and `mix64` is the SplitMix64 finalizer:

```
z = (z ^ z >> 30) * 0xbf58476d1ce4e5b9
z = (z ^ z >> 27) * 0x94d049bb133111eb
return z ^ z >> 31
```

The seed is mixed first and added. An earlier version XORed the seed into `h0`. For dense integer keys that made nearby seeds
produce almost the same set of hashes (`{i ^ seed}`), so `seed=1` rebuilt nearly the same filter as `seed=0`. A random 64-bit
offset makes every seed its own hash universe.

XXH3-64 is vendored as `core/vendor/xxhash.h` (BSD 2-Clause, notice shipped in the sdist and wheels), in scalar mode with
`XXH_FORCE_MEMORY_ACCESS=0`. It was chosen because it has a written promise that its output stays stable, a specification, test
vectors in its repository, and output that does not depend on byte order (R§11). The int path is defined on the numeric value and
`mix64` is a bijection, so two different int64 keys never share an `H`. Two different bytes or `str` keys share one with a
probability of about `n**2 / 2**65`. Like a duplicate key, they produce identical equations, which the elimination treats as
redundant, so the cost is at most one extra false positive.

### 3.2 From H to the ribbon coordinates

Each key gets a start row, a coefficient word and a fingerprint from three independent 64-bit words:

```
salt  = mix64((attempt + 1) * GAMMA)         # the attempt index is stored in the header
S     = H ^ salt
z0 = mix64(S + 1*GAMMA)   z1 = mix64(S + 2*GAMMA)   z2 = mix64(S + 3*GAMMA)
start = mulhi64(z0, m - 63)                  # floor(z0 * (m - w + 1) / 2^64), in [0, m - 64]
coeff = z1 | 1                               # bit 0 is always set: the equation includes its own start row
fp    = z2 >> (64 - r)                       # the top r bits
```

Stretching one 64-bit hash into all three values with a multiplication, as some designs do, has no avalanche. Independent words avoid
that, and for a retry only this cheap step is repeated. The seed enters before this step, when `H` is already fully mixed, so
the equations of different attempts are not correlated. XXH3's own seed argument is not used. The builder hashes every key
once into an array `H[n]`, which is 8 bytes per key of temporary memory.

## 4. The C core

C11, no dependency other than the vendored header, no global state, no atomics, no VLAs, and no allocation inside a query. It builds
and tests without Python (`make -C core test`), and [core/README.md](../core/README.md) explains the API. It compiles with
`-std=c11 -Wall -Wextra -Wconversion -Wshadow -Wcast-align -Wstrict-prototypes -Wmissing-prototypes -Werror`.

The core takes key hashes as input. Hashing is a separate step, so the Python layer can hash Python objects itself and call the
core on a `uint64_t` array. A loaded `rb_filter` copies every header field into its own struct and never reads the header from the
buffer again. Only payload words are read, at offsets worked out from the validated struct. A buffer that changes after
loading can give wrong answers but cannot cause a read outside it.

**Building.** The system is one array of 16-byte slots, `{uint64_t coeff; uint32_t res}`, so one insertion touches one cache line. An
empty slot has `coeff == 0`. Keys go in chunks of 16: the equations of a chunk are derived and their slots prefetched first, then
the keys are inserted in order. For each key:

```
i = start; c = coeff; b = fp
loop:
    if slot i is empty: store (c, b); done
    c ^= slot[i].coeff; b ^= slot[i].res
    if c == 0: redundant if b == 0, otherwise this attempt fails
    j = ctz(c); i += j; c >>= j
```

`c` has bit 0 set before the XOR and is not zero before `ctz`, so `1 <= j <= 63` and no shift reaches the width of the type.
Back-substitution then runs from the last row to the first, keeps one 64-bit running word per column, and writes the interleaved
layout directly, one block of `r` words per 64 rows.

**Insertion order.** The serialized bytes do not depend on the order in which keys are inserted. The set of pivots and the
solution with all free variables zero are the same for every order, and `tests/test_property.py` checks it. For tables of at
least 2^18 rows, `rb_build` uses that: it first groups the keys by start row with a counting sort on `start >> shift` (at most 1024
buckets of at least 4096 rows, which is 64 KiB of slots) and then inserts bucket by bucket. The slots of a bucket stay in cache and
the elimination walks memory in increasing order. The cost is one more 8-byte word per key and two extra passes over the hashes.
Measured with `core/tools/bench_build.c` and `core/tools/ab_build.sh` (old and new binaries alternating, pinned to one CPU,
an i7-7700 that was shared, so only the ratio means anything), the C core builds 19 to 24% faster at a million and ten million keys,
and the speed is unchanged within 2% from 1000 to 100,000 keys. These were tried and did not help: bucketing below 2^18 rows (7 to
10% slower at 10,000 to 100,000 keys), inserting several keys in lock step to hide the loads, fixing `r` at compile time in
the back-substitution, prefetching its slot stream, and other bucket sizes. `rb_build_ex` is an internal entry point that forces either
order, and `core/tests/test_core.c` compares the two on many sizes, widths, retries and duplicate keys.

**Querying.** With `s = start`, `blk = s >> 6` and `off = s & 63`, column `j` of the answer is

```
parity(W[blk][j] & (c << off)) ^ parity(W[blk + 1][j] & (c >> (64 - off)))
```

The second term covers the bits that spill into the next block, and it is skipped when `off == 0` because a shift by 64 is undefined
behaviour. A query stops at the first column that differs from the fingerprint. The last start row is `m - 64`, so `off == 0` there and
the block `blk + 1` always exists when it is needed: nothing is read past the payload. `rb_contains_many` derives and prefetches
chunks of 16 keys, the same way as the build.

**Portable bit operations.** They live in one internal header: `ctz64`, `parity64`, `mulhi64`, `load_le64` and `store_le64`. The
compilers' builtins are used on GCC and Clang. MSVC uses `_BitScanForward64` and `_umul128` (or `__umulh` on ARM64); parity is folded
with XORs, so no POPCNT is needed. Pure-C fallbacks exist for everything and are tested on Linux by forcing `-DRB_PORTABLE=1`. All
integers are `uint64_t` or `uint32_t`, never `long`, which is 32 bits on 64-bit Windows. `load_le64` is a `memcpy` plus a byte swap on
big-endian hosts, so the code assumes no alignment and no byte order.

## 5. File format, version 1

Everything is little-endian and every field is explicit.

| Offset | Size | Field | Notes |
|---:|---:|---|---|
| 0 | 8 | magic | `"PYRIBBON"` |
| 8 | 2 | `version` | 1. A reader rejects any other version. |
| 10 | 2 | `header_size` | 64 |
| 12 | 1 | `width_log2` | 6 |
| 13 | 1 | `fp_bits` | 1 to 32 |
| 14 | 1 | `hash_id` | 1 (section 3) |
| 15 | 1 | `flags` | 0. Reserved bits must be zero. |
| 16 | 8 | `num_keys` | Keys supplied, duplicates included. 0 exactly when `num_rows` is 0, and never above `num_rows`. |
| 24 | 8 | `num_rows` | 0, or a multiple of 64 from 128 to 2^40. |
| 32 | 8 | `seed` | The seed the caller gave. |
| 40 | 4 | `attempt` | The index of the attempt that succeeded. |
| 44 | 4 | reserved | 0 |
| 48 | 8 | `payload_xxh3` | XXH3-64 of the payload. |
| 56 | 8 | `header_xxh3` | XXH3-64 of bytes 0 to 55. |
| 64 | `num_rows / 64 * r * 8` | payload | For block `k`, `r` words. Word `j` holds column `j` for rows `64k` to `64k + 63`, with row `64k + i` at bit `i`. |

**Loader rules.** The input is untrusted. The rules run in this order, and the first one that fails decides the error
(`tests/spec_reference.py` follows the same order):

1. The buffer holds at least 64 bytes, otherwise truncated.
2. The magic is right (magic error), the version is 1 (version error), and `header_size` is 64 (format error).
3. `header_xxh3` matches the first 56 bytes (checksum error).
4. `width_log2` is 6, `hash_id` is 1, `flags` and the reserved field are 0, and `fp_bits` is 1 to 32 (format error).
5. `num_rows` is 0, or a multiple of 64 from 128 to 2^40 (format error).
6. `num_keys` is 0 exactly when `num_rows` is 0, and is at most `num_rows` (format error). That keeps `len()` meaningful for a loaded filter.
7. The payload length is `num_rows / 64 * r * 8`, at most 2^42, so it cannot overflow. A shorter buffer is truncated, and a longer one is a format error. To embed a filter in a larger buffer, slice a `memoryview`.
8. If the payload is being verified, `payload_xxh3` matches (checksum error). This reads every byte once.

`from_buffer(verify=False)` skips only rule 8, which keeps a memory-mapped filter lazy. Rules 1 to 7 take constant time and always
run, so even the unverified path cannot read out of bounds. The loader copies the 64 header bytes into a local buffer and parses
only that copy, so a writer changing the buffer at the same moment cannot make validation and use see different values. Damage to
the payload under `verify=False` can only change query answers, and `attempt` is taken as it stands. The checksums catch accidents
and are not a MAC, so they do not stop tampering. A file that another process truncates while it is memory-mapped faults on access,
which no library can prevent.

A loaded filter keeps a pointer into the caller's buffer. The payload is read with `load_le64`, so the same file works on
little-endian and big-endian machines without a conversion step.

## 6. The Python extension

A thin hand-written CPython extension (`src/pyribbon/_ribbon.c`) with no runtime dependency. It was chosen over Cython and cffi
for speed (a trivial call costs 32 to 34 ns, against 41 for Cython and 175 to 267 for cffi, R§12), and because an sdist then builds
with only a C compiler.

**Builds and wheels.**
- For CPython 3.11 and newer it uses the limited API, so one `cp311-abi3` wheel per platform covers them all.
- Python 3.10 gets its own wheel from the same source, because `Py_buffer` joined the stable ABI in 3.11. 3.10 is past end of
  life, but it was still 12.8% of numpy's downloads in the month before 2026-11-12, so it stays. Dropping it later removes one wheel and a few lines in `setup.py`.
- Free-threaded CPython (3.14t, 3.15t) has no stable ABI before 3.15, so those wheels use the full API.
- The type ships stubs (`_ribbon.pyi`) and `py.typed`, and CI checks the stubs against the compiled module with `mypy.stubtest`.

**The GIL.**
- `key in f` never releases it: releasing and taking it back costs more than the 30 ns of work.
- A build hashes keys with the GIL held, because it touches Python objects, and releases it for the elimination and the
  back-substitution, which are pure C and can take seconds. An integer buffer is hashed without the GIL.
- `contains_many` hashes into a temporary array with the GIL held and releases it for the probing when the batch has at least 1024 keys. That
  threshold has not been tuned. Between the release and acquire macros the code touches no Python object, reference count or error state.
- On free-threaded builds the module declares `Py_mod_gil = Py_MOD_GIL_NOT_USED`, only under `#if defined(Py_GIL_DISABLED) &&
  defined(Py_mod_gil)`. Without it, importing the extension would turn the GIL back on.

**Threads.** A filter is immutable: no field is written after it is built, there is no lazy state and the core has no globals, so any number
of threads can query one filter. Builds are independent of each other. A method holds a reference to the filter for the whole call,
including the part without the GIL, so dropping the last reference cannot free a filter in the middle of a query. Without the GIL, the
only writes to a filter object happen in the constructor, in `from_buffer`, and in `tp_clear` and `tp_dealloc`, which run only when
no other reference exists. Module state is written only when the module is set up and torn down. Key and buffer handling uses
only public functions that CPython makes safe for free threading. The one race left is the documented one: writing to a buffer
that a filter views. `tests/test_concurrency.py` and `tests/test_free_threaded.py` exercise all of this.

**Buffers.** `from_buffer` calls `PyObject_GetBuffer(PyBUF_SIMPLE)` once and keeps the view until the filter is freed. Any C-contiguous
buffer works: `bytes`, `mmap`, `memoryview`, `bytearray`. While the filter exists Python refuses to resize a `bytearray` or close an
`mmap` (`BufferError`). It does not stop writes into a `bytearray` or a writable `mmap`, which are memory-safe but can silently
change answers and even cause false negatives. The docs say not to modify the buffer, and a read-only source is the recommended
one. Writable buffers are accepted because the default `mmap` mode is writable.

**Keys.**
- A one-dimensional C-contiguous integer buffer (`array.array`, numpy) passed as `keys` is hashed in C without the GIL, with exactly the
  hashes the same ints would get one at a time. A `uint64` value of 2^63 or more takes the big-integer encoding.
- Non-contiguous, multi-dimensional, big-endian-format and float buffers fall back to plain iteration, and so to its errors.
- A lone `str`, `bytes`, `bytearray` or `memoryview` passed as `keys` raises `TypeError`, because iterating its characters or bytes is almost always a mistake.
- An `int` subclass is hashed by its value: the big-integer encoding runs on the exact int, so a subclass that overrides `bit_length` or
  `to_bytes` cannot change a key's hash.

**Length hints.** `len(keys)` is only a hint. It can lie or be huge (`range(2**61)`), so preallocation is capped at 2^20 keys and the array
grows geometrically. A `__len__` that raises `TypeError` means "unsized" and is ignored. Any other exception, `KeyboardInterrupt` included, propagates.
An uncapped `hint * 8` once wrapped to zero bytes and corrupted the heap, which an independent review found. It is regression-tested with hints up to
2^63 - 1.

**Garbage collection.** A filter made by `from_buffer` holds a reference to the buffer's owner, which could refer back to it, so the type is
tracked by the collector (traverse and clear, like `memoryview`). `tp_clear` frees the core filter before it releases the buffer and leaves the
object in a released state where every method raises `ValueError`.

**Subinterpreters.** The module keeps all its state in per-module state and has no mutable globals. The abi3 wheel targets the 3.11 limited
API, which has no `Py_mod_multiple_interpreters` slot, so an isolated subinterpreter with its own GIL (3.12 and newer) refuses the import.
Subinterpreters that share the GIL work. If a filter outlives the module, the exception types fall back to `RuntimeError`.

**Behaviour that follows from the design.**
- There is no `add` or `remove`: the structure is static.
- `len()` counts the keys supplied, duplicates included, because removing duplicates would need a sort. `bits_per_key` therefore counts them in its denominator.
- Builds are deterministic and independent of key order, including builds that needed retries.
- Single-pass iterables work: keys are hashed as they stream into the temporary array.
- `repr()` looks like `RibbonFilter(keys=1000, fp_bits=8, size_in_bytes=1146)`. `pickle` and `copy` rebuild the filter from `to_bytes()`.

## 7. Tests and CI

| What | Where |
|---|---|
| The format and the hashing, written independently in Python from the spec | `tests/spec_reference.py`, compared byte for byte with the C core through vectors in `core/tests/vectors.h` and in the Python tests |
| No false negatives, for sizes from 0 up, every key type, every `fp_bits`, duplicates, seeds | `tests/test_property.py` (Hypothesis), `tests/test_filter.py`, `core/tests/test_core.c` |
| The measured false-positive rate matches `2**-fp_bits`, and builds fail at the expected rate | `tests/test_statistics.py` (slow tests, run weekly by `stats.yml`), `make stats`, [measurements.md](measurements.md) |
| The loader on hostile input: every truncation, every header bit flip, crafted sizes, a differential fuzz against the Python reference, libFuzzer under ASan and UBSan | `tests/test_loader.py`, `core/fuzz/` |
| Memory: build and free in a loop, allocation failures | `tests/test_leaks.py`, `tests/test_extension_errors.py`, `core/tests/test_nomem.c` |
| Threads, the GIL, and free-threaded Python | `tests/test_concurrency.py`, `tests/test_free_threaded.py` |
| The docs, examples and release rules | `tests/test_docs.py`, `tests/test_readme.py`, `tests/test_examples.py`, `tests/test_release_workflow.py`, `tests/test_repo_health.py` |

The workflows are `ci.yml` (lint, strict mypy and stubtest, docstring checks, tests on Python 3.10 to 3.14, Windows and macOS builds,
sanitizers, a warnings-as-errors build, loader fuzzing, an sdist build, and a quick benchmark run), `wheels.yml`, `coverage.yml`
(line-coverage gates for the core and the extension), `cross-arch.yml` (s390x, 32-bit x86 and armv7), `free-threaded.yml`, `stats.yml` and
`release.yml`. [CONTRIBUTING.md](../CONTRIBUTING.md) says when each one runs and how a release is made.

## 8. Gaps and what is not built

**Known gaps**
- The sizing table is measured on the real core up to 2^24 slots (about 1.4 million keys). Above that it is extrapolated, and the
  retry-with-growth rule limits the damage without bounding the speed.
- The vendored XXH3 header is trusted. Its stability promise and test vectors are taken as given, and the header has not been audited.
- A build uses about 26 bytes per key temporarily: the 16-byte slots (about 18 bytes per key at the default overhead) and 8 bytes of hashes.
  That is about 2.6 GB at 100 million keys.
- Windows on ARM has never been built. The libFuzzer build runs only in CI. Free-threaded wheels were built only by CI.
- No big-endian or 32-bit wheels are published, though the core tests and the fast Python tests run on those machines in `cross-arch.yml`.
- Patents on ribbon filters were not searched.

**Not built yet**
- A width of 128 and/or sharding, to flatten the growth of the overhead at large sizes. This comes first, because it is the main reason to prefer a ribbon filter over a fuse filter at scale.
- The homogeneous variant, fractional `fp_bits`, and "smash" for small tables.
- BuRR (0.06 to 1.4% overhead, but with bucket sorting, rollback, per-bucket thresholds and four recursion layers) and the balanced variant.
- SIMD queries and a parallel build.
- The stable ABI for free-threaded builds (abi3t) once Python 3.15 is the minimum, which would also allow isolated subinterpreters. Loading from a `bytearray` that may change, and exporting a filter as a `memoryview` without copying.

**Provenance.** The implementation was written from the papers. The RocksDB code was read only through research notes, and every step is derived from the
papers (R§9, R§10). It uses none of RocksDB's constants and none of the pleat or ribbonGo test vectors, and it names its sources in code comments.
