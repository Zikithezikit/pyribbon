# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

- CI and wheel workflows now run only for pushes to `main`, tags (through `release.yml`) and pull requests that target `main`; a test
  enforces this for every workflow.

- The GitHub release is now its own last job in `release.yml`: it runs only after the PyPI upload succeeded, which itself needs the
  whole pipeline to have passed, and only for a pushed `v*` tag. A failed release can be re-run without touching PyPI.

- Project files: `SECURITY.md`, issue and pull request templates, Dependabot for Actions, pre-commit for ruff, `.editorconfig`.

### Added
- Documentation for the standalone C library (`core/README.md`), a runnable example (`core/examples/basic.c`, run by
  `make -C core example` and in CI), and complete function comments in `ribbon.h`.

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
