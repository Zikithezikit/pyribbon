# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.2.0] - 2026-11-16

This release adds ribbon width 128. The default is still width 64, so existing code builds the same filters, byte for byte, and
filters saved by 0.1.2 load unchanged.

### Added
- `RibbonFilter(..., width=Width.W128)` builds a ribbon filter of width 128, which needs less spare room in its table: the filter
  is 4% to 8% smaller than at width 64 from 10,000 keys up (8.41 against 8.99 bits per key at a million keys, `fp_bits=8`). A
  build takes 1.2 to 1.5 times as long, a batch query is 10% to 25% slower and one `in` is up to 30% slower at small sizes and
  about 5% slower at a million keys or more. Both widths are in the benchmark tables (`docs/performance.md`).
- `Width`, a new `IntEnum` with the two members `W64` and `W128`, the only values the `width` argument accepts. Anything else
  raises `ValueError`. The default is `Width.W64`.
- `RibbonFilter.width` reads the width a filter was built with, as a `Width`.
- The file format stores width 128 as `width_log2 = 7`, with at least 256 rows. The format version is still 1, so 0.1.2
  rejects a width-128 filter with a `FormatError` rather than misreading it. A filter cannot be converted from one width to
  the other, because it holds no keys: build a new one from the keys.
- C core: `rb_params.width` (an `rb_width_kind`: `RB_WIDTH_64` or `RB_WIDTH_128`), `rb_width()` and `rb_default_overhead_width()`.
  `make -C core calibrate WIDTH=128` measures the default-overhead table, which is measured up to 2^22 slots at this width and
  extrapolated above that.

### Changed
- `repr()` of a filter now includes the width: `RibbonFilter(keys=1000, fp_bits=8, width=64, size_in_bytes=1146)`.
- C core: `rb_params` has a new `width` field, so code compiled against the old header must be rebuilt, and a `rb_params` that
  is not made with `rb_params_default()` must set `width` to `RB_WIDTH_64` or `RB_WIDTH_128` (any other value, 0 included, is
  `RB_E_INVALID_ARG`).
- Width-64 queries are a little faster than in 0.1.2 (about 6% in batches and 1% for one key in the C core, on one machine); builds
  and the bytes written are unchanged.

### Tests
- Both widths run through the C unit tests, the byte-for-byte comparison with the pure-Python reference, the property tests, the
  loader tests, the thread, leak and allocation-failure tests and the fuzz corpus. Width 128 has its own slow statistical tests
  (`tests/test_statistics_wide.py`) that write nothing to `docs/measurements.md`.

### Documentation
- The README shows the pyribbon logo. The logo files are in `docs/img/logo/`: the mark and the lockup as SVG, in colour, ink, white and single-colour versions, a few PNG sizes, and a social preview image. The README uses the colour lockup on a white backing, so it reads on a dark page.
- The API reference, usage guide, limits page and internals describe width 128, the `Width` type and the file format change.
- `examples/08_width.py` compares the two widths, and the benchmarks (`benchmarks/bench.py`, `docs/performance.md`) measure both.

## [0.1.2] - 2026-11-14

The library and the file format are unchanged since 0.1.1. This release is documentation, tests and package metadata.

### Added
- The package metadata carries the free-threading classifier, so the PyPI page shows that free-threaded Python is supported.

### Documentation
- The README is a short front page: install, a quick start, sizes and performance. It links the PyPI page and shows PyPI,
  Python-version and licence badges.
- The rest moved into `docs/`: a usage guide, an API reference, limits, how it works, the full performance tables, and an index
  that links them. `DESIGN.md` is replaced by `docs/internals.md`, which describes the code as it is now: parameters, hashing, the
  C core, the exact file format, the Python extension, the tests and the known gaps. `RESEARCH.md` moved to `docs/research.md`.
- The sizes table covers the whole `fp_bits` range, 1 to 32, in 12 rows, and says why bits per key is a decimal.
- The benchmarks, the measured false-positive rates and the figures are rerun on this version, on an idle machine.

### Tests
- The thread tests no longer depend on timing. The GIL test is skipped on free-threaded builds, which have no GIL, and the stress
  tests keep running until every thread has done its minimum work. The GIL test's threshold is lower, because a loaded runner
  once measured 17% where a build that held the GIL would give about 0%.
