<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Zikithezikit/pyribbon/main/docs/img/logo/pyribbon-lockup-white.svg">
    <img alt="pyribbon" src="https://raw.githubusercontent.com/Zikithezikit/pyribbon/main/docs/img/logo/pyribbon-lockup.svg" width="360">
  </picture>
</p>

# pyribbon

[![PyPI](https://img.shields.io/pypi/v/pyribbon)](https://pypi.org/project/pyribbon/)
[![Python versions](https://img.shields.io/pypi/pyversions/pyribbon)](https://pypi.org/project/pyribbon/)
[![CI](https://github.com/Zikithezikit/pyribbon/actions/workflows/ci.yml/badge.svg)](https://github.com/Zikithezikit/pyribbon/actions/workflows/ci.yml)
[![Licence: MIT](https://img.shields.io/github/license/Zikithezikit/pyribbon)](https://github.com/Zikithezikit/pyribbon/blob/main/LICENSE)

Ribbon filters for Python: a static set-membership filter that never misses a key it was built from, and is wrong about any
other key with a probability you choose (`2**-fp_bits`), in fewer bits per key than a Bloom filter. Written in C11 with no
Python dependencies. Licensed MIT.

## Install

```bash
pip install pyribbon
```

Python 3.10 or newer, from [PyPI](https://pypi.org/project/pyribbon/). Prebuilt wheels cover Linux (x86-64 and ARM, glibc
and musl), macOS (Intel and Apple silicon) and Windows (x64), including the free-threaded builds of Python 3.14 and 3.15.
On any other platform pip builds the source distribution, and a C compiler is the only build requirement.

## Quick start

```python
from pyribbon import RibbonFilter

f = RibbonFilter(["alice", "bob", "carol"], fp_bits=12)  # a wrong "yes" about once in 2**12 lookups
assert "alice" in f  # a member is always found
assert "mallory" not in f  # this non-member was rejected; one in 2**12 would slip through
assert f.contains_many(["alice", "mallory"]) == [True, False]  # one answer per key
```

Keys can be `bytes`, `str` or `int`. A filter built from a list, an `array.array` or a numpy array of integers answers a whole
batch with `contains_many`. Save one with `f.to_bytes()` and load it back with `RibbonFilter.from_buffer(data)`, which
reads the bytes where they are without copying them. Seven runnable scripts in
[examples/](https://github.com/Zikithezikit/pyribbon/tree/main/examples) start with `01_quickstart.py`.

## Sizes

The false-positive rate is `2**-fp_bits`, with `fp_bits` from 1 to 32 (default 8). Measured at 1,000,000 keys, the 64-byte
header included. Bits per key is a decimal because the filter has about 12% more rows than keys, so its size divided by the
number of keys is not a whole number. A Bloom filter needs `1.44 * fp_bits` bits per key.

| `fp_bits` | false-positive rate | bits per key |
|---:|---:|---:|
| 1 | 50% | 1.12 |
| 2 | 25% | 2.25 |
| 4 | 6.25% | 4.50 |
| 6 | 1.6% | 6.75 |
| 8 | 0.39% | 8.99 |
| 10 | 0.098% | 11.24 |
| 12 | 0.024% | 13.49 |
| 16 | 0.0015% | 17.99 |
| 20 | 0.000095% | 22.48 |
| 24 | 0.0000060% | 26.98 |
| 28 | 0.00000037% | 31.48 |
| 32 | 0.000000023% | 35.97 |

## Performance

Space, build time and lookup time against the number of keys, on one machine (an i7-7700, CPython 3.14, pinned to one core)
against `pyfusefilter` and `rbloom`. Lower is better in every panel. One machine, one run.

![Space per key, build time and lookup time against the number of keys for pyribbon, Fuse8, Xor8 and rbloom](https://raw.githubusercontent.com/Zikithezikit/pyribbon/main/docs/img/overview.png)

The largest size, against the best other filter of the same fingerprint width:

<!-- bench:start -->
*Where pyribbon wins and loses (int keys, n = 10,000,000):*

| Class | Metric | pyribbon | Best other | Delta | Verdict |
| --- | --- | ---: | ---: | ---: | ---: |
| 8-bit | bits/key | 9.19 | 9.02 (Fuse8) | +2% | **pyribbon behind** |
| 8-bit | bits/key above log2(1/FPR) | 1.18 | 1.00 (Fuse8) | +17% | **pyribbon behind** |
| 8-bit | build ns/key | 78 | 207 (rbloom 2^-8, builtin hash()) | -63% | pyribbon ahead |
| 8-bit | `in` member ns | 86 | 218 (rbloom 2^-8, builtin hash()) | -60% | pyribbon ahead |
| 8-bit | `in` non-member ns | 88 | 143 (rbloom 2^-8, builtin hash()) | -38% | pyribbon ahead |
| 8-bit | batch Mkeys/s (50/50 mix) | 18.61 | 5.37 (rbloom 2^-8, builtin hash()) | +247% | pyribbon ahead |
| 16-bit | bits/key | 18.39 | 18.04 (Fuse16) | +2% | **pyribbon behind** |
| 16-bit | bits/key above log2(1/FPR) | 2.36 | 1.95 (Fuse16) | +21% | **pyribbon behind** |
| 16-bit | build ns/key | 92 | 432 (rbloom 2^-16, builtin hash()) | -79% | pyribbon ahead |
| 16-bit | `in` member ns | 136 | 417 (rbloom 2^-16, builtin hash()) | -67% | pyribbon ahead |
| 16-bit | `in` non-member ns | 106 | 162 (rbloom 2^-16, builtin hash()) | -34% | pyribbon ahead |
| 16-bit | batch Mkeys/s (50/50 mix) | 11.73 | 3.36 (rbloom 2^-16, builtin hash()) | +249% | pyribbon ahead |

Delta is relative to the best other filter of the same fingerprint class, including rbloom with its builtin `hash()`; a negative delta means pyribbon is lower. Lower is better except for batch throughput. The 'above log2(1/FPR)' rows move with the measured FPR, whose uncertainty is in the notes. The batch row compares `contains_many` with the other libraries' per-key loop, because none of them has a batch API. The table is computed from the raw results of this run.
<!-- bench:end -->

## More

Everything else is in [docs/](https://github.com/Zikithezikit/pyribbon/blob/main/docs/index.md): the [usage guide](https://github.com/Zikithezikit/pyribbon/blob/main/docs/usage.md), the [API reference](https://github.com/Zikithezikit/pyribbon/blob/main/docs/api.md), the
[limits](https://github.com/Zikithezikit/pyribbon/blob/main/docs/limits.md), [how it works](https://github.com/Zikithezikit/pyribbon/blob/main/docs/how-it-works.md), the [internals](https://github.com/Zikithezikit/pyribbon/blob/main/docs/internals.md) (hashing, the file format, the C core) and the full [performance numbers](https://github.com/Zikithezikit/pyribbon/blob/main/docs/performance.md) by number
of keys. The C core builds and tests on its own: see [core/README.md](https://github.com/Zikithezikit/pyribbon/blob/main/core/README.md). To work on pyribbon, read
[CONTRIBUTING.md](https://github.com/Zikithezikit/pyribbon/blob/main/CONTRIBUTING.md). To report a vulnerability, read [SECURITY.md](https://github.com/Zikithezikit/pyribbon/blob/main/SECURITY.md).

## Licence and credits

pyribbon is MIT licensed ([LICENSE](https://github.com/Zikithezikit/pyribbon/blob/main/LICENSE)). The vendored xxHash header (`core/vendor/xxhash.h`) is BSD 2-Clause
([LICENSES/](https://github.com/Zikithezikit/pyribbon/tree/main/LICENSES)). The algorithm is by Peter C. Dillinger and Stefan Walzer, in
"Ribbon filter: practically smaller than Bloom and Xor" (arXiv:2103.02515). This implementation was written from their papers,
not from existing code.
