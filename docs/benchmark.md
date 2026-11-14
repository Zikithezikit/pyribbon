# pyribbon benchmark

## Machine and software

- CPU: Intel Core i7-7700 CPU @ 3.60GHz
- Logical CPUs: 8, benchmark pinned to CPU 7
- Frequency scaling governor: powersave
- CPU frequency: 4.19 GHz at start, max 4.20 GHz, turbo enabled
- OS / kernel: Linux 7.0.0-43-generic (Linux-7.0.0-43-generic-x86_64-with-glibc2.43)
- Python: CPython 3.14.4, built with GCC 15.2.0
- Python build flags: CC=x86_64-linux-gnu-gcc; CFLAGS=-fno-strict-overflow -Wsign-compare -DNDEBUG -g -O2 -Wall
- pyribbon extension: _ribbon.abi3.so; compiler recorded in the binary: GCC: (Ubuntu 15.2.0-16ubuntu1) 15.2.0
- pyribbon build flags: setup.py adds none (/std:c11 on Windows only): the interpreter's CFLAGS above are used
- pyribbon version: 0.1.1
- pyfusefilter version: 1.3.2
- rbloom version: 1.5.4
- Other packages: xxhash 4.1.0, cffi 2.1.1, numpy 2.5.4, matplotlib 3.11.2

## Run

- Date: 2026-11-14T06:42:36+02:00
- Command: `python benchmarks/bench.py --plot docs/benchmark.png --table docs/benchmark.md --json docs/benchmark.json`
- Pinning: CPU 7
- Key sizes (int): 1,000, 10,000, 100,000, 1,000,000, 10,000,000
- Key sizes (str): 10,000, 1,000,000
- Repeats: 7 (at most 3 at n >= 10,000,000); statistics are median and min/max
- Query set: 100,000 keys per loop/batch
- FPR probes: 4,000,000 (8-bit class), 20,000,000 (16-bit class), in chunks of 1,000,000
- Seed: 20261112
- Mode: full
- Total run time: 561 s

## Where pyribbon wins and loses (int keys, n = 10,000,000)

| Class | Metric | pyribbon | Best other | Delta | Verdict |
| --- | --- | ---: | ---: | ---: | ---: |
| 8-bit | bits/key | 9.19 | 9.02 (Fuse8) | +2% | **pyribbon behind** |
| 8-bit | bits/key above log2(1/FPR) | 1.18 | 1.00 (Fuse8) | +17% | **pyribbon behind** |
| 8-bit | build ns/key | 77 | 212 (rbloom 2^-8, builtin hash()) | -64% | pyribbon ahead |
| 8-bit | `in` member ns | 87 | 221 (rbloom 2^-8, builtin hash()) | -61% | pyribbon ahead |
| 8-bit | `in` non-member ns | 89 | 141 (rbloom 2^-8, builtin hash()) | -37% | pyribbon ahead |
| 8-bit | batch Mkeys/s (50/50 mix) | 18.06 | 5.17 (rbloom 2^-8, builtin hash()) | +249% | pyribbon ahead |
| 16-bit | bits/key | 18.39 | 18.04 (Fuse16) | +2% | **pyribbon behind** |
| 16-bit | bits/key above log2(1/FPR) | 2.36 | 1.95 (Fuse16) | +21% | **pyribbon behind** |
| 16-bit | build ns/key | 92 | 447 (rbloom 2^-16, builtin hash()) | -80% | pyribbon ahead |
| 16-bit | `in` member ns | 136 | 435 (rbloom 2^-16, builtin hash()) | -69% | pyribbon ahead |
| 16-bit | `in` non-member ns | 108 | 163 (rbloom 2^-16, builtin hash()) | -34% | pyribbon ahead |
| 16-bit | batch Mkeys/s (50/50 mix) | 11.05 | 3.20 (rbloom 2^-16, builtin hash()) | +245% | pyribbon ahead |

Delta is relative to the best other filter of the same fingerprint class, including rbloom with its builtin `hash()`; a negative delta means pyribbon is lower. Lower is better except for batch throughput. The 'above log2(1/FPR)' rows move with the measured FPR, whose uncertainty is in the notes. The batch row compares `contains_many` with the other libraries' per-key loop, because none of them has a batch API. The table is computed from the raw results of this run.

