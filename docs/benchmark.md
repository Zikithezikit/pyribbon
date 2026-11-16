# pyribbon benchmark

## Machine and software

- CPU: Intel Core i7-7700 CPU @ 3.60GHz
- Logical CPUs: 8, benchmark pinned to CPU 7
- Frequency scaling governor: powersave
- CPU frequency: 4.09 GHz at start, max 4.20 GHz, turbo enabled
- OS / kernel: Linux 7.0.0-43-generic (Linux-7.0.0-43-generic-x86_64-with-glibc2.43)
- Python: CPython 3.14.4, built with GCC 15.2.0
- Python build flags: CC=x86_64-linux-gnu-gcc; CFLAGS=-fno-strict-overflow -Wsign-compare -DNDEBUG -g -O2 -Wall
- pyribbon extension: _ribbon.abi3.so; compiler recorded in the binary: GCC: (Ubuntu 15.2.0-16ubuntu1) 15.2.0
- pyribbon build flags: setup.py adds none (/std:c11 on Windows only): the interpreter's CFLAGS above are used
- pyribbon version: 0.2.0
- pyfusefilter version: 1.3.2
- rbloom version: 1.5.4
- Other packages: xxhash 4.1.0, cffi 2.1.1, numpy 2.5.4, matplotlib 3.11.2

## Run

- Date: 2026-11-16T09:32:03+02:00
- Command: `python benchmarks/bench.py --plot docs/benchmark.png --table docs/benchmark.md --json docs/benchmark.json`
- Pinning: CPU 7
- Key sizes (int): 1,000, 10,000, 100,000, 1,000,000, 10,000,000
- Key sizes (str): 10,000, 1,000,000
- Repeats: 7 (at most 3 at n >= 10,000,000); statistics are median and min/max
- Query set: 100,000 keys per loop/batch
- FPR probes: 4,000,000 (8-bit class), 20,000,000 (16-bit class), in chunks of 1,000,000
- Seed: 20261112
- Mode: full
- Total run time: 585 s

## Where pyribbon wins and loses (int keys, n = 10,000,000)

| Class | Metric | pyribbon | Best other | Delta | Verdict |
| --- | --- | ---: | ---: | ---: | ---: |
| 8-bit | bits/key | 9.19 | 9.02 (Fuse8) | +2% | **pyribbon behind** |
| 8-bit | bits/key above log2(1/FPR) | 1.18 | 1.00 (Fuse8) | +17% | **pyribbon behind** |
| 8-bit | build ns/key | 78 | 203 (rbloom 2^-8, builtin hash()) | -62% | pyribbon ahead |
| 8-bit | `in` member ns | 91 | 213 (rbloom 2^-8, builtin hash()) | -57% | pyribbon ahead |
| 8-bit | `in` non-member ns | 94 | 139 (rbloom 2^-8, builtin hash()) | -33% | pyribbon ahead |
| 8-bit | batch Mkeys/s (50/50 mix) | 20.92 | 5.48 (rbloom 2^-8, builtin hash()) | +281% | pyribbon ahead |
| 16-bit | bits/key | 18.39 | 18.04 (Fuse16) | +2% | **pyribbon behind** |
| 16-bit | bits/key above log2(1/FPR) | 2.36 | 1.95 (Fuse16) | +21% | **pyribbon behind** |
| 16-bit | build ns/key | 93 | 423 (rbloom 2^-16, builtin hash()) | -78% | pyribbon ahead |
| 16-bit | `in` member ns | 131 | 411 (rbloom 2^-16, builtin hash()) | -68% | pyribbon ahead |
| 16-bit | `in` non-member ns | 109 | 162 (rbloom 2^-16, builtin hash()) | -33% | pyribbon ahead |
| 16-bit | batch Mkeys/s (50/50 mix) | 12.24 | 3.40 (rbloom 2^-16, builtin hash()) | +260% | pyribbon ahead |

Delta is relative to the best other filter of the same fingerprint class, including rbloom with its builtin `hash()`; a negative delta means pyribbon is lower. Lower is better except for batch throughput. The 'above log2(1/FPR)' rows move with the measured FPR, whose uncertainty is in the notes. The batch row compares `contains_many` with the other libraries' per-key loop, because none of them has a batch API. The table is computed from the raw results of this run.

## Width 128 against width 64 (int keys, n = 10,000,000)

| Class | Metric | width 64 | width 128 | Delta |
| --- | --- | ---: | ---: | ---: |
| 8-bit | bits/key | 9.19 | 8.49 | -8% |
| 8-bit | build ns/key | 78 | 97 | +25% |
| 8-bit | `in` member ns | 91 | 97 | +6% |
| 8-bit | `in` non-member ns | 94 | 93 | -1% |
| 8-bit | batch Mkeys/s (50/50 mix) | 20.92 | 17.08 | -18% |
| 16-bit | bits/key | 18.39 | 16.99 | -8% |
| 16-bit | build ns/key | 93 | 114 | +23% |
| 16-bit | `in` member ns | 131 | 144 | +10% |
| 16-bit | `in` non-member ns | 109 | 118 | +9% |
| 16-bit | batch Mkeys/s (50/50 mix) | 12.24 | 10.13 | -17% |

The same keys, `fp_bits` and default overhead at both widths. The win/loss table above is width 64, the default; width 128 appears below as `w128` rows.

