# pyribbon documentation

pyribbon is a ribbon filter for Python: a static set-membership filter that never misses a key and is wrong about a
non-member with a probability you choose. The [front page](https://github.com/Zikithezikit/pyribbon#readme) has the install
line, a quick start and the headline numbers. Everything else is here.

## Using it

- [Usage](usage.md): keys, choosing `fp_bits`, saving and loading, batches, errors and threads, with the example scripts.
- [API reference](api.md): every class, method, parameter and exception.
- [Limits](limits.md): what a filter cannot do, and what it costs to build.

## Why it behaves this way

- [How it works](how-it-works.md): the algorithm in a few paragraphs, with the papers it comes from.
- [Performance](performance.md): space, build time and lookup time against `pyfusefilter` and `rbloom`, by number of keys.
- [Benchmark report](benchmark.md): the machine, the method, medians, spreads and caveats behind those numbers.
- [Measured false-positive rates](measurements.md): every test case, with the number of probes behind it.
- [DESIGN.md](../DESIGN.md): the decisions, the serialization format and the measurements behind the implementation.
- [RESEARCH.md](../RESEARCH.md): the literature survey.

## The C library

The core builds and tests without Python. [core/README.md](../core/README.md) explains how to use it from C.

## Working on pyribbon

- [CONTRIBUTING.md](../CONTRIBUTING.md): setup, checks, the examples rule, how releases are cut and when CI runs.
- [SECURITY.md](../SECURITY.md): how to report a vulnerability.
- [CHANGELOG.md](../CHANGELOG.md): what changed in each release.
