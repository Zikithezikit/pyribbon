# The C library

This directory is the C11 core of pyribbon. It builds and tests without Python. It implements a standard ribbon filter
(width 64) behind one header, `include/ribbon.h`: you give it a set of 64-bit key hashes, it builds a static filter that
answers "possibly present" or "definitely absent", and it can write the filter to a buffer and read it back without
copying. A key that was added is always found. A key that was not added is found with probability about
`2^-fp_bits`, where `fp_bits` is 1 to 32 (default 8). The filter cannot be changed after it is built.

The library has no dependencies besides the vendored `xxhash.h`, no global state, and does not allocate while querying.
The Python package is a thin layer over these same files.

## Build and test

From the repository root, or from `core/` without the `-C core`:

```bash
make -C core test       # unit tests, warnings as errors
make -C core example    # build and run examples/basic.c
make -C core asan       # tests and the example under AddressSanitizer and UBSan
make -C core portable   # tests with the portable bit-operation fallbacks forced
```

The Makefile compiles with `-std=c11 -Wall -Wextra -Wconversion -Wshadow -Wcast-align -Wstrict-prototypes
-Wmissing-prototypes -Werror`. CI runs `test`, `portable`, `asan` and `example` on Linux with gcc and clang. The same
two source files are compiled into the Python extension on macOS and Windows (MSVC).

## Use it in your own project

Compile two source files and put two directories on the include path:

```bash
cc -std=c11 -O2 -Icore/include -isystem core/vendor -c core/src/ribbon.c core/src/rb_hash.c
```

| What | Why |
|---|---|
| `core/src/ribbon.c`, `core/src/rb_hash.c` | the whole library |
| `-Icore/include` | `ribbon.h`, the only header your code includes |
| `-isystem core/vendor` (or `-I`) | `xxhash.h`, which `rb_hash.c` includes. `-isystem` keeps its warnings out of a `-Werror` build |
| `core/src/rb_internal.h` | read by both source files from their own directory, so keep it next to them |

No other library is needed: not `-lm`, not a thread library. `-O2` is recommended. `-DRB_PORTABLE=1` replaces the compiler
builtins and intrinsics with plain C, which is slower and gives identical results. `rb_hash.c` sets the xxHash
configuration macros itself, so you do not need to define any.

`ribbon.h` can be included from C or C++ (it has `extern "C"` guards).

## Walk-through

`examples/basic.c` is a complete program that runs every call below and triggers every error. The pieces:

### 1. Hash the keys

The filter works on 64-bit hashes, not on keys. Hash each key once:

```c
uint64_t h1 = rb_hash_bytes("apple", 5, seed, RB_KEY_STR);
uint64_t h2 = rb_hash_i64(-7, seed);
```

`rb_hash_bytes` takes a pointer, a length and a kind (`RB_KEY_BYTES`, `RB_KEY_STR` or `RB_KEY_BIGINT`). The kind is part of
the hash, so the same bytes as `RB_KEY_BYTES` and as `RB_KEY_STR` are two different keys. `rb_hash_i64` takes an integer
in the `int64_t` range. The seed is any `uint64_t`. Use the same seed when you hash the keys you query that you used
when you hashed the keys you built from, and pass that seed in `rb_params` too: `rb_build` only stores it, it does not
re-hash anything. The mapping from a key to its hash is hash id 1 and is specified in `DESIGN.md`, section 3.1. The
Python package writes and reads the same format, so a filter built there loads here when the keys are hashed this way.

### 2. Build

```c
rb_params params = rb_params_default();   /* fp_bits 8, 32 attempts, automatic overhead, seed 0 */
params.fp_bits = 10;
params.seed = seed;
rb_filter *f;
rb_build_info info;
rb_status st = rb_build(hashes, n, &params, &f, &info);
```

`hashes` is an array of `n` hashes. Duplicates are allowed and cost nothing. `params` and `info` may be NULL. `n == 0`
gives a valid empty filter that contains nothing. The array is only read during the call. If construction fails the
library retries with a new internal salt, and from the third attempt with a larger table, up to `max_attempts`. `info`
reports how many attempts were used and the row count. On any failure `f` is NULL.

### 3. Query

```c
int maybe = rb_contains(f, h1);                 /* 1: possibly present, 0: definitely absent */
rb_contains_many(f, hashes, n, out);            /* out[i] is 0 or 1; out has room for n bytes */
```

`rb_contains_many` gives the same answers as a loop of `rb_contains`. It overlaps the memory reads of neighbouring
queries, which helps when the filter does not fit in the cache.

### 4. Serialize

```c
size_t size = rb_serialized_size(f);
uint8_t *buf = malloc(size);
rb_status st = rb_serialize(f, buf, size);
```

The size is known in advance: a 64-byte header plus the payload. `rb_serialize` returns `RB_E_INVALID_ARG` and writes
nothing if `capacity` is smaller. The buffer needs no alignment. The format is specified in `DESIGN.md`, section 5; it is
little-endian, has a magic number and two checksums, and the same bytes come out on every platform for the same hashes and
parameters.

### 5. Load without copying

```c
rb_filter *g;
rb_status st = rb_from_buffer(buf, size, 1, &g);
```