## Results: int keys (pseudo-random 63-bit)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 9.216 | 0.00388 [0.00382, 0.00394] | 15,502 / 4,000,000 | 0.99 | 8.01 | 1.20 (15%) |
| pyribbon fp16 | 1,000 | 17.920 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 1.98 (12%) |
| Xor8 | 1,000 | 10.272 | 0.00384 [0.00378, 0.0039] | 15,361 / 4,000,000 | 0.98 | 8.02 | 2.25 (28%) |
| Xor16 | 1,000 | 20.352 | 1.47e-05 [1.32e-05, 1.65e-05] | 295 / 20,000,000 | 0.97 | 16.05 | 4.30 (27%) |
| Fuse8 | 1,000 | 11.584 | 0.00385 [0.00379, 0.00391] | 15,402 / 4,000,000 | 0.99 | 8.02 | 3.56 (44%) |
| Fuse16 | 1,000 | 22.848 | 1.53e-05 [1.37e-05, 1.71e-05] | 306 / 20,000,000 | 1.00 | 16.00 | 6.85 (43%) |
| rbloom 2^-8 | 1,000 | 11.544 | 0.00394 [0.00387, 0.004] | 15,741 / 4,000,000 | 1.01 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 1,000 | 23.088 | 1.78e-05 [1.6e-05, 1.97e-05] | 356 / 20,000,000 | 1.17 | 15.78 | 7.31 (46%) |
| pyribbon fp8 | 10,000 | 8.653 | 0.00389 [0.00383, 0.00395] | 15,564 / 4,000,000 | 1.00 | 8.01 | 0.65 (8%) |
| pyribbon fp16 | 10,000 | 17.254 | 1.5e-05 [1.34e-05, 1.68e-05] | 300 / 20,000,000 | 0.98 | 16.02 | 1.23 (8%) |
| Xor8 | 10,000 | 9.883 | 0.00391 [0.00385, 0.00397] | 15,638 / 4,000,000 | 1.00 | 8.00 | 1.88 (24%) |
| Xor16 | 10,000 | 19.747 | 1.4e-05 [1.25e-05, 1.57e-05] | 280 / 20,000,000 | 0.92 | 16.12 | 3.62 (22%) |
| Fuse8 | 10,000 | 10.067 | 0.00393 [0.00387, 0.00399] | 15,711 / 4,000,000 | 1.01 | 7.99 | 2.08 (26%) |
| Fuse16 | 10,000 | 20.102 | 1.65e-05 [1.48e-05, 1.83e-05] | 329 / 20,000,000 | 1.08 | 15.89 | 4.21 (26%) |
| rbloom 2^-8 | 10,000 | 11.542 | 0.00396 [0.0039, 0.00402] | 15,832 / 4,000,000 | 1.01 | 7.98 | 3.56 (45%) |
| rbloom 2^-16 | 10,000 | 23.083 | 1.52e-05 [1.36e-05, 1.7e-05] | 304 / 20,000,000 | 1.00 | 16.01 | 7.08 (44%) |
| pyribbon fp8 | 100,000 | 8.791 | 0.00391 [0.00384, 0.00397] | 15,621 / 4,000,000 | 1.00 | 8.00 | 0.79 (10%) |
| pyribbon fp16 | 100,000 | 17.577 | 1.38e-05 [1.23e-05, 1.55e-05] | 276 / 20,000,000 | 0.90 | 16.14 | 1.43 (9%) |
| Xor8 | 100,000 | 9.844 | 0.00391 [0.00385, 0.00397] | 15,639 / 4,000,000 | 1.00 | 8.00 | 1.85 (23%) |
| Xor16 | 100,000 | 19.687 | 1.51e-05 [1.35e-05, 1.69e-05] | 302 / 20,000,000 | 0.99 | 16.02 | 3.67 (23%) |
| Fuse8 | 100,000 | 9.506 | 0.00388 [0.00382, 0.00394] | 15,520 / 4,000,000 | 0.99 | 8.01 | 1.50 (19%) |
| Fuse16 | 100,000 | 19.009 | 1.52e-05 [1.36e-05, 1.7e-05] | 304 / 20,000,000 | 1.00 | 16.01 | 3.00 (19%) |
| rbloom 2^-8 | 100,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,663 / 4,000,000 | 1.00 | 8.00 | 3.55 (44%) |
| rbloom 2^-16 | 100,000 | 23.083 | 1.5e-05 [1.34e-05, 1.68e-05] | 301 / 20,000,000 | 0.99 | 16.02 | 7.06 (44%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,571 / 4,000,000 | 1.00 | 8.00 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.68e-05 [1.5e-05, 1.86e-05] | 335 / 20,000,000 | 1.10 | 15.87 | 2.12 (13%) |
| Xor8 | 1,000,000 | 9.840 | 0.00389 [0.00383, 0.00396] | 15,579 / 4,000,000 | 1.00 | 8.00 | 1.84 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.45e-05 [1.29e-05, 1.63e-05] | 290 / 20,000,000 | 0.95 | 16.07 | 3.61 (22%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00385 [0.00379, 0.00391] | 15,394 / 4,000,000 | 0.99 | 8.02 | 1.02 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.49e-05 [1.33e-05, 1.66e-05] | 297 / 20,000,000 | 0.97 | 16.04 | 2.05 (13%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00387 [0.00381, 0.00393] | 15,483 / 4,000,000 | 0.99 | 8.01 | 3.53 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 7.14 (45%) |
| pyribbon fp8 | 10,000,000 | 9.195 | 0.00386 [0.0038, 0.00392] | 15,440 / 4,000,000 | 0.99 | 8.02 | 1.18 (15%) |
| pyribbon fp16 | 10,000,000 | 18.390 | 1.49e-05 [1.33e-05, 1.67e-05] | 298 / 20,000,000 | 0.98 | 16.03 | 2.36 (15%) |
| Xor8 | 10,000,000 | 9.840 | 0.00392 [0.00386, 0.00398] | 15,681 / 4,000,000 | 1.00 | 7.99 | 1.85 (23%) |
| Xor16 | 10,000,000 | 19.680 | 1.57e-05 [1.4e-05, 1.75e-05] | 313 / 20,000,000 | 1.03 | 15.96 | 3.72 (23%) |
| Fuse8 | 10,000,000 | 9.018 | 0.00387 [0.00381, 0.00393] | 15,466 / 4,000,000 | 0.99 | 8.01 | 1.00 (13%) |
| Fuse16 | 10,000,000 | 18.036 | 1.44e-05 [1.28e-05, 1.62e-05] | 288 / 20,000,000 | 0.94 | 16.08 | 1.95 (12%) |
| rbloom 2^-8 | 10,000,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,690 / 4,000,000 | 1.00 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 10,000,000 | 23.083 | 1.62e-05 [1.45e-05, 1.81e-05] | 324 / 20,000,000 | 1.06 | 15.91 | 7.17 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 6.86e-05 [6.82e-05, 7.19e-05] | 68.6 [68.2, 71.9] |
| pyribbon fp16 | 1,000 | 8.34e-05 [8.18e-05, 9.7e-05] | 83.4 [81.8, 97] |
| Xor8 | 1,000 | 0.00062 [0.000607, 0.000669] | 620 [607, 669] |
| Xor16 | 1,000 | 0.000629 [0.0006, 0.000643] | 629 [600, 643] |
| Fuse8 | 1,000 | 0.000522 [0.000516, 0.000551] | 522 [516, 551] |
| Fuse16 | 1,000 | 0.000523 [0.000519, 0.000568] | 523 [519, 568] |
| rbloom 2^-8 | 1,000 | 0.000278 [0.000276, 0.000288] | 278 [276, 288] |
| rbloom 2^-16 | 1,000 | 0.000337 [0.000334, 0.000369] | 337 [334, 369] |
| pyribbon fp8 | 10,000 | 0.000572 [0.000564, 0.000632] | 57.2 [56.4, 63.2] |
| pyribbon fp16 | 10,000 | 0.000757 [0.000713, 0.000961] | 75.7 [71.3, 96.1] |
| Xor8 | 10,000 | 0.00499 [0.00496, 0.00527] | 499 [496, 527] |
| Xor16 | 10,000 | 0.00512 [0.00495, 0.0056] | 512 [495, 560] |
| Fuse8 | 10,000 | 0.00496 [0.00488, 0.0052] | 496 [488, 520] |
| Fuse16 | 10,000 | 0.0052 [0.00514, 0.00541] | 520 [514, 541] |
| rbloom 2^-8 | 10,000 | 0.00267 [0.00264, 0.0027] | 267 [264, 270] |
| rbloom 2^-16 | 10,000 | 0.00328 [0.00324, 0.00339] | 328 [324, 339] |
| pyribbon fp8 | 100,000 | 0.00564 [0.00557, 0.00575] | 56.4 [55.7, 57.5] |
| pyribbon fp16 | 100,000 | 0.00703 [0.00694, 0.00709] | 70.3 [69.4, 70.9] |
| Xor8 | 100,000 | 0.0557 [0.0555, 0.0561] | 557 [555, 561] |
| Xor16 | 100,000 | 0.0557 [0.0553, 0.059] | 557 [553, 590] |
| Fuse8 | 100,000 | 0.0521 [0.0505, 0.0581] | 521 [505, 581] |
| Fuse16 | 100,000 | 0.0508 [0.0506, 0.0545] | 508 [506, 545] |
| rbloom 2^-8 | 100,000 | 0.0265 [0.0262, 0.0303] | 265 [262, 303] |
| rbloom 2^-16 | 100,000 | 0.0335 [0.0329, 0.0357] | 335 [329, 357] |
| pyribbon fp8 | 1,000,000 | 0.0585 [0.058, 0.0677] | 58.5 [58, 67.7] |
| pyribbon fp16 | 1,000,000 | 0.0722 [0.072, 0.0749] | 72.2 [72, 74.9] |
| Xor8 | 1,000,000 | 0.592 [0.569, 0.599] | 592 [569, 599] |
| Xor16 | 1,000,000 | 0.598 [0.586, 0.619] | 598 [586, 619] |
| Fuse8 | 1,000,000 | 0.541 [0.533, 0.554] | 541 [533, 554] |
| Fuse16 | 1,000,000 | 0.543 [0.532, 0.587] | 543 [532, 587] |
| rbloom 2^-8 | 1,000,000 | 0.273 [0.272, 0.29] | 273 [272, 290] |
| rbloom 2^-16 | 1,000,000 | 0.337 [0.333, 0.356] | 337 [333, 356] |
| pyribbon fp8 | 10,000,000 | 0.766 [0.763, 0.768] | 76.6 [76.3, 76.8] |
| pyribbon fp16 | 10,000,000 | 0.915 [0.914, 0.923] | 91.5 [91.4, 92.3] |
| Xor8 | 10,000,000 | 6.2 [6.19, 6.22] | 620 [619, 622] |
| Xor16 | 10,000,000 | 6.24 [6.23, 6.29] | 624 [623, 629] |
| Fuse8 | 10,000,000 | 5.76 [5.71, 5.78] | 576 [571, 578] |
| Fuse16 | 10,000,000 | 5.71 [5.71, 5.72] | 571 [571, 572] |
| rbloom 2^-8 | 10,000,000 | 4.21 [4.2, 4.25] | 421 [420, 425] |
| rbloom 2^-16 | 10,000,000 | 6.45 [6.43, 6.49] | 645 [643, 649] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 46.1 [45.6, 47.2] | 39.6 [38.9, 41.1] | 53 |
| pyribbon fp16 | 1,000 | 65.5 [64.4, 67.8] | 40.5 [39.3, 50.3] | 72.2 |
| Xor8 | 1,000 | 686 [654, 745] | 662 [656, 728] | 694 |
| Xor16 | 1,000 | 650 [639, 659] | 666 [641, 747] | 657 |
| Fuse8 | 1,000 | 660 [647, 1.46e+03] | 659 [653, 670] | 667 |
| Fuse16 | 1,000 | 645 [643, 658] | 652 [643, 730] | 652 |
| rbloom 2^-8 | 1,000 | 283 [281, 341] | 262 [253, 296] | 290 |
| rbloom 2^-16 | 1,000 | 342 [339, 359] | 253 [252, 256] | 348 |
| pyribbon fp8 | 10,000 | 45.8 [44.9, 46.6] | 40 [39.2, 40.6] | 52.4 |
| pyribbon fp16 | 10,000 | 65.6 [64.5, 67.5] | 40.3 [39.4, 41.1] | 72.4 |
| Xor8 | 10,000 | 654 [638, 713] | 642 [637, 653] | 660 |
| Xor16 | 10,000 | 660 [644, 795] | 654 [643, 722] | 666 |
| Fuse8 | 10,000 | 642 [640, 774] | 641 [639, 695] | 649 |
| Fuse16 | 10,000 | 643 [639, 678] | 644 [641, 710] | 650 |
| rbloom 2^-8 | 10,000 | 287 [285, 327] | 256 [253, 312] | 294 |
| rbloom 2^-16 | 10,000 | 344 [342, 365] | 255 [255, 281] | 351 |
| pyribbon fp8 | 100,000 | 45.9 [45.1, 49.8] | 43.9 [42.4, 64.9] | 53 |
| pyribbon fp16 | 100,000 | 69.1 [65.6, 71.1] | 44.2 [43.2, 55.8] | 76 |
| Xor8 | 100,000 | 651 [643, 931] | 657 [654, 667] | 658 |
| Xor16 | 100,000 | 653 [645, 711] | 671 [651, 687] | 660 |
| Fuse8 | 100,000 | 646 [643, 717] | 646 [641, 669] | 654 |
| Fuse16 | 100,000 | 657 [650, 697] | 649 [646, 687] | 663 |
| rbloom 2^-8 | 100,000 | 283 [281, 299] | 255 [252, 257] | 290 |
| rbloom 2^-16 | 100,000 | 346 [345, 368] | 259 [257, 286] | 353 |
| pyribbon fp8 | 1,000,000 | 52.2 [51.3, 53.3] | 50.7 [49.9, 51.5] | 59.1 |
| pyribbon fp16 | 1,000,000 | 73 [72.5, 102] | 53.2 [51.4, 55] | 79.9 |
| Xor8 | 1,000,000 | 693 [660, 726] | 664 [657, 716] | 700 |
| Xor16 | 1,000,000 | 662 [658, 691] | 684 [668, 759] | 669 |
| Fuse8 | 1,000,000 | 657 [654, 702] | 681 [655, 751] | 664 |
| Fuse16 | 1,000,000 | 663 [655, 718] | 662 [659, 776] | 669 |
| rbloom 2^-8 | 1,000,000 | 295 [293, 296] | 269 [263, 301] | 302 |
| rbloom 2^-16 | 1,000,000 | 368 [358, 410] | 278 [265, 310] | 374 |
| pyribbon fp8 | 10,000,000 | 87.2 [86.7, 91] | 88.9 [86.6, 134] | 93.9 |
| pyribbon fp16 | 10,000,000 | 136 [133, 165] | 108 [106, 112] | 143 |
| Xor8 | 10,000,000 | 740 [733, 909] | 737 [728, 802] | 747 |
| Xor16 | 10,000,000 | 826 [770, 947] | 774 [756, 834] | 833 |
| Fuse8 | 10,000,000 | 733 [725, 818] | 731 [727, 793] | 740 |
| Fuse16 | 10,000,000 | 742 [737, 850] | 739 [737, 769] | 749 |
| rbloom 2^-8 | 10,000,000 | 422 [417, 539] | 340 [336, 413] | 428 |
| rbloom 2^-16 | 10,000,000 | 632 [629, 648] | 363 [356, 390] | 639 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | `contains_many` | 20.2 | 22.4 | 21.4 |
| pyribbon fp8 | 1,000 | `contains_many` over an int `array('q')` | 28.1 | 33.4 | 30.5 |
| pyribbon fp16 | 1,000 | `contains_many` | 14.5 | 23 | 17.8 |
| pyribbon fp16 | 1,000 | `contains_many` over an int `array('q')` | 18.1 | 33.3 | 23.5 |
| Xor8 | 1,000 | per-key loop | 1.48 | 1.49 | 1.48 |
| Xor16 | 1,000 | per-key loop | 1.52 | 1.52 | 1.5 |
| Fuse8 | 1,000 | per-key loop | 1.44 | 1.5 | 1.47 |
| Fuse16 | 1,000 | per-key loop | 1.52 | 1.52 | 1.52 |
| rbloom 2^-8 | 1,000 | per-key loop | 3.37 | 3.77 | 3.56 |
| rbloom 2^-16 | 1,000 | per-key loop | 2.83 | 3.79 | 3.23 |
| pyribbon fp8 | 10,000 | `contains_many` | 20.3 | 23 | 21.6 |
| pyribbon fp8 | 10,000 | `contains_many` over an int `array('q')` | 28.2 | 33.6 | 30.5 |
| pyribbon fp16 | 10,000 | `contains_many` | 14.6 | 23 | 17.9 |
| pyribbon fp16 | 10,000 | `contains_many` over an int `array('q')` | 18.3 | 33.5 | 23.7 |
| Xor8 | 10,000 | per-key loop | 1.53 | 1.54 | 1.53 |
| Xor16 | 10,000 | per-key loop | 1.52 | 1.52 | 1.51 |
| Fuse8 | 10,000 | per-key loop | 1.53 | 1.53 | 1.53 |
| Fuse16 | 10,000 | per-key loop | 1.53 | 1.53 | 1.53 |
| rbloom 2^-8 | 10,000 | per-key loop | 3.36 | 3.77 | 3.54 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.82 | 3.77 | 3.23 |
| pyribbon fp8 | 100,000 | `contains_many` | 20.3 | 22.8 | 21.6 |
| pyribbon fp8 | 100,000 | `contains_many` over an int `array('q')` | 28.1 | 33.3 | 30.5 |
| pyribbon fp16 | 100,000 | `contains_many` | 14.4 | 23.1 | 17.8 |
| pyribbon fp16 | 100,000 | `contains_many` over an int `array('q')` | 18 | 32.3 | 23.4 |
| Xor8 | 100,000 | per-key loop | 1.52 | 1.51 | 1.5 |
| Xor16 | 100,000 | per-key loop | 1.51 | 1.49 | 1.5 |
| Fuse8 | 100,000 | per-key loop | 1.51 | 1.52 | 1.52 |
| Fuse16 | 100,000 | per-key loop | 1.51 | 1.51 | 1.49 |
| rbloom 2^-8 | 100,000 | per-key loop | 3.38 | 3.74 | 3.54 |
| rbloom 2^-16 | 100,000 | per-key loop | 2.73 | 3.69 | 3.14 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 19.3 | 22 | 20.6 |
| pyribbon fp8 | 1,000,000 | `contains_many` over an int `array('q')` | 27 | 32.1 | 29.4 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 13.8 | 21.9 | 17 |
| pyribbon fp16 | 1,000,000 | `contains_many` over an int `array('q')` | 16.9 | 31.3 | 22 |
| Xor8 | 1,000,000 | per-key loop | 1.49 | 1.5 | 1.49 |
| Xor16 | 1,000,000 | per-key loop | 1.48 | 1.48 | 1.47 |
| Fuse8 | 1,000,000 | per-key loop | 1.47 | 1.49 | 1.48 |
| Fuse16 | 1,000,000 | per-key loop | 1.44 | 1.46 | 1.46 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 3.25 | 3.66 | 3.44 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.72 | 3.6 | 3.05 |
| pyribbon fp8 | 10,000,000 | `contains_many` | 15.8 | 21 | 18.1 |
| pyribbon fp8 | 10,000,000 | `contains_many` over an int `array('q')` | 20.8 | 30 | 24.6 |
| pyribbon fp16 | 10,000,000 | `contains_many` | 8.27 | 16.7 | 11 |
| pyribbon fp16 | 10,000,000 | `contains_many` over an int `array('q')` | 9.43 | 21.5 | 13.1 |
| Xor8 | 10,000,000 | per-key loop | 1.32 | 1.34 | 1.33 |
| Xor16 | 10,000,000 | per-key loop | 1.27 | 1.29 | 1.28 |
| Fuse8 | 10,000,000 | per-key loop | 1.33 | 1.35 | 1.34 |
| Fuse16 | 10,000,000 | per-key loop | 1.32 | 1.32 | 1.31 |
| rbloom 2^-8 | 10,000,000 | per-key loop | 2.31 | 2.9 | 2.57 |
| rbloom 2^-16 | 10,000,000 | per-key loop | 1.55 | 2.73 | 1.98 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 1,000 | 84 [83.1, 91.8] build ns/key | 88.2 [86, 93.7] | 60 [55.8, 62.3] | 12.4 |
| rbloom 2^-16, builtin hash() | 1,000 | 145 [144, 151] build ns/key | 145 [144, 147] | 56.2 [55.3, 57.1] | 8.79 |
| pyfusefilter: Python hashing only | 1,000 | 215 [211, 218] build ns/key | 191 [190, 194] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 45.2 [43.3, 79.3] build ns/key | 123 [121, 137] | 123 [122, 132] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 43.2 [41.6, 58.1] build ns/key | 120 [119, 124] | 121 [119, 121] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 40.1 [39.2, 53.2] build ns/key | 121 [120, 124] | 125 [120, 131] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 40 [39.5, 40.7] build ns/key | 128 [114, 129] | 122 [121, 128] | n/a |
| rbloom: `hash_func` call only | 1,000 | n/a | 125 [124, 159] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000 | 75.8 [75.5, 80.4] build ns/key | 86.3 [85.6, 95.3] | 57.5 [55.8, 59] | 12.3 |
| rbloom 2^-16, builtin hash() | 10,000 | 138 [135, 143] build ns/key | 147 [145, 172] | 56.6 [55.8, 57.3] | 8.58 |
| pyfusefilter: Python hashing only | 10,000 | 203 [200, 209] build ns/key | 192 [190, 193] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.7 [31.1, 46.7] build ns/key | 122 [121, 134] | 126 [122, 135] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.3 [30.9, 33.6] build ns/key | 122 [120, 123] | 122 [120, 135] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28.7 [27.2, 31.5] build ns/key | 122 [121, 129] | 122 [121, 125] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 27.3 [27.1, 28.3] build ns/key | 122 [121, 126] | 122 [121, 123] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 127 [125, 130] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 100,000 | 75.8 [75.1, 76.1] build ns/key | 87.3 [86.8, 88.9] | 59.4 [58.6, 64.3] | 12 |
| rbloom 2^-16, builtin hash() | 100,000 | 137 [137, 139] build ns/key | 150 [148, 152] | 63.3 [62.9, 64.1] | 7.87 |
| pyfusefilter: Python hashing only | 100,000 | 206 [201, 247] build ns/key | 193 [191, 199] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 72.4 [69.8, 89.9] build ns/key | 123 [122, 124] | 124 [123, 127] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 72.2 [69.2, 73.6] build ns/key | 126 [124, 161] | 126 [124, 138] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 27.5 [26.5, 39.1] build ns/key | 125 [123, 125] | 125 [123, 128] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 26.9 [26.4, 27.6] build ns/key | 128 [127, 129] | 127 [126, 130] | n/a |
| rbloom: `hash_func` call only | 100,000 | n/a | 120 [119, 126] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 81.2 [79.5, 87] build ns/key | 98.6 [98, 101] | 74.2 [73.1, 76] | 10.6 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 139 [139, 150] build ns/key | 159 [158, 160] | 89.4 [78.1, 127] | 7.75 |
| pyfusefilter: Python hashing only | 1,000,000 | 216 [214, 224] build ns/key | 192 [192, 208] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 90 [87.4, 97.5] build ns/key | 135 [134, 152] | 135 [135, 170] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 90.5 [88.9, 96.8] build ns/key | 136 [135, 142] | 139 [135, 202] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 38.2 [37.7, 39.3] build ns/key | 131 [131, 135] | 137 [133, 187] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 38.2 [37.5, 40.5] build ns/key | 140 [137, 149] | 136 [136, 138] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 120 [120, 121] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000,000 | 212 [212, 219] build ns/key | 221 [217, 224] | 141 [140, 161] | 5.17 |
| rbloom 2^-16, builtin hash() | 10,000,000 | 447 [445, 452] build ns/key | 435 [432, 465] | 163 [162, 193] | 3.2 |
| pyfusefilter: Python hashing only | 10,000,000 | 226 [225, 227] build ns/key | 193 [189, 202] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 102 [101, 104] build ns/key | 199 [198, 210] | 207 [200, 236] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 106 [105, 107] build ns/key | 216 [214, 224] | 216 [215, 218] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 54.7 [53.7, 54.8] build ns/key | 196 [193, 280] | 195 [193, 240] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 52.7 [52.6, 53.7] build ns/key | 215 [213, 241] | 213 [211, 214] | n/a |
| rbloom: `hash_func` call only | 10,000,000 | n/a | 120 [119, 122] | (same keys) | n/a |

## Results: str keys (`'user:00000000042'`, 16 characters)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 8.653 | 0.00394 [0.00388, 0.004] | 15,771 / 4,000,000 | 1.01 | 7.99 | 0.67 (8%) |
| pyribbon fp16 | 10,000 | 17.254 | 1.64e-05 [1.47e-05, 1.82e-05] | 327 / 20,000,000 | 1.07 | 15.90 | 1.35 (9%) |
| Xor8 | 10,000 | 9.883 | 0.00392 [0.00386, 0.00398] | 15,685 / 4,000,000 | 1.00 | 7.99 | 1.89 (24%) |
| Xor16 | 10,000 | 19.747 | 1.54e-05 [1.38e-05, 1.73e-05] | 309 / 20,000,000 | 1.01 | 15.98 | 3.77 (24%) |
| Fuse8 | 10,000 | 10.067 | 0.00392 [0.00386, 0.00398] | 15,685 / 4,000,000 | 1.00 | 7.99 | 2.07 (26%) |
| Fuse16 | 10,000 | 20.102 | 1.33e-05 [1.18e-05, 1.5e-05] | 266 / 20,000,000 | 0.87 | 16.20 | 3.90 (24%) |
| rbloom 2^-8 | 10,000 | 11.542 | 0.00396 [0.00389, 0.00402] | 15,823 / 4,000,000 | 1.01 | 7.98 | 3.56 (45%) |
| rbloom 2^-16 | 10,000 | 23.083 | 1.6e-05 [1.43e-05, 1.78e-05] | 319 / 20,000,000 | 1.05 | 15.94 | 7.15 (45%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,545 / 4,000,000 | 0.99 | 8.01 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.52e-05 [1.35e-05, 1.7e-05] | 303 / 20,000,000 | 0.99 | 16.01 | 1.98 (12%) |
| Xor8 | 1,000,000 | 9.840 | 0.00396 [0.0039, 0.00402] | 15,833 / 4,000,000 | 1.01 | 7.98 | 1.86 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.57e-05 [1.41e-05, 1.76e-05] | 315 / 20,000,000 | 1.03 | 15.95 | 3.73 (23%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00392 [0.00386, 0.00398] | 15,671 / 4,000,000 | 1.00 | 8.00 | 1.05 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.69e-05 [1.52e-05, 1.88e-05] | 338 / 20,000,000 | 1.11 | 15.85 | 2.24 (14%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00393 [0.00387, 0.00399] | 15,714 / 4,000,000 | 1.01 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.55e-05 [1.39e-05, 1.74e-05] | 311 / 20,000,000 | 1.02 | 15.97 | 7.11 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 0.000563 [0.000558, 0.000592] | 56.3 [55.8, 59.2] |
| pyribbon fp16 | 10,000 | 0.000696 [0.000688, 0.000723] | 69.6 [68.8, 72.3] |
| Xor8 | 10,000 | 0.00433 [0.0043, 0.00439] | 433 [430, 439] |
| Xor16 | 10,000 | 0.00437 [0.00427, 0.00458] | 437 [427, 458] |
| Fuse8 | 10,000 | 0.00449 [0.00433, 0.00479] | 449 [433, 479] |
| Fuse16 | 10,000 | 0.00434 [0.00427, 0.00439] | 434 [427, 439] |
| rbloom 2^-8 | 10,000 | 0.00358 [0.00348, 0.00391] | 358 [348, 391] |
| rbloom 2^-16 | 10,000 | 0.00412 [0.00407, 0.00421] | 412 [407, 421] |
| pyribbon fp8 | 1,000,000 | 0.0575 [0.0572, 0.0595] | 57.5 [57.2, 59.5] |
| pyribbon fp16 | 1,000,000 | 0.0714 [0.0709, 0.0722] | 71.4 [70.9, 72.2] |
| Xor8 | 1,000,000 | 0.532 [0.519, 0.554] | 532 [519, 554] |
| Xor16 | 1,000,000 | 0.528 [0.522, 0.53] | 528 [522, 530] |
| Fuse8 | 1,000,000 | 0.471 [0.466, 0.478] | 471 [466, 478] |
| Fuse16 | 1,000,000 | 0.48 [0.468, 0.485] | 480 [468, 485] |
| rbloom 2^-8 | 1,000,000 | 0.369 [0.366, 0.383] | 369 [366, 383] |
| rbloom 2^-16 | 1,000,000 | 0.436 [0.427, 0.447] | 436 [427, 447] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 48.3 [46.3, 51.2] | 40.6 [40.2, 42.1] | 55.8 |
| pyribbon fp16 | 10,000 | 65.6 [64.3, 67.2] | 41.1 [40.3, 58.3] | 73.1 |
| Xor8 | 10,000 | 573 [570, 597] | 588 [568, 637] | 581 |
| Xor16 | 10,000 | 572 [570, 632] | 590 [579, 640] | 580 |
| Fuse8 | 10,000 | 587 [572, 653] | 583 [568, 702] | 595 |
| Fuse16 | 10,000 | 577 [570, 612] | 577 [570, 659] | 584 |
| rbloom 2^-8 | 10,000 | 372 [368, 450] | 347 [335, 402] | 380 |
| rbloom 2^-16 | 10,000 | 433 [425, 745] | 340 [334, 376] | 441 |
| pyribbon fp8 | 1,000,000 | 52.6 [52, 55.9] | 51 [50.7, 52.7] | 60.1 |
| pyribbon fp16 | 1,000,000 | 71.2 [69.9, 71.9] | 50.8 [49.6, 63.5] | 78.7 |
| Xor8 | 1,000,000 | 586 [578, 705] | 590 [580, 663] | 594 |
| Xor16 | 1,000,000 | 600 [592, 631] | 598 [591, 605] | 608 |
| Fuse8 | 1,000,000 | 585 [581, 691] | 584 [579, 732] | 593 |
| Fuse16 | 1,000,000 | 597 [594, 708] | 599 [590, 646] | 604 |
| rbloom 2^-8 | 1,000,000 | 383 [381, 386] | 353 [348, 411] | 390 |
| rbloom 2^-16 | 1,000,000 | 446 [442, 488] | 357 [353, 382] | 454 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | `contains_many` | 20.7 | 23.2 | 21.8 |
| pyribbon fp16 | 10,000 | `contains_many` | 14.7 | 23.3 | 18 |
| Xor8 | 10,000 | per-key loop | 1.7 | 1.69 | 1.7 |
| Xor16 | 10,000 | per-key loop | 1.7 | 1.69 | 1.7 |
| Fuse8 | 10,000 | per-key loop | 1.7 | 1.7 | 1.7 |
| Fuse16 | 10,000 | per-key loop | 1.71 | 1.71 | 1.69 |
| rbloom 2^-8 | 10,000 | per-key loop | 2.63 | 2.89 | 2.76 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.27 | 2.87 | 2.47 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 20.2 | 22.2 | 21.1 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 13.9 | 22.6 | 17.3 |
| Xor8 | 1,000,000 | per-key loop | 1.67 | 1.69 | 1.69 |
| Xor16 | 1,000,000 | per-key loop | 1.65 | 1.68 | 1.66 |
| Fuse8 | 1,000,000 | per-key loop | 1.67 | 1.68 | 1.68 |
| Fuse16 | 1,000,000 | per-key loop | 1.64 | 1.65 | 1.65 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 2.53 | 2.79 | 2.64 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.18 | 2.77 | 2.43 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 10,000 | 71.5 [71.1, 74.6] build ns/key | 82.2 [81.1, 104] | 52.9 [51.9, 61.9] | 12.7 |
| rbloom 2^-16, builtin hash() | 10,000 | 134 [131, 137] build ns/key | 140 [140, 141] | 52.5 [51.9, 54.5] | 9.35 |
| pyfusefilter: Python hashing only | 10,000 | 140 [134, 141] build ns/key | 124 [119, 146] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31 [30.8, 33] build ns/key | 122 [121, 124] | 121 [121, 122] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31 [30.3, 32.1] build ns/key | 121 [120, 124] | 127 [122, 152] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 27.6 [27.5, 35.8] build ns/key | 121 [121, 124] | 122 [120, 172] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 30.4 [27.6, 33.3] build ns/key | 121 [120, 124] | 122 [120, 155] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 205 [204, 214] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 78.5 [78.2, 88.7] build ns/key | 91.9 [91, 95.1] | 66.3 [64.9, 67.1] | 11.2 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 140 [140, 157] build ns/key | 154 [153, 159] | 72.9 [72.1, 74.5] | 8.22 |
| pyfusefilter: Python hashing only | 1,000,000 | 144 [142, 174] build ns/key | 119 [118, 122] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 91.7 [88.9, 108] build ns/key | 135 [132, 171] | 132 [131, 133] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 91.8 [89.4, 100] build ns/key | 138 [138, 143] | 139 [138, 144] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 38.9 [37.8, 41.4] build ns/key | 133 [131, 163] | 132 [131, 139] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 38.6 [38, 46.1] build ns/key | 139 [138, 206] | 138 [135, 141] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 206 [205, 214] | (same keys) | n/a |

## Notes and caveats

- Every filter is built from the same keys, and its FPR is measured on the same disjoint negative probes (4,000,000 for the 8-bit class, 20,000,000 for the 16-bit class). The probe keys differ from all members by construction. Fingerprint widths are discrete (8 or 16 bits) and Bloom filters are continuous, so each Bloom filter is sized for 2^-8 or 2^-16 and its FPR is then measured. Bits/key is reported with the measured FPR and with the overhead above the information-theoretic minimum of log2(1/FPR) bits/key, which lets filters with slightly different FPRs be compared.
- The intervals are 95% Wilson intervals for the stated number of probes. The 16-bit filters have only a few hundred expected false positives, so their FPR, and therefore their 'above minimum' column, is known only to roughly 5-10%.
- All measured FPRs are within 0.5x-2x of 2^-bits.
- `pyfusefilter` hashes every key in Python (`str(key).encode()` then `xxhash.xxh64_intdigest`) on every call and has no batch query. `pyribbon` hashes inside the C call. The headline numbers include these costs because a user pays them. The diagnostic tables separate the Python hashing from the filter probe. The probe-only rows call the library's C function through cffi with a pre-hashed key. The sum of the hashing and probe rows is a lower bound on the shipped call, and the remainder is Python call overhead. pyribbon cannot be split this way because its hash is part of the C call.
- rbloom hashes keys with Python's `hash()` unless it is given a `hash_func`. For `str` and `bytes` that hash is salted per process (and cached in the str object), so it cannot be persisted and it flatters repeated lookups of the same objects. The headline rbloom rows therefore pass an explicit deterministic `hash_func` (ints: a 64-bit multiplicative hash; str: xxh64 of the UTF-8 bytes). Its Python call cost is included in those rows and listed in the diagnostics. The 'builtin hash()' rows in the diagnostics use no callback and show rbloom's own probe cost. For int keys that is a sound configuration, so the win/loss summary counts it among the competitors. A check on 10,000 sequential ints and 1,000,000 probes (target 3.91e-03) gives FPR 4.68e-03 with the default hash() and 4.32e-03 with our hash_func, so rbloom's FPR is sane with either.
- Only pyribbon has a batch API (`contains_many`). For every other library the batch figure is a per-key list comprehension, `[k in f for k in keys]`, marked as such in the table. The 50/50 mix is the throughput of one member batch plus one non-member batch.
- Single-query latency is measured with a tight Python `for` loop over 100,000 random member keys (sampled with replacement) or non-member keys. The same loop without the call is timed in the same repeat and subtracted (median 6.83 ns per empty iteration here). What remains still includes the `k in f` bytecodes, a few ns. The unsubtracted figure is in the last column.
- Timing uses `time.perf_counter_ns` with GC disabled while timed and one warm-up pass. The figures are the median and min/max of 7 repeats (3 at n = 10^7, with no warm-up build there). Keys are generated before timing. Build time includes allocation and hashing but not key generation.
- `int` keys are distinct pseudo-random 63-bit integers from a fixed-seed bijective mixer. `str` keys are `user:` plus 11 digits, with members 0..n-1 and probes from 10^10 upwards. Query keys are fresh objects created in query order, so members and non-members have the same memory layout, and they are the same objects in every repeat (CPython caches a str's hash, which only matters for rbloom's builtin hash rows).
- Numbers are comparable between libraries within this run and not across machines. A `powersave` or `ondemand` governor adds noise. Run on an otherwise idle machine, with turbo and the governor fixed if you can.
