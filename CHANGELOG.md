# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

- The test that a large build does not hold the GIL uses a lower threshold: it failed once on a loaded macOS Intel runner during
  the 0.1.1 release, with a ticker at 17% of its free speed where a build that held the GIL would give about 0%.

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