`rb_from_buffer` validates the header and then uses `buf` as the filter's payload. Nothing is copied, so a memory-mapped
file costs no memory beyond the pages you touch. The last argument chooses whether to verify the payload checksum. With 1
it reads every byte once and returns `RB_E_CHECKSUM` for a damaged payload. With 0 only the header is checked, which is
O(1) and keeps a mapped file lazy; a damaged payload then loads and can only make query answers wrong. It cannot make the
library read outside `[buf, buf + len)`: the input is treated as untrusted either way. The header checksum, the length
checks and every other rule are always applied.

`len` must be exactly the serialized size. A longer buffer is `RB_E_FORMAT`, so pass a slice when you store a filter
inside a larger file.

### Ownership and lifetime

| Object | Who owns what |
|---|---|
| filter from `rb_build` | owns its payload. Release it with `rb_free`. |
| filter from `rb_from_buffer` | owns only a small handle. The payload is your `buf`. |
| `buf` for `rb_from_buffer` | yours. Keep it valid and unmodified until `rb_free(filter)` has returned. Free it after the filter. |
| `hashes` for `rb_build` | yours. The library does not keep it. |

Modifying `buf` while a filter views it is a data race with every query, and unmapping or freeing it first is
use after free. `rb_free(NULL)` is allowed, so one cleanup path can free everything.

### Errors

Every function that can fail returns an `rb_status`, and `rb_strerror(status)` gives a static description to print. On
failure the output pointer (`*out`) is NULL, so there is nothing to free.

| Status | When |
|---|---|
| `RB_OK` | success |
| `RB_E_INVALID_ARG` | a NULL pointer, `fp_bits` outside 1 to 32, `max_attempts` above 255, `overhead` above 4 or NaN, or a destination buffer that is too small |
| `RB_E_NOMEM` | an allocation failed |
| `RB_E_CONSTRUCT` | every attempt failed to find a solution. Retry with another seed or a larger `overhead` |
| `RB_E_TOO_LARGE` | more than `RB_MAX_KEYS` (2^38) keys, or a size beyond the supported range |
| `RB_E_TRUNCATED` | the buffer is shorter than the header or than the payload the header declares |
| `RB_E_MAGIC` | the first 8 bytes are not the magic number: not a pyribbon filter |
| `RB_E_VERSION` | a format version this library does not read |
| `RB_E_FORMAT` | an inconsistent or unsupported header field, or trailing bytes after the payload |
| `RB_E_CHECKSUM` | the header checksum does not match, or the payload checksum does not match when it was requested |

The loader checks its rules in a fixed order and reports the first one that fails. `DESIGN.md`, section 5, lists the
order. The query functions have no failure mode, and passing them a NULL filter is not allowed.

### Accessors

`rb_num_keys` (keys given to `rb_build`, duplicates counted), `rb_num_rows`, `rb_fp_bits` and `rb_seed` read the stored
parameters of a built or loaded filter. `rb_default_overhead(n)` gives the table overhead the library picks for `n` keys.

## Thread safety

A filter does not change after `rb_build` or `rb_from_buffer` returns, and the library has no global state. Any number of
threads may call `rb_contains`, `rb_contains_many`, `rb_serialize` and the accessors on the same filter at the same time
without locks. Separate calls to `rb_build` and the hash functions may also run in parallel. You must not free a filter
while another thread is still using it, and you must not write to a buffer that a loaded filter views.

## What it costs

Space. A filter has `rows` rows, about `n * (1 + overhead)`, rounded up to a multiple of 64 with a minimum of 128. The
serialized size is `64 + rows / 64 * fp_bits * 8` bytes, which is about `fp_bits * (1 + overhead)` bits per key plus the
header. The default overhead is between 5% and 16% for up to 2^24 keys and grows slowly above that (`rb_default_overhead`, `DESIGN.md` section 2). At 1,000,000 keys
and `fp_bits` 8 that is 8.99 bits per key including the header, against 11.5 for a Bloom filter at the same false-positive
rate.

Memory while building. You supply the `hashes` array, 8 bytes per key. The builder allocates a temporary table of 16
bytes per row, plus the payload that becomes the filter. The table is freed before `rb_build` returns. Loading a filter
with `rb_from_buffer` allocates only a small fixed handle.

Time. Building does one pass over the keys per attempt, and the expected number of attempts is about 1.03 at the default
overhead. Construction is dominated by random memory accesses, which the library batches and prefetches. A query derives a start row, a
coefficient word and a fingerprint from the master hash with a few multiplications, then reads `fp_bits` words from each of two neighbouring 64-row blocks,
stopping at the first column that disagrees, which is about two columns for a key that is not present. Measured build and
query times against other libraries are in `docs/benchmark.md`.

## Where the details are

`DESIGN.md` section 3 specifies how a key becomes a 64-bit hash and how that hash becomes ribbon coordinates, section 5
specifies the serialized format, and section 4 describes this library. The format version 1 and hash id 1 are frozen. The
file layout of this directory:

| Path | Contents |
|---|---|
| `include/ribbon.h` | the public API, with a comment on every function |
| `src/` | the implementation (`ribbon.c`, `rb_hash.c`) and its internal header |
| `vendor/` | xxHash v0.8.4, see `vendor/README.md` |
| `examples/basic.c` | the complete example |
| `tests/` | unit tests and the test vectors that pin the format |
| `fuzz/` | the loader fuzz harness (`make -C core fuzz`) |
| `tools/` | calibration and measurement programs for the overhead table |