## Results: int keys (pseudo-random 63-bit)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 9.216 | 0.00388 [0.00382, 0.00394] | 15,502 / 4,000,000 | 0.99 | 8.01 | 1.20 (15%) |
| pyribbon fp16 | 1,000 | 17.920 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 1.98 (12%) |
| pyribbon fp8 w128 | 1,000 | 9.216 | 0.0039 [0.00383, 0.00396] | 15,581 / 4,000,000 | 1.00 | 8.00 | 1.21 (15%) |
| pyribbon fp16 w128 | 1,000 | 17.920 | 1.67e-05 [1.5e-05, 1.86e-05] | 334 / 20,000,000 | 1.09 | 15.87 | 2.05 (13%) |
| Xor8 | 1,000 | 10.272 | 0.00391 [0.00385, 0.00397] | 15,637 / 4,000,000 | 1.00 | 8.00 | 2.27 (28%) |
| Xor16 | 1,000 | 20.352 | 1.53e-05 [1.37e-05, 1.71e-05] | 306 / 20,000,000 | 1.00 | 16.00 | 4.36 (27%) |
| Fuse8 | 1,000 | 11.584 | 0.00385 [0.00379, 0.00391] | 15,402 / 4,000,000 | 0.99 | 8.02 | 3.56 (44%) |
| Fuse16 | 1,000 | 22.848 | 1.53e-05 [1.37e-05, 1.71e-05] | 306 / 20,000,000 | 1.00 | 16.00 | 6.85 (43%) |
| rbloom 2^-8 | 1,000 | 11.544 | 0.00394 [0.00387, 0.004] | 15,741 / 4,000,000 | 1.01 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 1,000 | 23.088 | 1.78e-05 [1.6e-05, 1.97e-05] | 356 / 20,000,000 | 1.17 | 15.78 | 7.31 (46%) |
| pyribbon fp8 | 10,000 | 8.653 | 0.00389 [0.00383, 0.00395] | 15,564 / 4,000,000 | 1.00 | 8.01 | 0.65 (8%) |
| pyribbon fp16 | 10,000 | 17.254 | 1.5e-05 [1.34e-05, 1.68e-05] | 300 / 20,000,000 | 0.98 | 16.02 | 1.23 (8%) |
| pyribbon fp8 w128 | 10,000 | 8.294 | 0.0039 [0.00384, 0.00396] | 15,599 / 4,000,000 | 1.00 | 8.00 | 0.29 (4%) |
| pyribbon fp16 w128 | 10,000 | 16.538 | 1.57e-05 [1.41e-05, 1.76e-05] | 315 / 20,000,000 | 1.03 | 15.95 | 0.58 (4%) |
| Xor8 | 10,000 | 9.883 | 0.00391 [0.00385, 0.00397] | 15,629 / 4,000,000 | 1.00 | 8.00 | 1.88 (24%) |
| Xor16 | 10,000 | 19.747 | 1.45e-05 [1.29e-05, 1.63e-05] | 290 / 20,000,000 | 0.95 | 16.07 | 3.67 (23%) |
| Fuse8 | 10,000 | 10.067 | 0.00393 [0.00387, 0.00399] | 15,711 / 4,000,000 | 1.01 | 7.99 | 2.08 (26%) |
| Fuse16 | 10,000 | 20.102 | 1.65e-05 [1.48e-05, 1.83e-05] | 329 / 20,000,000 | 1.08 | 15.89 | 4.21 (26%) |
| rbloom 2^-8 | 10,000 | 11.542 | 0.00396 [0.0039, 0.00402] | 15,832 / 4,000,000 | 1.01 | 7.98 | 3.56 (45%) |
| rbloom 2^-16 | 10,000 | 23.083 | 1.52e-05 [1.36e-05, 1.7e-05] | 304 / 20,000,000 | 1.00 | 16.01 | 7.08 (44%) |
| pyribbon fp8 | 100,000 | 8.791 | 0.00391 [0.00384, 0.00397] | 15,621 / 4,000,000 | 1.00 | 8.00 | 0.79 (10%) |
| pyribbon fp16 | 100,000 | 17.577 | 1.38e-05 [1.23e-05, 1.55e-05] | 276 / 20,000,000 | 0.90 | 16.14 | 1.43 (9%) |
| pyribbon fp8 w128 | 100,000 | 8.315 | 0.00391 [0.00385, 0.00397] | 15,626 / 4,000,000 | 1.00 | 8.00 | 0.31 (4%) |
| pyribbon fp16 w128 | 100,000 | 16.625 | 1.51e-05 [1.35e-05, 1.69e-05] | 302 / 20,000,000 | 0.99 | 16.02 | 0.61 (4%) |
| Xor8 | 100,000 | 9.844 | 0.00398 [0.00392, 0.00405] | 15,934 / 4,000,000 | 1.02 | 7.97 | 1.87 (23%) |
| Xor16 | 100,000 | 19.687 | 1.54e-05 [1.37e-05, 1.72e-05] | 307 / 20,000,000 | 1.01 | 15.99 | 3.70 (23%) |
| Fuse8 | 100,000 | 9.506 | 0.00388 [0.00382, 0.00394] | 15,520 / 4,000,000 | 0.99 | 8.01 | 1.50 (19%) |
| Fuse16 | 100,000 | 19.009 | 1.52e-05 [1.36e-05, 1.7e-05] | 304 / 20,000,000 | 1.00 | 16.01 | 3.00 (19%) |
| rbloom 2^-8 | 100,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,663 / 4,000,000 | 1.00 | 8.00 | 3.55 (44%) |
| rbloom 2^-16 | 100,000 | 23.083 | 1.5e-05 [1.34e-05, 1.68e-05] | 301 / 20,000,000 | 0.99 | 16.02 | 7.06 (44%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,571 / 4,000,000 | 1.00 | 8.00 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.68e-05 [1.5e-05, 1.86e-05] | 335 / 20,000,000 | 1.10 | 15.87 | 2.12 (13%) |
| pyribbon fp8 w128 | 1,000,000 | 8.414 | 0.00394 [0.00388, 0.004] | 15,756 / 4,000,000 | 1.01 | 7.99 | 0.43 (5%) |
| pyribbon fp16 w128 | 1,000,000 | 16.827 | 1.47e-05 [1.31e-05, 1.65e-05] | 294 / 20,000,000 | 0.96 | 16.05 | 0.77 (5%) |
| Xor8 | 1,000,000 | 9.840 | 0.00386 [0.0038, 0.00392] | 15,449 / 4,000,000 | 0.99 | 8.02 | 1.82 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.36e-05 [1.21e-05, 1.54e-05] | 273 / 20,000,000 | 0.89 | 16.16 | 3.52 (22%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00385 [0.00379, 0.00391] | 15,394 / 4,000,000 | 0.99 | 8.02 | 1.02 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.49e-05 [1.33e-05, 1.66e-05] | 297 / 20,000,000 | 0.97 | 16.04 | 2.05 (13%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00387 [0.00381, 0.00393] | 15,483 / 4,000,000 | 0.99 | 8.01 | 3.53 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 7.14 (45%) |
| pyribbon fp8 | 10,000,000 | 9.195 | 0.00386 [0.0038, 0.00392] | 15,440 / 4,000,000 | 0.99 | 8.02 | 1.18 (15%) |
| pyribbon fp16 | 10,000,000 | 18.390 | 1.49e-05 [1.33e-05, 1.67e-05] | 298 / 20,000,000 | 0.98 | 16.03 | 2.36 (15%) |
| pyribbon fp8 w128 | 10,000,000 | 8.494 | 0.00385 [0.00379, 0.00391] | 15,411 / 4,000,000 | 0.99 | 8.02 | 0.47 (6%) |
| pyribbon fp16 w128 | 10,000,000 | 16.988 | 1.58e-05 [1.42e-05, 1.77e-05] | 317 / 20,000,000 | 1.04 | 15.95 | 1.04 (7%) |
| Xor8 | 10,000,000 | 9.840 | 0.00392 [0.00386, 0.00398] | 15,681 / 4,000,000 | 1.00 | 7.99 | 1.85 (23%) |
| Xor16 | 10,000,000 | 19.680 | 1.47e-05 [1.31e-05, 1.65e-05] | 294 / 20,000,000 | 0.96 | 16.05 | 3.63 (23%) |
| Fuse8 | 10,000,000 | 9.018 | 0.00387 [0.00381, 0.00393] | 15,466 / 4,000,000 | 0.99 | 8.01 | 1.00 (13%) |
| Fuse16 | 10,000,000 | 18.036 | 1.44e-05 [1.28e-05, 1.62e-05] | 288 / 20,000,000 | 0.94 | 16.08 | 1.95 (12%) |
| rbloom 2^-8 | 10,000,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,690 / 4,000,000 | 1.00 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 10,000,000 | 23.083 | 1.62e-05 [1.45e-05, 1.81e-05] | 324 / 20,000,000 | 1.06 | 15.91 | 7.17 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 7.09e-05 [6.9e-05, 8.2e-05] | 70.9 [69, 82] |
| pyribbon fp16 | 1,000 | 8.71e-05 [8.39e-05, 0.000112] | 87.1 [83.9, 112] |
| pyribbon fp8 w128 | 1,000 | 0.000108 [0.000108, 0.000109] | 108 [108, 109] |
| pyribbon fp16 w128 | 1,000 | 0.00013 [0.000129, 0.000143] | 130 [129, 143] |
| Xor8 | 1,000 | 0.0006 [0.000585, 0.000693] | 600 [585, 693] |
| Xor16 | 1,000 | 0.000647 [0.000627, 0.00143] | 647 [627, 1.43e+03] |
| Fuse8 | 1,000 | 0.000527 [0.000516, 0.000545] | 527 [516, 545] |
| Fuse16 | 1,000 | 0.000527 [0.000517, 0.000549] | 527 [517, 549] |
| rbloom 2^-8 | 1,000 | 0.000279 [0.000275, 0.000283] | 279 [275, 283] |
| rbloom 2^-16 | 1,000 | 0.000338 [0.000334, 0.000377] | 338 [334, 377] |
| pyribbon fp8 | 10,000 | 0.000582 [0.000575, 0.00061] | 58.2 [57.5, 61] |
| pyribbon fp16 | 10,000 | 0.000722 [0.000719, 0.000744] | 72.2 [71.9, 74.4] |
| pyribbon fp8 w128 | 10,000 | 0.000862 [0.000855, 0.000891] | 86.2 [85.5, 89.1] |
| pyribbon fp16 w128 | 10,000 | 0.00103 [0.00102, 0.00107] | 103 [102, 107] |
| Xor8 | 10,000 | 0.00502 [0.00495, 0.00525] | 502 [495, 525] |
| Xor16 | 10,000 | 0.005 [0.0049, 0.00512] | 500 [490, 512] |
| Fuse8 | 10,000 | 0.00501 [0.00491, 0.00513] | 501 [491, 513] |
| Fuse16 | 10,000 | 0.00494 [0.00486, 0.00508] | 494 [486, 508] |
| rbloom 2^-8 | 10,000 | 0.00269 [0.00266, 0.00275] | 269 [266, 275] |
| rbloom 2^-16 | 10,000 | 0.00344 [0.00335, 0.00516] | 344 [335, 516] |
| pyribbon fp8 | 100,000 | 0.00572 [0.00566, 0.00574] | 57.2 [56.6, 57.4] |
| pyribbon fp16 | 100,000 | 0.00713 [0.00709, 0.00723] | 71.3 [70.9, 72.3] |
| pyribbon fp8 w128 | 100,000 | 0.00794 [0.00785, 0.00803] | 79.4 [78.5, 80.3] |
| pyribbon fp16 w128 | 100,000 | 0.00962 [0.00951, 0.00986] | 96.2 [95.1, 98.6] |
| Xor8 | 100,000 | 0.056 [0.0556, 0.0569] | 560 [556, 569] |
| Xor16 | 100,000 | 0.0559 [0.0557, 0.0604] | 559 [557, 604] |
| Fuse8 | 100,000 | 0.0512 [0.051, 0.0584] | 512 [510, 584] |
| Fuse16 | 100,000 | 0.0512 [0.0504, 0.0572] | 512 [504, 572] |
| rbloom 2^-8 | 100,000 | 0.028 [0.0262, 0.0306] | 280 [262, 306] |
| rbloom 2^-16 | 100,000 | 0.0338 [0.0327, 0.0385] | 338 [327, 385] |
| pyribbon fp8 | 1,000,000 | 0.0581 [0.0578, 0.0776] | 58.1 [57.8, 77.6] |
| pyribbon fp16 | 1,000,000 | 0.0729 [0.0724, 0.0772] | 72.9 [72.4, 77.2] |
| pyribbon fp8 w128 | 1,000,000 | 0.0738 [0.0734, 0.0901] | 73.8 [73.4, 90.1] |
| pyribbon fp16 w128 | 1,000,000 | 0.0906 [0.0902, 0.0964] | 90.6 [90.2, 96.4] |
| Xor8 | 1,000,000 | 0.598 [0.586, 0.612] | 598 [586, 612] |
| Xor16 | 1,000,000 | 0.605 [0.593, 0.617] | 605 [593, 617] |
| Fuse8 | 1,000,000 | 0.549 [0.539, 0.584] | 549 [539, 584] |
| Fuse16 | 1,000,000 | 0.554 [0.537, 0.556] | 554 [537, 556] |
| rbloom 2^-8 | 1,000,000 | 0.272 [0.271, 0.293] | 272 [271, 293] |
| rbloom 2^-16 | 1,000,000 | 0.349 [0.332, 0.388] | 349 [332, 388] |
| pyribbon fp8 | 10,000,000 | 0.775 [0.77, 0.784] | 77.5 [77, 78.4] |
| pyribbon fp16 | 10,000,000 | 0.927 [0.924, 0.935] | 92.7 [92.4, 93.5] |
| pyribbon fp8 w128 | 10,000,000 | 0.968 [0.967, 0.984] | 96.8 [96.7, 98.4] |
| pyribbon fp16 w128 | 10,000,000 | 1.14 [1.14, 1.15] | 114 [114, 115] |
| Xor8 | 10,000,000 | 6.24 [6.23, 6.34] | 624 [623, 634] |
| Xor16 | 10,000,000 | 6.26 [6.26, 6.32] | 626 [626, 632] |
| Fuse8 | 10,000,000 | 5.79 [5.75, 5.79] | 579 [575, 579] |
| Fuse16 | 10,000,000 | 5.75 [5.75, 5.79] | 575 [575, 579] |
| rbloom 2^-8 | 10,000,000 | 4.1 [4.08, 4.1] | 410 [408, 410] |
| rbloom 2^-16 | 10,000,000 | 6.34 [6.31, 6.38] | 634 [631, 638] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 39.2 [21.8, 39.7] | 39.1 [38.5, 39.7] | 46.1 |
| pyribbon fp16 | 1,000 | 54.1 [53.7, 57.8] | 40 [37.5, 40.3] | 60.9 |
| pyribbon fp8 w128 | 1,000 | 49.3 [47.6, 50.1] | 41.8 [40.1, 42.4] | 55.9 |
| pyribbon fp16 w128 | 1,000 | 70 [69.6, 71.9] | 41.3 [40.8, 42.4] | 77.2 |
| Xor8 | 1,000 | 678 [669, 706] | 658 [657, 684] | 685 |
| Xor16 | 1,000 | 682 [664, 730] | 679 [664, 749] | 689 |
| Fuse8 | 1,000 | 683 [677, 739] | 670 [658, 690] | 690 |
| Fuse16 | 1,000 | 684 [668, 690] | 652 [651, 760] | 691 |
| rbloom 2^-8 | 1,000 | 285 [283, 338] | 251 [250, 274] | 291 |
| rbloom 2^-16 | 1,000 | 341 [340, 348] | 252 [252, 255] | 348 |
| pyribbon fp8 | 10,000 | 39.1 [38.3, 44.1] | 39 [38.7, 39.7] | 46.2 |
| pyribbon fp16 | 10,000 | 53 [52.4, 55.3] | 39.5 [39, 40] | 59.6 |
| pyribbon fp8 w128 | 10,000 | 49.1 [47.6, 50.9] | 42.2 [41.6, 43.8] | 55.8 |
| pyribbon fp16 w128 | 10,000 | 70.4 [70, 72.6] | 41.4 [41, 42.1] | 77 |
| Xor8 | 10,000 | 670 [667, 687] | 667 [652, 671] | 677 |
| Xor16 | 10,000 | 674 [667, 737] | 682 [663, 717] | 681 |
| Fuse8 | 10,000 | 685 [676, 755] | 668 [660, 682] | 691 |
| Fuse16 | 10,000 | 669 [660, 759] | 677 [657, 738] | 675 |
| rbloom 2^-8 | 10,000 | 287 [286, 291] | 256 [255, 267] | 294 |
| rbloom 2^-16 | 10,000 | 346 [344, 408] | 257 [254, 259] | 353 |
| pyribbon fp8 | 100,000 | 40.6 [40.3, 41.2] | 40.6 [40.6, 41.1] | 47.5 |
| pyribbon fp16 | 100,000 | 56.5 [55.8, 58] | 42.7 [42.4, 45] | 63.1 |
| pyribbon fp8 w128 | 100,000 | 49.1 [48.4, 52] | 44.9 [43.5, 48.6] | 56.7 |
| pyribbon fp16 w128 | 100,000 | 69.5 [68.1, 70.4] | 45.3 [44.2, 46.5] | 76.1 |
| Xor8 | 100,000 | 668 [649, 785] | 651 [648, 655] | 675 |
| Xor16 | 100,000 | 694 [650, 759] | 680 [663, 684] | 701 |
| Fuse8 | 100,000 | 688 [675, 725] | 665 [654, 677] | 695 |
| Fuse16 | 100,000 | 663 [655, 730] | 663 [653, 671] | 669 |
| rbloom 2^-8 | 100,000 | 284 [281, 294] | 254 [252, 258] | 290 |
| rbloom 2^-16 | 100,000 | 345 [343, 350] | 261 [257, 282] | 351 |
| pyribbon fp8 | 1,000,000 | 50.8 [50.2, 52.2] | 50.5 [43.7, 78.2] | 57.5 |
| pyribbon fp16 | 1,000,000 | 65.9 [65.3, 67.7] | 52.8 [51.9, 54.2] | 72.5 |
| pyribbon fp8 w128 | 1,000,000 | 54.6 [54.2, 56.7] | 52.3 [52, 52.5] | 61.2 |
| pyribbon fp16 w128 | 1,000,000 | 78.1 [77.4, 80] | 54.1 [53.5, 54.4] | 84.8 |
| Xor8 | 1,000,000 | 673 [663, 781] | 680 [663, 737] | 680 |
| Xor16 | 1,000,000 | 681 [670, 927] | 686 [672, 729] | 687 |
| Fuse8 | 1,000,000 | 684 [667, 818] | 673 [669, 705] | 690 |
| Fuse16 | 1,000,000 | 694 [671, 756] | 675 [675, 771] | 701 |
| rbloom 2^-8 | 1,000,000 | 294 [292, 361] | 267 [266, 362] | 300 |
| rbloom 2^-16 | 1,000,000 | 357 [356, 367] | 276 [273, 321] | 364 |
| pyribbon fp8 | 10,000,000 | 91.2 [89.4, 92.3] | 93.8 [92.1, 104] | 97.9 |
| pyribbon fp16 | 10,000,000 | 131 [130, 153] | 109 [108, 110] | 138 |
| pyribbon fp8 w128 | 10,000,000 | 96.8 [94.3, 121] | 93.2 [92.2, 94.6] | 103 |
| pyribbon fp16 w128 | 10,000,000 | 144 [144, 155] | 118 [117, 153] | 151 |
| Xor8 | 10,000,000 | 764 [747, 850] | 757 [750, 811] | 771 |
| Xor16 | 10,000,000 | 766 [754, 842] | 770 [763, 852] | 773 |
| Fuse8 | 10,000,000 | 755 [747, 764] | 747 [739, 849] | 762 |
| Fuse16 | 10,000,000 | 764 [754, 889] | 765 [748, 840] | 771 |
| rbloom 2^-8 | 10,000,000 | 417 [416, 486] | 341 [339, 342] | 424 |
| rbloom 2^-16 | 10,000,000 | 623 [620, 739] | 360 [357, 434] | 630 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | `contains_many` | 23.3 | 23.9 | 23.5 |
| pyribbon fp8 | 1,000 | `contains_many` over an int `array('q')` | 34 | 34.8 | 34.4 |
| pyribbon fp16 | 1,000 | `contains_many` | 17.6 | 23 | 20 |
| pyribbon fp16 | 1,000 | `contains_many` over an int `array('q')` | 24.2 | 36.5 | 29.1 |
| pyribbon fp8 w128 | 1,000 | `contains_many` | 19.6 | 22.6 | 21 |
| pyribbon fp8 w128 | 1,000 | `contains_many` over an int `array('q')` | 27.8 | 33.2 | 30.2 |
| pyribbon fp16 w128 | 1,000 | `contains_many` | 13.9 | 22.4 | 17.2 |
| pyribbon fp16 w128 | 1,000 | `contains_many` over an int `array('q')` | 17.3 | 33.4 | 22.8 |
| Xor8 | 1,000 | per-key loop | 1.47 | 1.47 | 1.47 |
| Xor16 | 1,000 | per-key loop | 1.51 | 1.5 | 1.5 |
| Fuse8 | 1,000 | per-key loop | 1.48 | 1.49 | 1.49 |
| Fuse16 | 1,000 | per-key loop | 1.5 | 1.48 | 1.48 |
| rbloom 2^-8 | 1,000 | per-key loop | 3.38 | 3.82 | 3.58 |
| rbloom 2^-16 | 1,000 | per-key loop | 2.84 | 3.82 | 3.26 |
| pyribbon fp8 | 10,000 | `contains_many` | 23.6 | 23.7 | 23.6 |
| pyribbon fp8 | 10,000 | `contains_many` over an int `array('q')` | 35.9 | 36.3 | 36.1 |
| pyribbon fp16 | 10,000 | `contains_many` | 18 | 23.8 | 20.4 |
| pyribbon fp16 | 10,000 | `contains_many` over an int `array('q')` | 23.3 | 34.4 | 27.8 |
| pyribbon fp8 w128 | 10,000 | `contains_many` | 19.6 | 22.4 | 21 |
| pyribbon fp8 w128 | 10,000 | `contains_many` over an int `array('q')` | 27.5 | 33.4 | 30.3 |
| pyribbon fp16 w128 | 10,000 | `contains_many` | 13.3 | 21.1 | 16.3 |
| pyribbon fp16 w128 | 10,000 | `contains_many` over an int `array('q')` | 17.3 | 33.5 | 22.8 |
| Xor8 | 10,000 | per-key loop | 1.49 | 1.5 | 1.49 |
| Xor16 | 10,000 | per-key loop | 1.5 | 1.49 | 1.49 |
| Fuse8 | 10,000 | per-key loop | 1.48 | 1.49 | 1.49 |
| Fuse16 | 10,000 | per-key loop | 1.47 | 1.49 | 1.48 |
| rbloom 2^-8 | 10,000 | per-key loop | 3.36 | 3.75 | 3.54 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.81 | 3.74 | 3.21 |
| pyribbon fp8 | 100,000 | `contains_many` | 22.5 | 22.3 | 22.5 |
| pyribbon fp8 | 100,000 | `contains_many` over an int `array('q')` | 34.5 | 34.8 | 34.7 |
| pyribbon fp16 | 100,000 | `contains_many` | 17.8 | 23.7 | 20.3 |
| pyribbon fp16 | 100,000 | `contains_many` over an int `array('q')` | 24 | 35.8 | 28.5 |
| pyribbon fp8 w128 | 100,000 | `contains_many` | 19.7 | 22.5 | 21 |
| pyribbon fp8 w128 | 100,000 | `contains_many` over an int `array('q')` | 27.6 | 33.3 | 30.2 |
| pyribbon fp16 w128 | 100,000 | `contains_many` | 13.8 | 22.5 | 17.1 |
| pyribbon fp16 w128 | 100,000 | `contains_many` over an int `array('q')` | 16.7 | 32.3 | 22 |
| Xor8 | 100,000 | per-key loop | 1.51 | 1.5 | 1.5 |
| Xor16 | 100,000 | per-key loop | 1.48 | 1.47 | 1.48 |
| Fuse8 | 100,000 | per-key loop | 1.45 | 1.45 | 1.45 |
| Fuse16 | 100,000 | per-key loop | 1.49 | 1.46 | 1.47 |
| rbloom 2^-8 | 100,000 | per-key loop | 3.36 | 3.73 | 3.53 |
| rbloom 2^-16 | 100,000 | per-key loop | 2.77 | 3.67 | 3.15 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 22.3 | 22.6 | 22.5 |
| pyribbon fp8 | 1,000,000 | `contains_many` over an int `array('q')` | 34.2 | 35.1 | 34.6 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 15.7 | 23.1 | 18.6 |
| pyribbon fp16 | 1,000,000 | `contains_many` over an int `array('q')` | 20.6 | 34.6 | 25.8 |
| pyribbon fp8 w128 | 1,000,000 | `contains_many` | 18.1 | 20.6 | 19.3 |
| pyribbon fp8 w128 | 1,000,000 | `contains_many` over an int `array('q')` | 26.2 | 31.5 | 28.6 |
| pyribbon fp16 w128 | 1,000,000 | `contains_many` | 13 | 20.8 | 16 |
| pyribbon fp16 w128 | 1,000,000 | `contains_many` over an int `array('q')` | 15.9 | 29.2 | 20.6 |
| Xor8 | 1,000,000 | per-key loop | 1.46 | 1.46 | 1.45 |
| Xor16 | 1,000,000 | per-key loop | 1.45 | 1.46 | 1.45 |
| Fuse8 | 1,000,000 | per-key loop | 1.45 | 1.43 | 1.41 |
| Fuse16 | 1,000,000 | per-key loop | 1.43 | 1.45 | 1.44 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 3.29 | 3.69 | 3.48 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.72 | 3.67 | 3.13 |
| pyribbon fp8 | 10,000,000 | `contains_many` | 20.4 | 21.4 | 20.9 |
| pyribbon fp8 | 10,000,000 | `contains_many` over an int `array('q')` | 28.8 | 31.4 | 30.1 |
| pyribbon fp16 | 10,000,000 | `contains_many` | 8.96 | 19.4 | 12.2 |
| pyribbon fp16 | 10,000,000 | `contains_many` over an int `array('q')` | 10.2 | 27.2 | 14.9 |
| pyribbon fp8 w128 | 10,000,000 | `contains_many` | 15.2 | 19.2 | 17.1 |
| pyribbon fp8 w128 | 10,000,000 | `contains_many` over an int `array('q')` | 19.8 | 27.3 | 23 |
| pyribbon fp16 w128 | 10,000,000 | `contains_many` | 7.76 | 14.6 | 10.1 |
| pyribbon fp16 w128 | 10,000,000 | `contains_many` over an int `array('q')` | 8.69 | 18.3 | 11.8 |
| Xor8 | 10,000,000 | per-key loop | 1.31 | 1.31 | 1.31 |
| Xor16 | 10,000,000 | per-key loop | 1.3 | 1.3 | 1.3 |
| Fuse8 | 10,000,000 | per-key loop | 1.32 | 1.33 | 1.33 |
| Fuse16 | 10,000,000 | per-key loop | 1.31 | 1.3 | 1.31 |
| rbloom 2^-8 | 10,000,000 | per-key loop | 2.32 | 2.92 | 2.58 |
| rbloom 2^-16 | 10,000,000 | per-key loop | 1.58 | 2.74 | 2 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 1,000 | 85.7 [84.2, 89.6] build ns/key | 86.1 [85.7, 87.5] | 56 [55.1, 60.7] | 12.4 |
| rbloom 2^-16, builtin hash() | 1,000 | 145 [143, 150] build ns/key | 144 [144, 158] | 55.8 [55.6, 57.6] | 9.13 |
| pyfusefilter: Python hashing only | 1,000 | 233 [219, 331] build ns/key | 190 [189, 197] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 43 [42.4, 66.1] build ns/key | 123 [121, 149] | 121 [120, 123] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 43.8 [42.7, 45.4] build ns/key | 121 [120, 121] | 122 [120, 139] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 39.5 [38.8, 41.6] build ns/key | 121 [120, 140] | 123 [121, 125] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 40.2 [38.1, 41.8] build ns/key | 121 [121, 123] | 122 [120, 126] | n/a |
| rbloom: `hash_func` call only | 1,000 | n/a | 127 [124, 153] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000 | 78.5 [75.5, 81.3] build ns/key | 86.5 [85.7, 88] | 56 [55.7, 57.1] | 12.4 |
| rbloom 2^-16, builtin hash() | 10,000 | 135 [135, 141] build ns/key | 145 [143, 145] | 56.8 [56.2, 58.1] | 9.12 |
| pyfusefilter: Python hashing only | 10,000 | 201 [199, 202] build ns/key | 191 [190, 194] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.6 [31.1, 47.4] build ns/key | 122 [121, 125] | 121 [121, 159] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.1 [30.8, 33.1] build ns/key | 125 [121, 181] | 121 [120, 124] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 27.5 [27, 30.1] build ns/key | 121 [116, 121] | 121 [121, 123] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 27 [26.8, 27.3] build ns/key | 125 [121, 146] | 123 [120, 129] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 125 [124, 126] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 100,000 | 75.5 [75.2, 77] build ns/key | 87.2 [86.3, 91.6] | 58.9 [58.4, 59.6] | 12.1 |
| rbloom 2^-16, builtin hash() | 100,000 | 137 [136, 139] build ns/key | 150 [149, 151] | 63.9 [63, 65.6] | 8.37 |
| pyfusefilter: Python hashing only | 100,000 | 203 [201, 241] build ns/key | 193 [191, 207] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 76 [73, 82] build ns/key | 123 [123, 125] | 126 [123, 155] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 75.8 [72.4, 78.2] build ns/key | 125 [125, 126] | 126 [124, 160] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 27 [26.5, 27.5] build ns/key | 123 [122, 160] | 128 [118, 153] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 26.7 [26.3, 26.7] build ns/key | 125 [124, 126] | 126 [124, 127] | n/a |
| rbloom: `hash_func` call only | 100,000 | n/a | 121 [119, 159] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 80.5 [80, 86] build ns/key | 99.3 [98.2, 100] | 75.3 [73.9, 134] | 10.6 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 146 [141, 169] build ns/key | 164 [162, 206] | 79.5 [78.8, 82.2] | 7.96 |
| pyfusefilter: Python hashing only | 1,000,000 | 218 [215, 234] build ns/key | 190 [188, 191] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 87.3 [86.8, 94.2] build ns/key | 133 [132, 138] | 133 [132, 135] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 88.1 [86.7, 90.8] build ns/key | 139 [138, 189] | 137 [137, 138] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 37.6 [37.4, 40.3] build ns/key | 136 [131, 182] | 132 [131, 133] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 37.7 [37.3, 40.3] build ns/key | 137 [136, 138] | 137 [136, 143] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 124 [123, 144] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000,000 | 203 [202, 204] build ns/key | 213 [210, 246] | 139 [138, 196] | 5.48 |
| rbloom 2^-16, builtin hash() | 10,000,000 | 423 [422, 425] build ns/key | 411 [408, 506] | 162 [161, 164] | 3.4 |
| pyfusefilter: Python hashing only | 10,000,000 | 225 [225, 227] build ns/key | 190 [189, 201] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 100 [99.8, 100] build ns/key | 195 [194, 206] | 196 [194, 204] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 104 [104, 105] build ns/key | 212 [212, 215] | 213 [212, 219] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 54 [53.5, 55] build ns/key | 193 [190, 292] | 194 [190, 206] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 52.7 [52, 53.2] build ns/key | 203 [202, 217] | 204 [203, 231] | n/a |
| rbloom: `hash_func` call only | 10,000,000 | n/a | 127 [126, 136] | (same keys) | n/a |

## Results: str keys (`'user:00000000042'`, 16 characters)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 8.653 | 0.00394 [0.00388, 0.004] | 15,771 / 4,000,000 | 1.01 | 7.99 | 0.67 (8%) |
| pyribbon fp16 | 10,000 | 17.254 | 1.64e-05 [1.47e-05, 1.82e-05] | 327 / 20,000,000 | 1.07 | 15.90 | 1.35 (9%) |
| pyribbon fp8 w128 | 10,000 | 8.294 | 0.00398 [0.00391, 0.00404] | 15,904 / 4,000,000 | 1.02 | 7.97 | 0.32 (4%) |
| pyribbon fp16 w128 | 10,000 | 16.538 | 1.57e-05 [1.41e-05, 1.75e-05] | 314 / 20,000,000 | 1.03 | 15.96 | 0.58 (4%) |
| Xor8 | 10,000 | 9.883 | 0.00389 [0.00383, 0.00396] | 15,576 / 4,000,000 | 1.00 | 8.00 | 1.88 (23%) |
| Xor16 | 10,000 | 19.747 | 1.47e-05 [1.31e-05, 1.65e-05] | 294 / 20,000,000 | 0.96 | 16.05 | 3.69 (23%) |
| Fuse8 | 10,000 | 10.067 | 0.00392 [0.00386, 0.00398] | 15,685 / 4,000,000 | 1.00 | 7.99 | 2.07 (26%) |
| Fuse16 | 10,000 | 20.102 | 1.33e-05 [1.18e-05, 1.5e-05] | 266 / 20,000,000 | 0.87 | 16.20 | 3.90 (24%) |
| rbloom 2^-8 | 10,000 | 11.542 | 0.00396 [0.00389, 0.00402] | 15,823 / 4,000,000 | 1.01 | 7.98 | 3.56 (45%) |
| rbloom 2^-16 | 10,000 | 23.083 | 1.6e-05 [1.43e-05, 1.78e-05] | 319 / 20,000,000 | 1.05 | 15.94 | 7.15 (45%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,545 / 4,000,000 | 0.99 | 8.01 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.52e-05 [1.35e-05, 1.7e-05] | 303 / 20,000,000 | 0.99 | 16.01 | 1.98 (12%) |
| pyribbon fp8 w128 | 1,000,000 | 8.414 | 0.00388 [0.00381, 0.00394] | 15,501 / 4,000,000 | 0.99 | 8.01 | 0.40 (5%) |
| pyribbon fp16 w128 | 1,000,000 | 16.827 | 1.61e-05 [1.44e-05, 1.79e-05] | 321 / 20,000,000 | 1.05 | 15.93 | 0.90 (6%) |
| Xor8 | 1,000,000 | 9.840 | 0.00394 [0.00388, 0.004] | 15,766 / 4,000,000 | 1.01 | 7.99 | 1.85 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.52e-05 [1.35e-05, 1.7e-05] | 303 / 20,000,000 | 0.99 | 16.01 | 3.67 (23%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00392 [0.00386, 0.00398] | 15,671 / 4,000,000 | 1.00 | 8.00 | 1.05 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.69e-05 [1.52e-05, 1.88e-05] | 338 / 20,000,000 | 1.11 | 15.85 | 2.24 (14%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00393 [0.00387, 0.00399] | 15,714 / 4,000,000 | 1.01 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.55e-05 [1.39e-05, 1.74e-05] | 311 / 20,000,000 | 1.02 | 15.97 | 7.11 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 0.000566 [0.000562, 0.000585] | 56.6 [56.2, 58.5] |
| pyribbon fp16 | 10,000 | 0.000702 [0.000698, 0.000715] | 70.2 [69.8, 71.5] |
| pyribbon fp8 w128 | 10,000 | 0.000852 [0.000849, 0.000897] | 85.2 [84.9, 89.7] |
| pyribbon fp16 w128 | 10,000 | 0.00101 [0.00101, 0.00117] | 101 [101, 117] |
| Xor8 | 10,000 | 0.00444 [0.00431, 0.00457] | 444 [431, 457] |
| Xor16 | 10,000 | 0.00446 [0.00429, 0.00525] | 446 [429, 525] |
| Fuse8 | 10,000 | 0.00426 [0.00423, 0.00445] | 426 [423, 445] |
| Fuse16 | 10,000 | 0.0044 [0.00427, 0.00447] | 440 [427, 447] |
| rbloom 2^-8 | 10,000 | 0.00352 [0.00347, 0.00354] | 352 [347, 354] |
| rbloom 2^-16 | 10,000 | 0.00427 [0.00406, 0.00455] | 427 [406, 455] |
| pyribbon fp8 | 1,000,000 | 0.0575 [0.0575, 0.0587] | 57.5 [57.5, 58.7] |
| pyribbon fp16 | 1,000,000 | 0.0721 [0.0716, 0.0724] | 72.1 [71.6, 72.4] |
| pyribbon fp8 w128 | 1,000,000 | 0.0735 [0.0731, 0.0772] | 73.5 [73.1, 77.2] |
| pyribbon fp16 w128 | 1,000,000 | 0.0904 [0.09, 0.0952] | 90.4 [90, 95.2] |
| Xor8 | 1,000,000 | 0.523 [0.517, 0.531] | 523 [517, 531] |
| Xor16 | 1,000,000 | 0.527 [0.515, 0.531] | 527 [515, 531] |
| Fuse8 | 1,000,000 | 0.467 [0.464, 0.476] | 467 [464, 476] |
| Fuse16 | 1,000,000 | 0.474 [0.465, 0.482] | 474 [465, 482] |
| rbloom 2^-8 | 1,000,000 | 0.37 [0.363, 0.387] | 370 [363, 387] |
| rbloom 2^-16 | 1,000,000 | 0.426 [0.425, 0.447] | 426 [425, 447] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 39.9 [39.7, 44.4] | 42.1 [39.4, 67.2] | 47 |
| pyribbon fp16 | 10,000 | 54.3 [53.8, 55.1] | 40.4 [39.6, 41.9] | 61.4 |
| pyribbon fp8 w128 | 10,000 | 48.2 [47.9, 48.6] | 42 [42, 43] | 55.4 |
| pyribbon fp16 w128 | 10,000 | 70 [68.5, 70.9] | 42 [41.6, 42.3] | 77.1 |
| Xor8 | 10,000 | 598 [587, 630] | 574 [571, 605] | 605 |
| Xor16 | 10,000 | 588 [586, 648] | 598 [581, 643] | 595 |
| Fuse8 | 10,000 | 590 [572, 600] | 579 [575, 607] | 597 |
| Fuse16 | 10,000 | 585 [572, 614] | 576 [572, 832] | 592 |
| rbloom 2^-8 | 10,000 | 366 [363, 376] | 335 [333, 345] | 373 |
| rbloom 2^-16 | 10,000 | 422 [420, 432] | 339 [334, 577] | 430 |
| pyribbon fp8 | 1,000,000 | 51.2 [50.4, 52] | 50.9 [49.8, 65.9] | 58.5 |
| pyribbon fp16 | 1,000,000 | 66.4 [65.5, 68.5] | 52.1 [51.6, 54.2] | 73.6 |
| pyribbon fp8 w128 | 1,000,000 | 52.9 [52.7, 54.4] | 49.4 [49, 50.6] | 60 |
| pyribbon fp16 w128 | 1,000,000 | 74.7 [74.1, 82.9] | 51.2 [49.9, 57.5] | 81.9 |
| Xor8 | 1,000,000 | 594 [585, 654] | 586 [583, 621] | 601 |
| Xor16 | 1,000,000 | 595 [591, 678] | 614 [612, 631] | 602 |
| Fuse8 | 1,000,000 | 589 [587, 643] | 587 [585, 646] | 596 |
| Fuse16 | 1,000,000 | 592 [587, 609] | 595 [589, 700] | 602 |
| rbloom 2^-8 | 1,000,000 | 386 [383, 426] | 349 [348, 351] | 394 |
| rbloom 2^-16 | 1,000,000 | 443 [439, 513] | 355 [354, 356] | 450 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | `contains_many` | 22.8 | 23.5 | 23.2 |
| pyribbon fp16 | 10,000 | `contains_many` | 18.2 | 24 | 20.7 |
| pyribbon fp8 w128 | 10,000 | `contains_many` | 19.2 | 21.9 | 20.5 |
| pyribbon fp16 w128 | 10,000 | `contains_many` | 14.1 | 22.7 | 17.4 |
| Xor8 | 10,000 | per-key loop | 1.71 | 1.72 | 1.71 |
| Xor16 | 10,000 | per-key loop | 1.71 | 1.71 | 1.71 |
| Fuse8 | 10,000 | per-key loop | 1.7 | 1.7 | 1.7 |
| Fuse16 | 10,000 | per-key loop | 1.67 | 1.68 | 1.67 |
| rbloom 2^-8 | 10,000 | per-key loop | 2.6 | 2.88 | 2.74 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.27 | 2.86 | 2.49 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 21.7 | 23.2 | 22.4 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 16 | 23.6 | 19.2 |
| pyribbon fp8 w128 | 1,000,000 | `contains_many` | 19.1 | 22.4 | 20.6 |
| pyribbon fp16 w128 | 1,000,000 | `contains_many` | 13.2 | 21.8 | 16.4 |
| Xor8 | 1,000,000 | per-key loop | 1.63 | 1.68 | 1.64 |
| Xor16 | 1,000,000 | per-key loop | 1.63 | 1.63 | 1.63 |
| Fuse8 | 1,000,000 | per-key loop | 1.66 | 1.67 | 1.67 |
| Fuse16 | 1,000,000 | per-key loop | 1.64 | 1.68 | 1.66 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 2.53 | 2.79 | 2.65 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.21 | 2.77 | 2.46 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 10,000 | 71.8 [71.2, 77.4] build ns/key | 82 [81.5, 88.7] | 51.8 [51.4, 52.7] | 12.7 |
| rbloom 2^-16, builtin hash() | 10,000 | 131 [131, 136] build ns/key | 140 [139, 141] | 53.6 [52.5, 65.9] | 9.28 |
| pyfusefilter: Python hashing only | 10,000 | 130 [130, 133] build ns/key | 120 [119, 121] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.5 [31.3, 36.2] build ns/key | 128 [121, 138] | 122 [120, 127] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.2 [31.1, 33.6] build ns/key | 122 [120, 130] | 121 [120, 122] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28 [27.7, 28.8] build ns/key | 121 [120, 122] | 121 [120, 124] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 27.7 [27.5, 29.2] build ns/key | 125 [122, 136] | 122 [121, 124] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 206 [203, 209] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 78.1 [78, 85.3] build ns/key | 94.1 [91.6, 109] | 66.7 [65.5, 67.6] | 11.3 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 142 [142, 152] build ns/key | 157 [155, 170] | 75.2 [74.3, 91.7] | 8.17 |
| pyfusefilter: Python hashing only | 1,000,000 | 144 [142, 170] build ns/key | 121 [118, 126] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 88.7 [86.6, 97.4] build ns/key | 131 [129, 132] | 131 [128, 144] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 89.5 [87.7, 92.1] build ns/key | 138 [138, 140] | 138 [137, 180] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 37.8 [37.5, 39.1] build ns/key | 131 [129, 135] | 132 [129, 139] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 38.2 [37.8, 38.7] build ns/key | 137 [136, 167] | 136 [135, 140] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 204 [202, 205] | (same keys) | n/a |

## Notes and caveats

- Every filter is built from the same keys, and its FPR is measured on the same disjoint negative probes (4,000,000 for the 8-bit class, 20,000,000 for the 16-bit class). The probe keys differ from all members by construction. Fingerprint widths are discrete (8 or 16 bits) and Bloom filters are continuous, so each Bloom filter is sized for 2^-8 or 2^-16 and its FPR is then measured. Bits/key is reported with the measured FPR and with the overhead above the information-theoretic minimum of log2(1/FPR) bits/key, which lets filters with slightly different FPRs be compared.
- The intervals are 95% Wilson intervals for the stated number of probes. The 16-bit filters have only a few hundred expected false positives, so their FPR, and therefore their 'above minimum' column, is known only to roughly 5-10%.
- All measured FPRs are within 0.5x-2x of 2^-bits.
- `pyfusefilter` hashes every key in Python (`str(key).encode()` then `xxhash.xxh64_intdigest`) on every call and has no batch query. `pyribbon` hashes inside the C call. The headline numbers include these costs because a user pays them. The diagnostic tables separate the Python hashing from the filter probe. The probe-only rows call the library's C function through cffi with a pre-hashed key. The sum of the hashing and probe rows is a lower bound on the shipped call, and the remainder is Python call overhead. pyribbon cannot be split this way because its hash is part of the C call.
- rbloom hashes keys with Python's `hash()` unless it is given a `hash_func`. For `str` and `bytes` that hash is salted per process (and cached in the str object), so it cannot be persisted and it flatters repeated lookups of the same objects. The headline rbloom rows therefore pass an explicit deterministic `hash_func` (ints: a 64-bit multiplicative hash; str: xxh64 of the UTF-8 bytes). Its Python call cost is included in those rows and listed in the diagnostics. The 'builtin hash()' rows in the diagnostics use no callback and show rbloom's own probe cost. For int keys that is a sound configuration, so the win/loss summary counts it among the competitors. A check on 10,000 sequential ints and 1,000,000 probes (target 3.91e-03) gives FPR 4.68e-03 with the default hash() and 4.32e-03 with our hash_func, so rbloom's FPR is sane with either.
- Only pyribbon has a batch API (`contains_many`). For every other library the batch figure is a per-key list comprehension, `[k in f for k in keys]`, marked as such in the table. The 50/50 mix is the throughput of one member batch plus one non-member batch.
- Single-query latency is measured with a tight Python `for` loop over 100,000 random member keys (sampled with replacement) or non-member keys. The same loop without the call is timed in the same repeat and subtracted (median 6.66 ns per empty iteration here). What remains still includes the `k in f` bytecodes, a few ns. The unsubtracted figure is in the last column.
- Timing uses `time.perf_counter_ns` with GC disabled while timed and one warm-up pass. The figures are the median and min/max of 7 repeats (3 at n = 10^7, with no warm-up build there). Keys are generated before timing. Build time includes allocation and hashing but not key generation.
- `int` keys are distinct pseudo-random 63-bit integers from a fixed-seed bijective mixer. `str` keys are `user:` plus 11 digits, with members 0..n-1 and probes from 10^10 upwards. Query keys are fresh objects created in query order, so members and non-members have the same memory layout, and they are the same objects in every repeat (CPython caches a str's hash, which only matters for rbloom's builtin hash rows).
- Numbers are comparable between libraries within this run and not across machines. A `powersave` or `ondemand` governor adds noise. Run on an otherwise idle machine, with turbo and the governor fixed if you can.
