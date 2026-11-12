# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

First development version (0.1.0, not published).

### Added
- `RibbonFilter`: an immutable standard ribbon filter (width 64, `fp_bits` 1 to 32), built from an iterable of
  `bytes`, `bytearray`, `memoryview`, `str` or `int` keys, or from a 1-D integer buffer (`array.array`, numpy).
- `in`, `contains_many`, `len`, `to_bytes`, zero-copy `from_buffer` (optional payload verification), `size_in_bytes`,
  `bits_per_key`, `fp_bits`, `pickle` and `copy` support, `RibbonError`, `ConstructionError`, `FormatError`.
- Versioned little-endian serialization format with magic number, header and payload checksums; the loader treats its
  input as untrusted.
- C11 core (`core/`) with its own unit tests, portable bit-operation fallbacks, ASan/UBSan runs and a loader fuzz harness;
  builds without Python.
- Pure-Python reference implementation of the spec used as a test oracle (`tests/spec_reference.py`).
- Property, differential-fuzz, statistical, leak and concurrency tests; `make stats`, `make bench`, `make calibrate`.
- Benchmarks against `pyfusefilter` (Xor8, Xor16, Fuse8, Fuse16) and `rbloom` (`docs/benchmark.md`, `docs/benchmark.png`).
- CI workflows (lint, docstyle, mypy strict + stubtest, tests on Python 3.10 to 3.14, Windows and macOS builds,
  sanitizers, fuzzing, sdist build, cibuildwheel); nothing publishes.

### Notes
- Two measurement findings changed the design before this version: the seed is pre-mixed and added to the key hash (an
  XOR-mixed seed made nearby seeds produce nearly identical filters for dense integer keys), and the default overhead
  table was recalibrated against the real build (3.3% per-attempt failure or less at every size).
