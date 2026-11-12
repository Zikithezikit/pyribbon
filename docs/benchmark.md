# pyribbon benchmark

## Machine and software

- **CPU**: Intel Core i7-7700 CPU @ 3.60GHz
- **Logical CPUs**: 8, benchmark pinned to CPU 7
- **Frequency scaling governor**: powersave
- **CPU frequency**: 0.80 GHz at start, max 4.20 GHz, turbo enabled
- **OS / kernel**: Linux 7.0.0-43-generic (Linux-7.0.0-43-generic-x86_64-with-glibc2.43)
- **Python**: CPython 3.14.4, built with GCC 15.2.0
- **Python build flags**: CC=x86_64-linux-gnu-gcc; CFLAGS=-fno-strict-overflow -Wsign-compare -DNDEBUG -g -O2 -Wall
- **pyribbon extension**: _ribbon.abi3.so; compiler recorded in the binary: GCC: (Ubuntu 15.2.0-16ubuntu1) 15.2.0
- **pyribbon build flags**: setup.py adds none (/std:c11 on Windows only): the interpreter's CFLAGS above are used
- **pyribbon version**: 0.1.0
- **pyfusefilter version**: 1.3.2
- **rbloom version**: 1.5.4
- **Other packages**: xxhash 4.1.0, cffi 2.1.1, numpy 2.5.4, matplotlib 3.11.2

## Run

- **Date**: 2026-11-12T21:28:24+02:00
- **Command**: `python benchmarks/bench.py --plot docs/benchmark.png --table docs/benchmark.md --json docs/benchmark.json`
- **Pinning**: CPU 7
- **Key sizes (int)**: 1,000, 10,000, 100,000, 1,000,000, 10,000,000
- **Key sizes (str)**: 10,000, 1,000,000
- **Repeats**: 7 (at most 3 at n >= 10,000,000); statistics are median and min/max
- **Query set**: 100,000 keys per loop/batch
- **FPR probes**: 4,000,000 (8-bit class), 20,000,000 (16-bit class), in chunks of 1,000,000
- **Seed**: 20261112
- **Mode**: full
- **Total run time**: 591 s

## Where pyribbon wins and loses (int keys, n = 10,000,000)

| Class | Metric | pyribbon | Best other | Delta | Verdict |
| --- | --- | ---: | ---: | ---: | ---: |
| 8-bit | bits/key | 9.19 | 9.02 (Fuse8) | +2% | **pyribbon behind** |
| 8-bit | bits/key above log2(1/FPR) | 1.18 | 1.00 (Fuse8) | +17% | **pyribbon behind** |
| 8-bit | build ns/key | 94 | 219 (rbloom 2^-8, builtin hash()) | -57% | pyribbon ahead |
| 8-bit | `in` member ns | 91 | 229 (rbloom 2^-8, builtin hash()) | -60% | pyribbon ahead |
| 8-bit | `in` non-member ns | 93 | 155 (rbloom 2^-8, builtin hash()) | -40% | pyribbon ahead |
| 8-bit | batch Mkeys/s (50/50 mix) | 18.04 | 5.01 (rbloom 2^-8, builtin hash()) | +260% | pyribbon ahead |
| 16-bit | bits/key | 18.39 | 18.04 (Fuse16) | +2% | **pyribbon behind** |
| 16-bit | bits/key above log2(1/FPR) | 2.36 | 1.95 (Fuse16) | +21% | **pyribbon behind** |
| 16-bit | build ns/key | 109 | 441 (rbloom 2^-16, builtin hash()) | -75% | pyribbon ahead |
| 16-bit | `in` member ns | 138 | 431 (rbloom 2^-16, builtin hash()) | -68% | pyribbon ahead |
| 16-bit | `in` non-member ns | 113 | 169 (rbloom 2^-16, builtin hash()) | -33% | pyribbon ahead |
| 16-bit | batch Mkeys/s (50/50 mix) | 10.81 | 3.24 (rbloom 2^-16, builtin hash()) | +234% | pyribbon ahead |

Delta is relative to the best other filter of the same fingerprint class, including rbloom with its builtin `hash()` (negative = pyribbon lower). The 'above log2(1/FPR)' rows move with the measured FPR, whose uncertainty is in the notes. Lower is better except for batch throughput. The batch row compares `contains_many` with the others' per-key loop, because none of them has a batch API. Generated from the data of this run, not hand-written.