- New tests keep the README quick start running, check that every docs link and image points at a file, that the API reference
  names every public member, that every docs file named anywhere in the repository exists, and that every row of the sizes
  table matches a real filter.

## [0.1.1] - 2026-11-13

### Fixed
- On big-endian machines (found on s390x), a 1-, 2- or 4-byte integer buffer such as `array('i')` hashed to a different
  filter than the same ints. Buffers of 8-byte items were unaffected, and so was every little-endian machine.

### Added
- Wheels for the free-threaded builds of CPython (3.14t and 3.15t). The extension declares that it does not need the GIL, so
  importing it no longer turns the GIL back on.
- Documentation for the standalone C library (`core/README.md`), a runnable example (`core/examples/basic.c`, run by
  `make -C core example` and in CI), and complete function comments in `ribbon.h`.
- `SECURITY.md`, issue and pull request templates, Dependabot for GitHub Actions, a pre-commit configuration for ruff and
  `.editorconfig`.

### Changed
- Building a filter of 1e6 keys or more is about 15 to 25% faster. Keys are grouped by start row before insertion, and the
  output is byte-identical.

### Project and CI
- A cross-architecture workflow runs the C core tests and the fast Python tests on s390x (big-endian), 32-bit x86 and armv7.
- `make coverage` (line and branch coverage of the C core and the extension with gcc and gcovr), allocation-failure and
  extension error-path tests, and a Coverage workflow with a line-coverage gate on the core.
- CI and wheel workflows run only for pushes to `main`, tags (through `release.yml`) and pull requests that target `main`; a
  test enforces this for every workflow.
- The GitHub release is its own last job in `release.yml`: it runs only after the PyPI upload succeeded, which itself needs the
  whole pipeline to have passed, and only for a pushed `v*` tag. A failed release can be re-run without touching PyPI.

## [0.1.0] - 2026-11-12

First release.

### Added
- `RibbonFilter`: an immutable standard ribbon filter (width 64, `fp_bits` 1 to 32), built from an iterable of
  `bytes`, `bytearray`, `memoryview`, `str` or `int` keys, or from a 1-D integer buffer (`array.array`, numpy).
- On `RibbonFilter`: `in`, `contains_many`, `len`, `to_bytes`, `size_in_bytes`, `bits_per_key` and `fp_bits`, plus
  zero-copy `from_buffer` (with optional payload verification) and `pickle` and `copy` support. The exceptions are
  `RibbonError`, `ConstructionError` and `FormatError`.
- A versioned, little-endian serialization format with a magic number, a header checksum and a payload checksum. The
  loader treats its input as untrusted.
- A C11 core (`core/`) that builds without Python. It has its own unit tests, portable fallbacks for the bit operations,
  ASan/UBSan runs and a fuzz harness for the loader.
- Seven numbered example scripts in `examples/` (start with `01_quickstart.py`); `make example` runs them and a test checks
  their output.
- A pure-Python reference implementation of the spec (`tests/spec_reference.py`), used as the oracle in tests.
- Property, differential-fuzz, statistical, leak and concurrency tests, plus the `make stats`, `make bench` and
  `make calibrate` targets.
- Benchmarks against `pyfusefilter` (Xor8, Xor16, Fuse8, Fuse16) and `rbloom` (`docs/benchmark.md`, `docs/benchmark.png`),
  plus small README figures drawn from the saved results (`docs/img/`, `make figures`).
- A release workflow (`release.yml`): a pushed `v*` tag runs the tests, builds the sdist and the wheels, publishes to PyPI and creates
  a GitHub release. Manual runs are dry runs.
- CI workflows for lint, docstyle, mypy strict and stubtest, tests on Python 3.10 to 3.14, Windows and macOS builds,
  sanitizers, fuzzing, the sdist build and cibuildwheel. None of them publishes anything.

### Notes
- Two measurements changed the design before this version. The seed is now pre-mixed and added to the key hash, because
  an XOR-mixed seed made nearby seeds produce nearly identical filters for dense integer keys. The default overhead
  table was also recalibrated against the real build, which fails at most 3.3% of attempts at every size.
