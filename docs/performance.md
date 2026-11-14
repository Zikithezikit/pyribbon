# Performance

The front page shows the summary. This page has the numbers behind it.

The tables on this page come from `make bench` and are copied in by `benchmarks/update_readme.py`; a test fails if a
number here differs from the report. [benchmark.md](benchmark.md) has the machine description, method, medians, spreads and
caveats, [benchmark.json](benchmark.json) the raw data. The overview figure on the front page comes from `benchmarks/make_figures.py`; the full six-panel plot is
[benchmark.png](benchmark.png). The baselines are `pyfusefilter` (Xor8,
Xor16, Fuse8 and Fuse16; it is the maintained successor of `pyxorfilter`) and `rbloom` (a Bloom filter). All numbers come
from one machine (an i7-7700, CPython 3.14), pinned to one core.

The first table summarises the largest size, comparing pyribbon with the best other filter of the same fingerprint width:

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

The next tables show how the results change with the number of keys:

<!-- bench-by-size:start -->
*Space, 8-bit class (bits per key including the 64-byte header; last column: pyribbon relative to Fuse8):*

| n | pyribbon | Xor8 | Fuse8 | rbloom 2^-8 | pyribbon vs Fuse8 |
|---:|---:|---:|---:|---:|---:|
| 1,000 | 9.22 | 10.27 | 11.58 | 11.54 | -20.4% |
| 10,000 | 8.65 | 9.88 | 10.07 | 11.54 | -14.0% |
| 100,000 | 8.79 | 9.84 | 9.51 | 11.54 | -7.5% |
| 1,000,000 | 8.99 | 9.84 | 9.04 | 11.54 | -0.6% |
| 10,000,000 | 9.19 | 9.84 | 9.02 | 11.54 | +2.0% |

*Build time (ns per key). `pyfusefilter` as shipped hashes every key in Python; the last column is its bare C core on pre-hashed keys, which is what a C-to-C comparison would use:*

| n | pyribbon (Python keys) | Fuse8 as shipped | Fuse8 C core only |
|---:|---:|---:|---:|
| 1,000 | 70 | 521 | 40 |
| 10,000 | 57 | 527 | 27 |
| 100,000 | 56 | 521 | 27 |
| 1,000,000 | 59 | 541 | 39 |
| 10,000,000 | 78 | 570 | 54 |

*Query: `key in f` in ns (member / non-member) and `contains_many` throughput (million keys per second, 50/50 mix, from a list and from an `array('q')`):*

| n | pyribbon `in` | Fuse8 `in` | pyribbon batch (list) | pyribbon batch (array) |
|---:|---:|---:|---:|---:|
| 1,000 | 46 / 40 | 648 / 650 | 21.1 | 30.3 |
| 10,000 | 48 / 40 | 658 / 658 | 21.5 | 30.7 |
| 100,000 | 46 / 44 | 652 / 659 | 21.6 | 29.6 |
| 1,000,000 | 52 / 51 | 662 / 660 | 21.0 | 29.0 |
| 10,000,000 | 86 / 88 | 753 / 733 | 18.6 | 24.8 |
<!-- bench-by-size:end -->

On space, pyribbon is the smallest filter up to about a hundred thousand keys, roughly level with Fuse8 at a million, and
slightly larger than Fuse8 at ten million. With width 64 the overhead grows with the logarithm of the set size. It stays
well below a Bloom filter at every size.

Building from Python keys, pyribbon is several times faster than `pyfusefilter` as shipped, because that package hashes
every key in Python. That says something about the Python wrapper, not the algorithm: on pre-hashed keys the bare C core
of Fuse8 builds faster than pyribbon's elimination (last column of the build table). pyribbon also builds faster than
`rbloom` here, which calls Python's `hash()` per key.

`key in f` takes tens of nanoseconds in the C extension, and a good part of that is the interpreter's call overhead.
`pyfusefilter` goes through `cffi` and hashes in Python. The batch API, especially with an integer array, avoids most of
the per-key interpreter cost.

The caveats are in [benchmark.md](benchmark.md). The numbers come from one machine with a `powersave` governor, so absolute
figures do not transfer, only the comparisons within a run. The baselines are measured as shipped, including the
Python-side hashing they do.