## Results: int keys (pseudo-random 63-bit)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 9.216 | 0.00388 [0.00382, 0.00394] | 15,502 / 4,000,000 | 0.99 | 8.01 | 1.20 (15%) |
| pyribbon fp16 | 1,000 | 17.920 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 1.98 (12%) |
| Xor8 | 1,000 | 10.272 | 0.00383 [0.00377, 0.0039] | 15,340 / 4,000,000 | 0.98 | 8.03 | 2.25 (28%) |
| Xor16 | 1,000 | 20.352 | 1.47e-05 [1.31e-05, 1.65e-05] | 294 / 20,000,000 | 0.96 | 16.05 | 4.30 (27%) |
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
| Xor8 | 100,000 | 9.844 | 0.00391 [0.00385, 0.00397] | 15,634 / 4,000,000 | 1.00 | 8.00 | 1.85 (23%) |
| Xor16 | 100,000 | 19.687 | 1.53e-05 [1.37e-05, 1.71e-05] | 306 / 20,000,000 | 1.00 | 16.00 | 3.69 (23%) |
| Fuse8 | 100,000 | 9.506 | 0.00388 [0.00382, 0.00394] | 15,520 / 4,000,000 | 0.99 | 8.01 | 1.50 (19%) |
| Fuse16 | 100,000 | 19.009 | 1.52e-05 [1.36e-05, 1.7e-05] | 304 / 20,000,000 | 1.00 | 16.01 | 3.00 (19%) |
| rbloom 2^-8 | 100,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,663 / 4,000,000 | 1.00 | 8.00 | 3.55 (44%) |
| rbloom 2^-16 | 100,000 | 23.083 | 1.5e-05 [1.34e-05, 1.68e-05] | 301 / 20,000,000 | 0.99 | 16.02 | 7.06 (44%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,571 / 4,000,000 | 1.00 | 8.00 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.68e-05 [1.5e-05, 1.86e-05] | 335 / 20,000,000 | 1.10 | 15.87 | 2.12 (13%) |
| Xor8 | 1,000,000 | 9.840 | 0.00389 [0.00383, 0.00395] | 15,556 / 4,000,000 | 1.00 | 8.01 | 1.83 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.61e-05 [1.44e-05, 1.8e-05] | 322 / 20,000,000 | 1.06 | 15.92 | 3.76 (24%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00385 [0.00379, 0.00391] | 15,394 / 4,000,000 | 0.99 | 8.02 | 1.02 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.49e-05 [1.33e-05, 1.66e-05] | 297 / 20,000,000 | 0.97 | 16.04 | 2.05 (13%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00387 [0.00381, 0.00393] | 15,483 / 4,000,000 | 0.99 | 8.01 | 3.53 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 7.14 (45%) |
| pyribbon fp8 | 10,000,000 | 9.195 | 0.00386 [0.0038, 0.00392] | 15,440 / 4,000,000 | 0.99 | 8.02 | 1.18 (15%) |
| pyribbon fp16 | 10,000,000 | 18.390 | 1.49e-05 [1.33e-05, 1.67e-05] | 298 / 20,000,000 | 0.98 | 16.03 | 2.36 (15%) |
| Xor8 | 10,000,000 | 9.840 | 0.00392 [0.00386, 0.00398] | 15,681 / 4,000,000 | 1.00 | 7.99 | 1.85 (23%) |
| Xor16 | 10,000,000 | 19.680 | 1.4e-05 [1.24e-05, 1.57e-05] | 279 / 20,000,000 | 0.91 | 16.13 | 3.55 (22%) |
| Fuse8 | 10,000,000 | 9.018 | 0.00387 [0.00381, 0.00393] | 15,466 / 4,000,000 | 0.99 | 8.01 | 1.00 (13%) |
| Fuse16 | 10,000,000 | 18.036 | 1.44e-05 [1.28e-05, 1.62e-05] | 288 / 20,000,000 | 0.94 | 16.08 | 1.95 (12%) |
| rbloom 2^-8 | 10,000,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,690 / 4,000,000 | 1.00 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 10,000,000 | 23.083 | 1.62e-05 [1.45e-05, 1.81e-05] | 324 / 20,000,000 | 1.06 | 15.91 | 7.17 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 6.78e-05 [6.65e-05, 7.07e-05] | 67.8 [66.5, 70.7] |
| pyribbon fp16 | 1,000 | 8.65e-05 [8.05e-05, 0.000145] | 86.5 [80.5, 145] |
| Xor8 | 1,000 | 0.000633 [0.000617, 0.000691] | 633 [617, 691] |
| Xor16 | 1,000 | 0.000631 [0.000627, 0.000784] | 631 [627, 784] |
| Fuse8 | 1,000 | 0.000549 [0.000542, 0.000561] | 549 [542, 561] |
| Fuse16 | 1,000 | 0.000547 [0.00054, 0.000579] | 547 [540, 579] |
| rbloom 2^-8 | 1,000 | 0.000276 [0.000272, 0.000307] | 276 [272, 307] |
| rbloom 2^-16 | 1,000 | 0.000348 [0.00033, 0.000381] | 348 [330, 381] |
| pyribbon fp8 | 10,000 | 0.000563 [0.000561, 0.000598] | 56.3 [56.1, 59.8] |
| pyribbon fp16 | 10,000 | 0.000694 [0.000686, 0.000735] | 69.4 [68.6, 73.5] |
| Xor8 | 10,000 | 0.00524 [0.00518, 0.00557] | 524 [518, 557] |
| Xor16 | 10,000 | 0.00544 [0.00525, 0.00603] | 544 [525, 603] |
| Fuse8 | 10,000 | 0.00529 [0.00517, 0.00558] | 529 [517, 558] |
| Fuse16 | 10,000 | 0.00544 [0.00511, 0.00565] | 544 [511, 565] |
| rbloom 2^-8 | 10,000 | 0.00274 [0.00269, 0.0029] | 274 [269, 290] |
| rbloom 2^-16 | 10,000 | 0.00333 [0.0033, 0.00338] | 333 [330, 338] |
| pyribbon fp8 | 100,000 | 0.00575 [0.00557, 0.00677] | 57.5 [55.7, 67.7] |
| pyribbon fp16 | 100,000 | 0.00709 [0.00705, 0.00741] | 70.9 [70.5, 74.1] |
| Xor8 | 100,000 | 0.0603 [0.0599, 0.0736] | 603 [599, 736] |
| Xor16 | 100,000 | 0.0628 [0.0605, 0.0643] | 628 [605, 643] |
| Fuse8 | 100,000 | 0.0555 [0.0548, 0.0581] | 555 [548, 581] |
| Fuse16 | 100,000 | 0.0573 [0.0552, 0.064] | 573 [552, 640] |
| rbloom 2^-8 | 100,000 | 0.0274 [0.027, 0.032] | 274 [270, 320] |
| rbloom 2^-16 | 100,000 | 0.0353 [0.0336, 0.0362] | 353 [336, 362] |
| pyribbon fp8 | 1,000,000 | 0.0713 [0.0708, 0.0818] | 71.3 [70.8, 81.8] |
| pyribbon fp16 | 1,000,000 | 0.086 [0.0855, 0.0889] | 86 [85.5, 88.9] |
| Xor8 | 1,000,000 | 0.642 [0.632, 0.66] | 642 [632, 660] |
| Xor16 | 1,000,000 | 0.639 [0.631, 0.667] | 639 [631, 667] |
| Fuse8 | 1,000,000 | 0.582 [0.575, 0.588] | 582 [575, 588] |
| Fuse16 | 1,000,000 | 0.578 [0.574, 0.585] | 578 [574, 585] |
| rbloom 2^-8 | 1,000,000 | 0.301 [0.293, 0.307] | 301 [293, 307] |
| rbloom 2^-16 | 1,000,000 | 0.363 [0.351, 0.38] | 363 [351, 380] |
| pyribbon fp8 | 10,000,000 | 0.941 [0.941, 0.944] | 94.1 [94.1, 94.4] |
| pyribbon fp16 | 10,000,000 | 1.09 [1.09, 1.09] | 109 [109, 109] |
| Xor8 | 10,000,000 | 6.65 [6.64, 6.68] | 665 [664, 668] |
| Xor16 | 10,000,000 | 6.69 [6.67, 6.72] | 669 [667, 672] |
| Fuse8 | 10,000,000 | 6.13 [6.1, 6.18] | 613 [610, 618] |
| Fuse16 | 10,000,000 | 6.16 [6.1, 6.17] | 616 [610, 617] |
| rbloom 2^-8 | 10,000,000 | 4.32 [4.32, 4.35] | 432 [432, 435] |
| rbloom 2^-16 | 10,000,000 | 6.57 [6.55, 6.58] | 657 [655, 658] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 45.8 [45.2, 46.2] | 40.4 [39.8, 44.5] | 52.5 |
| pyribbon fp16 | 1,000 | 66 [64.9, 71.3] | 40 [39.4, 44] | 72.7 |
| Xor8 | 1,000 | 704 [695, 737] | 710 [705, 746] | 716 |
| Xor16 | 1,000 | 711 [683, 772] | 710 [693, 807] | 718 |
| Fuse8 | 1,000 | 685 [682, 715] | 698 [689, 827] | 691 |
| Fuse16 | 1,000 | 697 [687, 747] | 696 [690, 719] | 703 |
| rbloom 2^-8 | 1,000 | 286 [282, 306] | 251 [247, 266] | 293 |
| rbloom 2^-16 | 1,000 | 342 [339, 346] | 254 [249, 264] | 349 |
| pyribbon fp8 | 10,000 | 46.2 [45.7, 46.6] | 40.2 [39.2, 42.8] | 52.9 |
| pyribbon fp16 | 10,000 | 65.2 [64.5, 66.4] | 41.8 [39.8, 42.9] | 71.8 |
| Xor8 | 10,000 | 737 [701, 909] | 708 [696, 719] | 744 |
| Xor16 | 10,000 | 748 [710, 773] | 758 [710, 795] | 755 |
| Fuse8 | 10,000 | 727 [699, 772] | 699 [692, 727] | 733 |
| Fuse16 | 10,000 | 696 [690, 740] | 714 [694, 744] | 703 |
| rbloom 2^-8 | 10,000 | 291 [286, 319] | 256 [253, 277] | 298 |
| rbloom 2^-16 | 10,000 | 345 [343, 372] | 259 [256, 274] | 352 |
| pyribbon fp8 | 100,000 | 47 [45.9, 53.7] | 43.1 [42.3, 65.5] | 54 |
| pyribbon fp16 | 100,000 | 71.8 [69.9, 80.9] | 44.9 [29, 53.8] | 78.7 |
| Xor8 | 100,000 | 729 [722, 752] | 748 [726, 766] | 736 |
| Xor16 | 100,000 | 745 [717, 779] | 721 [715, 877] | 753 |
| Fuse8 | 100,000 | 729 [707, 949] | 705 [699, 827] | 736 |
| Fuse16 | 100,000 | 723 [702, 766] | 748 [712, 785] | 730 |
| rbloom 2^-8 | 100,000 | 297 [288, 299] | 259 [257, 275] | 305 |
| rbloom 2^-16 | 100,000 | 360 [356, 396] | 266 [264, 287] | 368 |
| pyribbon fp8 | 1,000,000 | 54 [52.7, 55.5] | 51.9 [51.2, 53.3] | 60.8 |
| pyribbon fp16 | 1,000,000 | 77.1 [74.4, 91.4] | 58.2 [55.8, 71.2] | 84.3 |
| Xor8 | 1,000,000 | 735 [723, 776] | 739 [728, 775] | 741 |
| Xor16 | 1,000,000 | 777 [758, 818] | 762 [756, 835] | 784 |
| Fuse8 | 1,000,000 | 728 [725, 777] | 737 [725, 800] | 734 |
| Fuse16 | 1,000,000 | 770 [752, 885] | 766 [755, 812] | 777 |
| rbloom 2^-8 | 1,000,000 | 311 [309, 333] | 291 [285, 353] | 318 |
| rbloom 2^-16 | 1,000,000 | 380 [376, 411] | 298 [280, 365] | 387 |
| pyribbon fp8 | 10,000,000 | 90.9 [89.5, 107] | 93.2 [88.6, 96] | 98.5 |
| pyribbon fp16 | 10,000,000 | 138 [134, 142] | 113 [108, 115] | 145 |
| Xor8 | 10,000,000 | 812 [807, 839] | 817 [812, 850] | 819 |
| Xor16 | 10,000,000 | 823 [814, 861] | 817 [811, 860] | 832 |
| Fuse8 | 10,000,000 | 806 [796, 832] | 804 [798, 827] | 813 |
| Fuse16 | 10,000,000 | 807 [801, 1.02e+03] | 802 [796, 820] | 814 |
| rbloom 2^-8 | 10,000,000 | 449 [436, 475] | 357 [353, 369] | 456 |
| rbloom 2^-16 | 10,000,000 | 648 [640, 686] | 372 [370, 402] | 655 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | `contains_many` | 20.7 | 23.5 | 21.9 |
| pyribbon fp8 | 1,000 | `contains_many` over an int `array('q')` | 28 | 33.5 | 30.7 |
| pyribbon fp16 | 1,000 | `contains_many` | 14.7 | 23.5 | 18.1 |
| pyribbon fp16 | 1,000 | `contains_many` over an int `array('q')` | 17.6 | 32.1 | 22.8 |
| Xor8 | 1,000 | per-key loop | 1.39 | 1.4 | 1.4 |
| Xor16 | 1,000 | per-key loop | 1.35 | 1.41 | 1.38 |
| Fuse8 | 1,000 | per-key loop | 1.41 | 1.43 | 1.42 |
| Fuse16 | 1,000 | per-key loop | 1.4 | 1.41 | 1.4 |
| rbloom 2^-8 | 1,000 | per-key loop | 3.35 | 3.8 | 3.58 |
| rbloom 2^-16 | 1,000 | per-key loop | 2.83 | 3.8 | 3.26 |
| pyribbon fp8 | 10,000 | `contains_many` | 20.7 | 23.4 | 22.1 |
| pyribbon fp8 | 10,000 | `contains_many` over an int `array('q')` | 28.4 | 33.5 | 30.7 |
| pyribbon fp16 | 10,000 | `contains_many` | 14.7 | 23.1 | 17.7 |
| pyribbon fp16 | 10,000 | `contains_many` over an int `array('q')` | 17.9 | 33.4 | 23.4 |
| Xor8 | 10,000 | per-key loop | 1.37 | 1.37 | 1.38 |
| Xor16 | 10,000 | per-key loop | 1.34 | 1.35 | 1.35 |
| Fuse8 | 10,000 | per-key loop | 1.41 | 1.41 | 1.39 |
| Fuse16 | 10,000 | per-key loop | 1.4 | 1.37 | 1.38 |
| rbloom 2^-8 | 10,000 | per-key loop | 3.34 | 3.75 | 3.53 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.79 | 3.69 | 3.18 |
| pyribbon fp8 | 100,000 | `contains_many` | 19.8 | 22.8 | 21 |
| pyribbon fp8 | 100,000 | `contains_many` over an int `array('q')` | 26.2 | 32 | 28.9 |
| pyribbon fp16 | 100,000 | `contains_many` | 14.4 | 22.9 | 17.7 |
| pyribbon fp16 | 100,000 | `contains_many` over an int `array('q')` | 17.7 | 32.2 | 22.8 |
| Xor8 | 100,000 | per-key loop | 1.3 | 1.31 | 1.29 |
| Xor16 | 100,000 | per-key loop | 1.34 | 1.34 | 1.33 |
| Fuse8 | 100,000 | per-key loop | 1.36 | 1.39 | 1.35 |
| Fuse16 | 100,000 | per-key loop | 1.37 | 1.29 | 1.3 |
| rbloom 2^-8 | 100,000 | per-key loop | 3.22 | 3.63 | 3.41 |
| rbloom 2^-16 | 100,000 | per-key loop | 2.69 | 3.46 | 2.95 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 19.9 | 22.3 | 21 |
| pyribbon fp8 | 1,000,000 | `contains_many` over an int `array('q')` | 26.8 | 30.8 | 28.6 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 13.7 | 21.9 | 16.9 |
| pyribbon fp16 | 1,000,000 | `contains_many` over an int `array('q')` | 16.4 | 30.2 | 21.1 |
| Xor8 | 1,000,000 | per-key loop | 1.33 | 1.32 | 1.32 |
| Xor16 | 1,000,000 | per-key loop | 1.27 | 1.27 | 1.26 |
| Fuse8 | 1,000,000 | per-key loop | 1.32 | 1.33 | 1.32 |
| Fuse16 | 1,000,000 | per-key loop | 1.28 | 1.3 | 1.28 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 3.09 | 3.44 | 3.25 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.57 | 3.39 | 2.93 |
| pyribbon fp8 | 10,000,000 | `contains_many` | 16 | 20.6 | 18 |
| pyribbon fp8 | 10,000,000 | `contains_many` over an int `array('q')` | 20.7 | 28.6 | 24 |
| pyribbon fp16 | 10,000,000 | `contains_many` | 8.06 | 16.3 | 10.8 |
| pyribbon fp16 | 10,000,000 | `contains_many` over an int `array('q')` | 8.94 | 20.3 | 12.4 |
| Xor8 | 10,000,000 | per-key loop | 1.2 | 1.2 | 1.2 |
| Xor16 | 10,000,000 | per-key loop | 1.17 | 1.2 | 1.18 |
| Fuse8 | 10,000,000 | per-key loop | 1.22 | 1.23 | 1.22 |
| Fuse16 | 10,000,000 | per-key loop | 1.2 | 1.21 | 1.21 |
| rbloom 2^-8 | 10,000,000 | per-key loop | 2.21 | 2.74 | 2.45 |
| rbloom 2^-16 | 10,000,000 | per-key loop | 1.51 | 2.63 | 1.92 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 1,000 | 89.8 [86.6, 101] build ns/key | 88 [86.1, 90.2] | 56.1 [54.3, 57.9] | 12.3 |
| rbloom 2^-16, builtin hash() | 1,000 | 147 [144, 154] build ns/key | 145 [143, 147] | 56 [55.2, 59.6] | 9.09 |
| pyfusefilter: Python hashing only | 1,000 | 220 [215, 265] build ns/key | 194 [192, 210] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 44.2 [43.3, 46.7] build ns/key | 125 [122, 130] | 123 [122, 137] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 44.3 [42.8, 47.8] build ns/key | 125 [120, 154] | 124 [121, 124] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 42.2 [40.6, 63.3] build ns/key | 123 [122, 138] | 124 [121, 129] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 43.8 [41.5, 44.9] build ns/key | 124 [122, 136] | 123 [121, 151] | n/a |
| rbloom: `hash_func` call only | 1,000 | n/a | 126 [123, 240] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000 | 76 [75.4, 78.4] build ns/key | 89.2 [85.6, 108] | 57.3 [56, 75.8] | 12.2 |
| rbloom 2^-16, builtin hash() | 10,000 | 138 [135, 139] build ns/key | 150 [145, 153] | 58.3 [55.6, 59.8] | 9.14 |
| pyfusefilter: Python hashing only | 10,000 | 213 [208, 234] build ns/key | 203 [198, 211] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 32.5 [32.1, 47.8] build ns/key | 128 [124, 156] | 133 [108, 152] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 32.8 [31.5, 36.2] build ns/key | 126 [124, 180] | 178 [169, 207] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28.4 [27.4, 30.8] build ns/key | 133 [126, 199] | 128 [125, 152] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28.9 [27.9, 37.5] build ns/key | 125 [124, 131] | 125 [124, 128] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 131 [129, 161] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 100,000 | 78.6 [77, 82.8] build ns/key | 91.5 [88.6, 92.8] | 61.2 [60.4, 62.7] | 11.7 |
| rbloom 2^-16, builtin hash() | 100,000 | 143 [141, 150] build ns/key | 155 [153, 172] | 68 [58.6, 85.6] | 8.18 |
| pyfusefilter: Python hashing only | 100,000 | 210 [206, 429] build ns/key | 200 [198, 203] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 75.7 [70.7, 76.8] build ns/key | 131 [129, 133] | 130 [115, 134] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 79 [71.8, 85.5] build ns/key | 136 [131, 150] | 131 [130, 134] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 27.8 [27.3, 28.5] build ns/key | 129 [127, 132] | 133 [126, 135] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 27.3 [27.1, 28] build ns/key | 131 [130, 136] | 132 [130, 138] | n/a |
| rbloom: `hash_func` call only | 100,000 | n/a | 126 [123, 133] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 80.9 [80.5, 84.7] build ns/key | 100 [99.1, 121] | 75.1 [73.1, 76.9] | 10.4 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 147 [146, 158] build ns/key | 170 [169, 217] | 86.1 [82.3, 91] | 7.39 |
| pyfusefilter: Python hashing only | 1,000,000 | 227 [224, 231] build ns/key | 199 [195, 207] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 92.4 [90.8, 96.6] build ns/key | 137 [136, 163] | 138 [135, 151] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 95.5 [92.9, 105] build ns/key | 143 [140, 147] | 146 [142, 169] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 39.9 [39.4, 41.3] build ns/key | 136 [133, 146] | 136 [135, 139] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 39.2 [38.7, 41.3] build ns/key | 140 [139, 140] | 141 [139, 187] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 130 [129, 149] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000,000 | 219 [217, 225] build ns/key | 229 [225, 250] | 155 [153, 160] | 5.01 |
| rbloom 2^-16, builtin hash() | 10,000,000 | 441 [441, 446] build ns/key | 431 [427, 462] | 169 [168, 199] | 3.24 |
| pyfusefilter: Python hashing only | 10,000,000 | 234 [234, 235] build ns/key | 201 [197, 221] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 107 [107, 108] build ns/key | 208 [207, 227] | 209 [207, 233] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 111 [110, 112] build ns/key | 218 [216, 228] | 220 [215, 234] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 56.7 [56.3, 57.7] build ns/key | 210 [205, 245] | 208 [205, 231] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 55 [54.7, 55.3] build ns/key | 220 [216, 221] | 217 [215, 229] | n/a |
| rbloom: `hash_func` call only | 10,000,000 | n/a | 124 [123, 136] | (same keys) | n/a |

## Results: str keys (`'user:00000000042'`, 16 characters)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 8.653 | 0.00394 [0.00388, 0.004] | 15,771 / 4,000,000 | 1.01 | 7.99 | 0.67 (8%) |
| pyribbon fp16 | 10,000 | 17.254 | 1.64e-05 [1.47e-05, 1.82e-05] | 327 / 20,000,000 | 1.07 | 15.90 | 1.35 (9%) |
| Xor8 | 10,000 | 9.883 | 0.00391 [0.00385, 0.00397] | 15,645 / 4,000,000 | 1.00 | 8.00 | 1.89 (24%) |
| Xor16 | 10,000 | 19.747 | 1.58e-05 [1.42e-05, 1.76e-05] | 316 / 20,000,000 | 1.04 | 15.95 | 3.80 (24%) |
| Fuse8 | 10,000 | 10.067 | 0.00392 [0.00386, 0.00398] | 15,685 / 4,000,000 | 1.00 | 7.99 | 2.07 (26%) |
| Fuse16 | 10,000 | 20.102 | 1.33e-05 [1.18e-05, 1.5e-05] | 266 / 20,000,000 | 0.87 | 16.20 | 3.90 (24%) |
| rbloom 2^-8 | 10,000 | 11.542 | 0.00396 [0.00389, 0.00402] | 15,823 / 4,000,000 | 1.01 | 7.98 | 3.56 (45%) |
| rbloom 2^-16 | 10,000 | 23.083 | 1.6e-05 [1.43e-05, 1.78e-05] | 319 / 20,000,000 | 1.05 | 15.94 | 7.15 (45%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,545 / 4,000,000 | 0.99 | 8.01 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.52e-05 [1.35e-05, 1.7e-05] | 303 / 20,000,000 | 0.99 | 16.01 | 1.98 (12%) |
| Xor8 | 1,000,000 | 9.840 | 0.00394 [0.00388, 0.004] | 15,771 / 4,000,000 | 1.01 | 7.99 | 1.85 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.33e-05 [1.18e-05, 1.5e-05] | 266 / 20,000,000 | 0.87 | 16.20 | 3.48 (21%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00392 [0.00386, 0.00398] | 15,671 / 4,000,000 | 1.00 | 8.00 | 1.05 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.69e-05 [1.52e-05, 1.88e-05] | 338 / 20,000,000 | 1.11 | 15.85 | 2.24 (14%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00393 [0.00387, 0.00399] | 15,714 / 4,000,000 | 1.01 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.55e-05 [1.39e-05, 1.74e-05] | 311 / 20,000,000 | 1.02 | 15.97 | 7.11 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 0.000571 [0.000551, 0.000587] | 57.1 [55.1, 58.7] |
| pyribbon fp16 | 10,000 | 0.000725 [0.0007, 0.000768] | 72.5 [70, 76.8] |
| Xor8 | 10,000 | 0.00466 [0.00461, 0.00845] | 466 [461, 845] |
| Xor16 | 10,000 | 0.00468 [0.00459, 0.00471] | 468 [459, 471] |
| Fuse8 | 10,000 | 0.00463 [0.00457, 0.0048] | 463 [457, 480] |
| Fuse16 | 10,000 | 0.0046 [0.00455, 0.00474] | 460 [455, 474] |
| rbloom 2^-8 | 10,000 | 0.0036 [0.00356, 0.00387] | 360 [356, 387] |
| rbloom 2^-16 | 10,000 | 0.00421 [0.0042, 0.00431] | 421 [420, 431] |
| pyribbon fp8 | 1,000,000 | 0.0712 [0.07, 0.0751] | 71.2 [70, 75.1] |
| pyribbon fp16 | 1,000,000 | 0.085 [0.0845, 0.0876] | 85 [84.5, 87.6] |
| Xor8 | 1,000,000 | 0.561 [0.554, 0.572] | 561 [554, 572] |
| Xor16 | 1,000,000 | 0.563 [0.558, 0.57] | 563 [558, 570] |
| Fuse8 | 1,000,000 | 0.509 [0.503, 0.536] | 509 [503, 536] |
| Fuse16 | 1,000,000 | 0.504 [0.502, 0.513] | 504 [502, 513] |
| rbloom 2^-8 | 1,000,000 | 0.385 [0.375, 0.398] | 385 [375, 398] |
| rbloom 2^-16 | 1,000,000 | 0.448 [0.439, 0.461] | 448 [439, 461] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 46.7 [44.5, 51.5] | 41.3 [41, 43.7] | 55.1 |
| pyribbon fp16 | 10,000 | 66.5 [66.2, 67.5] | 43.3 [41.7, 44.6] | 74.4 |
| Xor8 | 10,000 | 640 [631, 670] | 645 [643, 676] | 647 |
| Xor16 | 10,000 | 634 [627, 700] | 636 [626, 653] | 642 |
| Fuse8 | 10,000 | 633 [620, 687] | 630 [618, 668] | 641 |
| Fuse16 | 10,000 | 625 [620, 658] | 625 [623, 652] | 633 |
| rbloom 2^-8 | 10,000 | 386 [380, 415] | 354 [347, 396] | 394 |
| rbloom 2^-16 | 10,000 | 445 [440, 466] | 347 [343, 376] | 454 |
| pyribbon fp8 | 1,000,000 | 53.4 [50.8, 55] | 51.7 [51, 54.2] | 61.1 |
| pyribbon fp16 | 1,000,000 | 72.4 [71, 73.7] | 51.6 [50.2, 59.8] | 80 |
| Xor8 | 1,000,000 | 653 [645, 694] | 650 [644, 668] | 661 |
| Xor16 | 1,000,000 | 675 [658, 780] | 664 [661, 703] | 682 |
| Fuse8 | 1,000,000 | 643 [637, 706] | 637 [628, 674] | 651 |
| Fuse16 | 1,000,000 | 668 [649, 736] | 656 [653, 729] | 677 |
| rbloom 2^-8 | 1,000,000 | 392 [390, 457] | 367 [360, 400] | 400 |
| rbloom 2^-16 | 1,000,000 | 467 [464, 526] | 371 [368, 423] | 475 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | `contains_many` | 20.4 | 23 | 21.4 |
| pyribbon fp16 | 10,000 | `contains_many` | 14.4 | 22.8 | 17.6 |
| Xor8 | 10,000 | per-key loop | 1.52 | 1.52 | 1.52 |
| Xor16 | 10,000 | per-key loop | 1.53 | 1.48 | 1.5 |
| Fuse8 | 10,000 | per-key loop | 1.55 | 1.56 | 1.55 |
| Fuse16 | 10,000 | per-key loop | 1.57 | 1.56 | 1.57 |
| rbloom 2^-8 | 10,000 | per-key loop | 2.55 | 2.81 | 2.66 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.22 | 2.79 | 2.47 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 19.7 | 22 | 20.8 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 13.6 | 22.6 | 17 |
| Xor8 | 1,000,000 | per-key loop | 1.5 | 1.51 | 1.51 |
| Xor16 | 1,000,000 | per-key loop | 1.47 | 1.47 | 1.47 |
| Fuse8 | 1,000,000 | per-key loop | 1.52 | 1.53 | 1.52 |
| Fuse16 | 1,000,000 | per-key loop | 1.47 | 1.48 | 1.45 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 2.42 | 2.68 | 2.54 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.11 | 2.66 | 2.35 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 10,000 | 74.6 [72.8, 78] build ns/key | 85.4 [83.8, 89] | 54.3 [51.4, 69.3] | 12.4 |
| rbloom 2^-16, builtin hash() | 10,000 | 138 [134, 147] build ns/key | 144 [142, 145] | 53.2 [51.8, 56.3] | 8.92 |
| pyfusefilter: Python hashing only | 10,000 | 133 [132, 138] build ns/key | 123 [122, 164] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 32.8 [31.8, 36.5] build ns/key | 144 [132, 177] | 128 [126, 180] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.4 [30.7, 35.1] build ns/key | 132 [123, 137] | 126 [124, 137] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28.6 [28.5, 33.1] build ns/key | 128 [125, 156] | 129 [125, 130] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28.5 [28.3, 32.3] build ns/key | 125 [124, 128] | 126 [124, 153] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 211 [208, 228] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 80.1 [79.3, 81.7] build ns/key | 96.1 [95.2, 109] | 68.4 [68, 70.1] | 10.8 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 149 [146, 167] build ns/key | 182 [166, 197] | 77.9 [75.4, 82.4] | 7.78 |
| pyfusefilter: Python hashing only | 1,000,000 | 148 [146, 150] build ns/key | 124 [120, 126] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 98.3 [94.4, 99.8] build ns/key | 139 [136, 140] | 139 [138, 158] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 96.8 [94, 99.5] build ns/key | 154 [145, 161] | 154 [145, 197] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 40.3 [39.7, 41.7] build ns/key | 136 [133, 142] | 136 [133, 151] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 40.1 [39.4, 41.4] build ns/key | 144 [143, 148] | 149 [144, 171] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 211 [208, 220] | (same keys) | n/a |

## Notes and caveats

- **Same keys, same measured FPR.** Every filter is built from the same keys and its FPR is measured on the same disjoint negative probes (4,000,000 for the 8-bit class, 20,000,000 for the 16-bit class; keys differ from all members by construction). Fingerprint widths are discrete (8 or 16 bits) and Bloom filters are continuous, so each Bloom filter is sized for 2^-8 or 2^-16 and then *measured*; bits/key is reported together with the measured FPR and with the overhead above the information-theoretic minimum log2(1/FPR) bits/key, which compares filters with slightly different FPRs.
- **FPR confidence.** Intervals are 95% Wilson intervals for the stated number of probes. The 16-bit filters have only a few hundred expected false positives, so their FPR (and therefore their 'above minimum' column) is known to roughly 5-10% only.
- **FPR sanity.** All measured FPRs are within 0.5x-2x of 2^-bits.
- **As shipped.** `pyfusefilter` hashes every key in Python (`str(key).encode()` then `xxhash.xxh64_intdigest`) on every call and has no batch query; `pyribbon` hashes inside the C call. The headline numbers include these costs because they are what a user gets. The diagnostic tables separate the Python hashing from the filter probe (the probe-only rows call the library's C function through cffi with a pre-hashed key; the sum of hashing and probe rows is a lower bound on the shipped call, the rest is Python call overhead). pyribbon cannot be split this way: its hash is part of the C call.
- **rbloom hashing.** rbloom hashes keys with Python's `hash()` unless given a `hash_func`; for `str`/`bytes` that hash is salted per process (and cached in the str object), so it cannot be persisted and flatters repeated lookups of the same objects. The headline rbloom rows therefore pass an explicit deterministic `hash_func` (ints: a 64-bit multiplicative hash; str: xxh64 of the UTF-8 bytes), whose Python call cost is included and listed in the diagnostics. The 'builtin hash()' rows in the diagnostics use no callback and show rbloom's own probe cost; for int keys that is a sound configuration, so the win/loss summary counts it among the competitors. Check on 10,000 sequential ints and 1,000,000 probes (target 3.91e-03): default hash() gives FPR 4.68e-03, our hash_func 4.32e-03, so rbloom's FPR is sane with either.
- **Batch.** Only pyribbon has a batch API (`contains_many`). For every other library the batch figure is a per-key list comprehension `[k in f for k in keys]` (marked in the table). The 50/50 mix is the throughput of one member batch plus one non-member batch.
- **Single-query latency.** A tight Python `for` loop over 100,000 random member keys (sampled with replacement) or non-member keys, with the same loop without the call timed in the same repeat and subtracted (median 7.04 ns per empty iteration here). What remains still contains the `k in f` bytecodes (a few ns). The unsubtracted figure is in the last column.
- **Timing.** `time.perf_counter_ns`, GC disabled while timed, one warm-up pass, median and min/max of 7 repeats (3 at n = 10^7, no warm-up build there). Keys are generated before timing. Build time includes allocation and hashing, but not key generation.
- **Keys.** `int`: distinct pseudo-random 63-bit integers from a fixed-seed bijective mixer; `str`: `user:` + 11 digits, members 0..n-1, probes from 10^10 upwards. Query keys are fresh objects created in query order (so members and non-members have the same memory layout) and are the same objects in every repeat (CPython caches a str's hash, which only matters for rbloom's builtin hash rows).
- **Machine.** Numbers are comparable between libraries within this run, not across machines. A `powersave`/`ondemand` governor adds noise; run on an otherwise idle machine, with turbo and the governor fixed if you can.
