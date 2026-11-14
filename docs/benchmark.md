# pyribbon benchmark

## Machine and software

- CPU: Intel Core i7-7700 CPU @ 3.60GHz
- Logical CPUs: 8, benchmark pinned to CPU 7
- Frequency scaling governor: powersave
- CPU frequency: 0.80 GHz at start, max 4.20 GHz, turbo enabled
- OS / kernel: Linux 7.0.0-43-generic (Linux-7.0.0-43-generic-x86_64-with-glibc2.43)
- Python: CPython 3.14.4, built with GCC 15.2.0
- Python build flags: CC=x86_64-linux-gnu-gcc; CFLAGS=-fno-strict-overflow -Wsign-compare -DNDEBUG -g -O2 -Wall
- pyribbon extension: _ribbon.abi3.so; compiler recorded in the binary: GCC: (Ubuntu 15.2.0-16ubuntu1) 15.2.0
- pyribbon build flags: setup.py adds none (/std:c11 on Windows only): the interpreter's CFLAGS above are used
- pyribbon version: 0.1.2
- pyfusefilter version: 1.3.2
- rbloom version: 1.5.4
- Other packages: xxhash 4.1.0, cffi 2.1.1, numpy 2.5.4, matplotlib 3.11.2

## Run

- Date: 2026-11-14T08:29:02+02:00
- Command: `python benchmarks/bench.py --plot docs/benchmark.png --table docs/benchmark.md --json docs/benchmark.json`
- Pinning: CPU 7
- Key sizes (int): 1,000, 10,000, 100,000, 1,000,000, 10,000,000
- Key sizes (str): 10,000, 1,000,000
- Repeats: 7 (at most 3 at n >= 10,000,000); statistics are median and min/max
- Query set: 100,000 keys per loop/batch
- FPR probes: 4,000,000 (8-bit class), 20,000,000 (16-bit class), in chunks of 1,000,000
- Seed: 20261112
- Mode: full
- Total run time: 563 s

## Where pyribbon wins and loses (int keys, n = 10,000,000)

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

## Results: int keys (pseudo-random 63-bit)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 9.216 | 0.00388 [0.00382, 0.00394] | 15,502 / 4,000,000 | 0.99 | 8.01 | 1.20 (15%) |
| pyribbon fp16 | 1,000 | 17.920 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 1.98 (12%) |
| Xor8 | 1,000 | 10.272 | 0.00387 [0.00381, 0.00393] | 15,486 / 4,000,000 | 0.99 | 8.01 | 2.26 (28%) |
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
| Xor8 | 100,000 | 9.844 | 0.00392 [0.00386, 0.00398] | 15,678 / 4,000,000 | 1.00 | 8.00 | 1.85 (23%) |
| Xor16 | 100,000 | 19.687 | 1.55e-05 [1.39e-05, 1.73e-05] | 310 / 20,000,000 | 1.02 | 15.98 | 3.71 (23%) |
| Fuse8 | 100,000 | 9.506 | 0.00388 [0.00382, 0.00394] | 15,520 / 4,000,000 | 0.99 | 8.01 | 1.50 (19%) |
| Fuse16 | 100,000 | 19.009 | 1.52e-05 [1.36e-05, 1.7e-05] | 304 / 20,000,000 | 1.00 | 16.01 | 3.00 (19%) |
| rbloom 2^-8 | 100,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,663 / 4,000,000 | 1.00 | 8.00 | 3.55 (44%) |
| rbloom 2^-16 | 100,000 | 23.083 | 1.5e-05 [1.34e-05, 1.68e-05] | 301 / 20,000,000 | 0.99 | 16.02 | 7.06 (44%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,571 / 4,000,000 | 1.00 | 8.00 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.68e-05 [1.5e-05, 1.86e-05] | 335 / 20,000,000 | 1.10 | 15.87 | 2.12 (13%) |
| Xor8 | 1,000,000 | 9.840 | 0.00392 [0.00386, 0.00399] | 15,698 / 4,000,000 | 1.00 | 7.99 | 1.85 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.45e-05 [1.29e-05, 1.63e-05] | 290 / 20,000,000 | 0.95 | 16.07 | 3.61 (22%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00385 [0.00379, 0.00391] | 15,394 / 4,000,000 | 0.99 | 8.02 | 1.02 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.49e-05 [1.33e-05, 1.66e-05] | 297 / 20,000,000 | 0.97 | 16.04 | 2.05 (13%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00387 [0.00381, 0.00393] | 15,483 / 4,000,000 | 0.99 | 8.01 | 3.53 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.59e-05 [1.42e-05, 1.77e-05] | 318 / 20,000,000 | 1.04 | 15.94 | 7.14 (45%) |
| pyribbon fp8 | 10,000,000 | 9.195 | 0.00386 [0.0038, 0.00392] | 15,440 / 4,000,000 | 0.99 | 8.02 | 1.18 (15%) |
| pyribbon fp16 | 10,000,000 | 18.390 | 1.49e-05 [1.33e-05, 1.67e-05] | 298 / 20,000,000 | 0.98 | 16.03 | 2.36 (15%) |
| Xor8 | 10,000,000 | 9.840 | 0.00392 [0.00386, 0.00398] | 15,681 / 4,000,000 | 1.00 | 7.99 | 1.85 (23%) |
| Xor16 | 10,000,000 | 19.680 | 1.61e-05 [1.45e-05, 1.8e-05] | 323 / 20,000,000 | 1.06 | 15.92 | 3.76 (24%) |
| Fuse8 | 10,000,000 | 9.018 | 0.00387 [0.00381, 0.00393] | 15,466 / 4,000,000 | 0.99 | 8.01 | 1.00 (13%) |
| Fuse16 | 10,000,000 | 18.036 | 1.44e-05 [1.28e-05, 1.62e-05] | 288 / 20,000,000 | 0.94 | 16.08 | 1.95 (12%) |
| rbloom 2^-8 | 10,000,000 | 11.542 | 0.00392 [0.00386, 0.00398] | 15,690 / 4,000,000 | 1.00 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 10,000,000 | 23.083 | 1.62e-05 [1.45e-05, 1.81e-05] | 324 / 20,000,000 | 1.06 | 15.91 | 7.17 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 6.98e-05 [6.81e-05, 9.19e-05] | 69.8 [68.1, 91.9] |
| pyribbon fp16 | 1,000 | 8.26e-05 [8.16e-05, 8.92e-05] | 82.6 [81.6, 89.2] |
| Xor8 | 1,000 | 0.000631 [0.000613, 0.000668] | 631 [613, 668] |
| Xor16 | 1,000 | 0.000616 [0.000602, 0.000647] | 616 [602, 647] |
| Fuse8 | 1,000 | 0.000521 [0.000514, 0.000524] | 521 [514, 524] |
| Fuse16 | 1,000 | 0.000527 [0.000517, 0.000622] | 527 [517, 622] |
| rbloom 2^-8 | 1,000 | 0.000278 [0.000275, 0.000307] | 278 [275, 307] |
| rbloom 2^-16 | 1,000 | 0.000334 [0.000333, 0.00036] | 334 [333, 360] |
| pyribbon fp8 | 10,000 | 0.000572 [0.000568, 0.000632] | 57.2 [56.8, 63.2] |
| pyribbon fp16 | 10,000 | 0.000707 [0.000693, 0.000732] | 70.7 [69.3, 73.2] |
| Xor8 | 10,000 | 0.00528 [0.00519, 0.00566] | 528 [519, 566] |
| Xor16 | 10,000 | 0.00501 [0.00499, 0.00507] | 501 [499, 507] |
| Fuse8 | 10,000 | 0.00527 [0.00517, 0.00863] | 527 [517, 863] |
| Fuse16 | 10,000 | 0.00493 [0.0049, 0.00516] | 493 [490, 516] |
| rbloom 2^-8 | 10,000 | 0.00269 [0.00268, 0.00275] | 269 [268, 275] |
| rbloom 2^-16 | 10,000 | 0.00326 [0.00325, 0.00332] | 326 [325, 332] |
| pyribbon fp8 | 100,000 | 0.00561 [0.00556, 0.00567] | 56.1 [55.6, 56.7] |
| pyribbon fp16 | 100,000 | 0.00723 [0.00706, 0.00738] | 72.3 [70.6, 73.8] |
| Xor8 | 100,000 | 0.0571 [0.0556, 0.0593] | 571 [556, 593] |
| Xor16 | 100,000 | 0.0559 [0.0555, 0.0607] | 559 [555, 607] |
| Fuse8 | 100,000 | 0.0521 [0.0507, 0.0588] | 521 [507, 588] |
| Fuse16 | 100,000 | 0.0515 [0.051, 0.0564] | 515 [510, 564] |
| rbloom 2^-8 | 100,000 | 0.0265 [0.0261, 0.0268] | 265 [261, 268] |
| rbloom 2^-16 | 100,000 | 0.0331 [0.0328, 0.0359] | 331 [328, 359] |
| pyribbon fp8 | 1,000,000 | 0.0585 [0.0579, 0.0674] | 58.5 [57.9, 67.4] |
| pyribbon fp16 | 1,000,000 | 0.0721 [0.0716, 0.0734] | 72.1 [71.6, 73.4] |
| Xor8 | 1,000,000 | 0.592 [0.569, 0.6] | 592 [569, 600] |
| Xor16 | 1,000,000 | 0.598 [0.588, 0.621] | 598 [588, 621] |
| Fuse8 | 1,000,000 | 0.541 [0.532, 0.545] | 541 [532, 545] |
| Fuse16 | 1,000,000 | 0.538 [0.529, 0.555] | 538 [529, 555] |
| rbloom 2^-8 | 1,000,000 | 0.279 [0.271, 0.295] | 279 [271, 295] |
| rbloom 2^-16 | 1,000,000 | 0.341 [0.331, 0.394] | 341 [331, 394] |
| pyribbon fp8 | 10,000,000 | 0.775 [0.774, 0.779] | 77.5 [77.4, 77.9] |
| pyribbon fp16 | 10,000,000 | 0.925 [0.919, 0.935] | 92.5 [91.9, 93.5] |
| Xor8 | 10,000,000 | 6.23 [6.18, 6.24] | 623 [618, 624] |
| Xor16 | 10,000,000 | 6.26 [6.24, 6.26] | 626 [624, 626] |
| Fuse8 | 10,000,000 | 5.7 [5.7, 5.71] | 570 [570, 571] |
| Fuse16 | 10,000,000 | 5.69 [5.68, 5.69] | 569 [568, 569] |
| rbloom 2^-8 | 10,000,000 | 4.08 [4.08, 4.09] | 408 [408, 409] |
| rbloom 2^-16 | 10,000,000 | 6.26 [6.25, 6.28] | 626 [625, 628] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | 46 [45, 47.6] | 39.9 [38.9, 60.4] | 53 |
| pyribbon fp16 | 1,000 | 66.9 [58.8, 79.4] | 39.7 [37.8, 40.9] | 74.7 |
| Xor8 | 1,000 | 696 [664, 793] | 704 [675, 757] | 702 |
| Xor16 | 1,000 | 649 [643, 670] | 644 [641, 758] | 656 |
| Fuse8 | 1,000 | 648 [645, 843] | 650 [639, 717] | 655 |
| Fuse16 | 1,000 | 650 [645, 767] | 650 [647, 795] | 657 |
| rbloom 2^-8 | 1,000 | 282 [281, 304] | 251 [249, 305] | 289 |
| rbloom 2^-16 | 1,000 | 339 [338, 418] | 250 [249, 256] | 346 |
| pyribbon fp8 | 10,000 | 48.4 [47.4, 51.5] | 39.8 [39.1, 40.6] | 55.7 |
| pyribbon fp16 | 10,000 | 65.2 [64.4, 67.5] | 40.2 [39.4, 40.9] | 71.8 |
| Xor8 | 10,000 | 653 [651, 670] | 655 [651, 712] | 660 |
| Xor16 | 10,000 | 657 [652, 760] | 653 [649, 724] | 664 |
| Fuse8 | 10,000 | 658 [651, 958] | 658 [651, 699] | 665 |
| Fuse16 | 10,000 | 660 [653, 748] | 658 [651, 671] | 667 |
| rbloom 2^-8 | 10,000 | 286 [285, 288] | 256 [254, 263] | 293 |
| rbloom 2^-16 | 10,000 | 347 [342, 382] | 257 [256, 264] | 353 |
| pyribbon fp8 | 100,000 | 46 [45.3, 47.4] | 44.5 [43.4, 49.3] | 52.6 |
| pyribbon fp16 | 100,000 | 66.7 [66.2, 67.3] | 44 [43.5, 47] | 73.6 |
| Xor8 | 100,000 | 650 [647, 694] | 650 [645, 663] | 657 |
| Xor16 | 100,000 | 652 [650, 758] | 652 [649, 730] | 660 |
| Fuse8 | 100,000 | 652 [650, 665] | 659 [652, 694] | 659 |
| Fuse16 | 100,000 | 659 [652, 683] | 659 [653, 710] | 666 |
| rbloom 2^-8 | 100,000 | 292 [282, 347] | 254 [252, 256] | 299 |
| rbloom 2^-16 | 100,000 | 349 [345, 397] | 259 [256, 265] | 355 |
| pyribbon fp8 | 1,000,000 | 52.2 [51.2, 54.1] | 51 [50.6, 52.6] | 58.9 |
| pyribbon fp16 | 1,000,000 | 72.5 [71.2, 72.9] | 55.4 [53, 92.4] | 79.1 |
| Xor8 | 1,000,000 | 669 [659, 717] | 663 [658, 667] | 676 |
| Xor16 | 1,000,000 | 666 [661, 787] | 665 [658, 751] | 673 |
| Fuse8 | 1,000,000 | 662 [660, 715] | 660 [654, 706] | 669 |
| Fuse16 | 1,000,000 | 683 [662, 732] | 678 [663, 750] | 690 |
| rbloom 2^-8 | 1,000,000 | 296 [291, 355] | 264 [262, 297] | 303 |
| rbloom 2^-16 | 1,000,000 | 355 [353, 357] | 270 [269, 343] | 362 |
| pyribbon fp8 | 10,000,000 | 86.3 [84.8, 98.5] | 88 [85.2, 120] | 93 |
| pyribbon fp16 | 10,000,000 | 136 [128, 149] | 106 [104, 109] | 144 |
| Xor8 | 10,000,000 | 748 [736, 780] | 741 [734, 840] | 756 |
| Xor16 | 10,000,000 | 761 [752, 780] | 768 [752, 781] | 768 |
| Fuse8 | 10,000,000 | 753 [730, 805] | 733 [729, 756] | 760 |
| Fuse16 | 10,000,000 | 756 [749, 780] | 762 [753, 799] | 763 |
| rbloom 2^-8 | 10,000,000 | 418 [412, 437] | 337 [333, 349] | 425 |
| rbloom 2^-16 | 10,000,000 | 613 [607, 672] | 360 [352, 420] | 622 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 1,000 | `contains_many` | 20.4 | 22.5 | 21.1 |
| pyribbon fp8 | 1,000 | `contains_many` over an int `array('q')` | 27.7 | 33 | 30.3 |
| pyribbon fp16 | 1,000 | `contains_many` | 14.5 | 22.9 | 17.8 |
| pyribbon fp16 | 1,000 | `contains_many` over an int `array('q')` | 18.1 | 32.8 | 23.3 |
| Xor8 | 1,000 | per-key loop | 1.47 | 1.48 | 1.47 |
| Xor16 | 1,000 | per-key loop | 1.51 | 1.52 | 1.51 |
| Fuse8 | 1,000 | per-key loop | 1.51 | 1.5 | 1.5 |
| Fuse16 | 1,000 | per-key loop | 1.5 | 1.51 | 1.5 |
| rbloom 2^-8 | 1,000 | per-key loop | 3.2 | 3.84 | 3.47 |
| rbloom 2^-16 | 1,000 | per-key loop | 2.87 | 3.83 | 3.25 |
| pyribbon fp8 | 10,000 | `contains_many` | 20.4 | 22.6 | 21.5 |
| pyribbon fp8 | 10,000 | `contains_many` over an int `array('q')` | 28.4 | 33.4 | 30.7 |
| pyribbon fp16 | 10,000 | `contains_many` | 14.6 | 22.9 | 17.8 |
| pyribbon fp16 | 10,000 | `contains_many` over an int `array('q')` | 18.3 | 33.3 | 23.6 |
| Xor8 | 10,000 | per-key loop | 1.5 | 1.51 | 1.5 |
| Xor16 | 10,000 | per-key loop | 1.5 | 1.5 | 1.49 |
| Fuse8 | 10,000 | per-key loop | 1.49 | 1.5 | 1.49 |
| Fuse16 | 10,000 | per-key loop | 1.47 | 1.5 | 1.48 |
| rbloom 2^-8 | 10,000 | per-key loop | 3.35 | 3.75 | 3.52 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.8 | 3.68 | 3.18 |
| pyribbon fp8 | 100,000 | `contains_many` | 20.3 | 23 | 21.6 |
| pyribbon fp8 | 100,000 | `contains_many` over an int `array('q')` | 26.8 | 32.3 | 29.6 |
| pyribbon fp16 | 100,000 | `contains_many` | 14.7 | 23 | 17.9 |
| pyribbon fp16 | 100,000 | `contains_many` over an int `array('q')` | 18.1 | 33.3 | 23.5 |
| Xor8 | 100,000 | per-key loop | 1.51 | 1.51 | 1.51 |
| Xor16 | 100,000 | per-key loop | 1.5 | 1.51 | 1.51 |
| Fuse8 | 100,000 | per-key loop | 1.49 | 1.49 | 1.5 |
| Fuse16 | 100,000 | per-key loop | 1.47 | 1.49 | 1.49 |
| rbloom 2^-8 | 100,000 | per-key loop | 3.38 | 3.8 | 3.57 |
| rbloom 2^-16 | 100,000 | per-key loop | 2.78 | 3.73 | 3.18 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 19.9 | 22.2 | 21 |
| pyribbon fp8 | 1,000,000 | `contains_many` over an int `array('q')` | 26.5 | 32.1 | 29 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 14 | 22.2 | 17.2 |
| pyribbon fp16 | 1,000,000 | `contains_many` over an int `array('q')` | 16.9 | 31.8 | 22.1 |
| Xor8 | 1,000,000 | per-key loop | 1.48 | 1.48 | 1.48 |
| Xor16 | 1,000,000 | per-key loop | 1.47 | 1.49 | 1.47 |
| Fuse8 | 1,000,000 | per-key loop | 1.48 | 1.49 | 1.49 |
| Fuse16 | 1,000,000 | per-key loop | 1.45 | 1.49 | 1.47 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 3.27 | 3.72 | 3.47 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.73 | 3.7 | 3.14 |
| pyribbon fp8 | 10,000,000 | `contains_many` | 16.5 | 21.4 | 18.6 |
| pyribbon fp8 | 10,000,000 | `contains_many` over an int `array('q')` | 21.3 | 30.5 | 24.8 |
| pyribbon fp16 | 10,000,000 | `contains_many` | 8.61 | 18.6 | 11.7 |
| pyribbon fp16 | 10,000,000 | `contains_many` over an int `array('q')` | 9.82 | 24.9 | 14.1 |
| Xor8 | 10,000,000 | per-key loop | 1.32 | 1.33 | 1.3 |
| Xor16 | 10,000,000 | per-key loop | 1.28 | 1.29 | 1.29 |
| Fuse8 | 10,000,000 | per-key loop | 1.31 | 1.31 | 1.31 |
| Fuse16 | 10,000,000 | per-key loop | 1.29 | 1.3 | 1.29 |
| rbloom 2^-8 | 10,000,000 | per-key loop | 2.33 | 2.96 | 2.61 |
| rbloom 2^-16 | 10,000,000 | per-key loop | 1.6 | 2.76 | 2.02 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 1,000 | 85.3 [83.7, 90.7] build ns/key | 86.3 [85.5, 88.4] | 56.2 [55.5, 57.7] | 11.8 |
| rbloom 2^-16, builtin hash() | 1,000 | 153 [148, 192] build ns/key | 145 [143, 148] | 55.7 [55, 55.8] | 9.13 |
| pyfusefilter: Python hashing only | 1,000 | 215 [211, 240] build ns/key | 191 [190, 235] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 43.9 [42.3, 51.4] build ns/key | 121 [121, 123] | 122 [121, 123] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 44.2 [41.9, 69.7] build ns/key | 121 [119, 123] | 121 [120, 128] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 40.1 [39.4, 53.8] build ns/key | 126 [122, 162] | 121 [120, 124] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000 | 40.3 [39.5, 41.9] build ns/key | 122 [121, 134] | 121 [120, 123] | n/a |
| rbloom: `hash_func` call only | 1,000 | n/a | 119 [118, 141] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000 | 75.5 [75.2, 78] build ns/key | 86.2 [85.7, 87.1] | 55.9 [55.1, 57.6] | 12.4 |
| rbloom 2^-16, builtin hash() | 10,000 | 138 [135, 139] build ns/key | 144 [143, 144] | 56.2 [55.4, 57.3] | 9.14 |
| pyfusefilter: Python hashing only | 10,000 | 203 [200, 206] build ns/key | 192 [191, 194] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 32 [31.1, 46.8] build ns/key | 122 [122, 128] | 122 [121, 126] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 30.8 [30.7, 31] build ns/key | 128 [121, 155] | 122 [120, 125] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 27.4 [27, 31.4] build ns/key | 122 [121, 142] | 121 [121, 124] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 27.7 [27.2, 30.1] build ns/key | 121 [121, 142] | 125 [121, 150] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 125 [125, 127] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 100,000 | 77.3 [75, 81.6] build ns/key | 88 [87, 91.8] | 58.7 [57.9, 59.5] | 12 |
| rbloom 2^-16, builtin hash() | 100,000 | 137 [136, 139] build ns/key | 149 [148, 151] | 64.8 [63.2, 66.6] | 8.58 |
| pyfusefilter: Python hashing only | 100,000 | 203 [201, 212] build ns/key | 196 [192, 231] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 72.8 [69.8, 74.8] build ns/key | 125 [123, 128] | 127 [123, 143] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 73 [69.7, 81.5] build ns/key | 126 [125, 151] | 128 [124, 248] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 26.7 [26.6, 27.8] build ns/key | 125 [122, 130] | 123 [122, 125] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 100,000 | 26.9 [26.3, 29.1] build ns/key | 129 [125, 149] | 125 [124, 127] | n/a |
| rbloom: `hash_func` call only | 100,000 | n/a | 120 [119, 131] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 79.9 [79.6, 80.5] build ns/key | 101 [98.9, 121] | 74.1 [73.3, 75.6] | 10.6 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 140 [139, 157] build ns/key | 160 [159, 164] | 78.1 [77.1, 79.3] | 8.05 |
| pyfusefilter: Python hashing only | 1,000,000 | 221 [214, 236] build ns/key | 191 [189, 197] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 89.6 [87.6, 98.1] build ns/key | 133 [131, 173] | 133 [132, 182] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 91.5 [88.4, 94.1] build ns/key | 139 [136, 266] | 136 [136, 141] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 38.9 [37.4, 45.3] build ns/key | 141 [131, 158] | 135 [130, 209] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 37.8 [37.1, 39.1] build ns/key | 137 [134, 144] | 136 [135, 137] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 124 [123, 139] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 10,000,000 | 207 [205, 209] build ns/key | 218 [214, 263] | 143 [140, 149] | 5.37 |
| rbloom 2^-16, builtin hash() | 10,000,000 | 432 [432, 432] build ns/key | 417 [414, 441] | 162 [160, 171] | 3.36 |
| pyfusefilter: Python hashing only | 10,000,000 | 226 [225, 226] build ns/key | 189 [189, 191] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 101 [100, 103] build ns/key | 196 [195, 221] | 204 [196, 282] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 106 [104, 106] build ns/key | 212 [210, 234] | 213 [211, 243] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 53.8 [53.8, 54.6] build ns/key | 191 [187, 211] | 187 [186, 193] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000,000 | 52.7 [52.6, 53.5] build ns/key | 207 [205, 208] | 207 [205, 207] | n/a |
| rbloom: `hash_func` call only | 10,000,000 | n/a | 120 [116, 131] | (same keys) | n/a |

## Results: str keys (`'user:00000000042'`, 16 characters)

### Space at matched false-positive rate

| Filter | n | bits/key | measured FPR [95% CI] | FP / probes | FPR / 2^-bits | min bits/key = log2(1/FPR) | above minimum (bits/key, %) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 8.653 | 0.00394 [0.00388, 0.004] | 15,771 / 4,000,000 | 1.01 | 7.99 | 0.67 (8%) |
| pyribbon fp16 | 10,000 | 17.254 | 1.64e-05 [1.47e-05, 1.82e-05] | 327 / 20,000,000 | 1.07 | 15.90 | 1.35 (9%) |
| Xor8 | 10,000 | 9.883 | 0.00392 [0.00386, 0.00398] | 15,665 / 4,000,000 | 1.00 | 8.00 | 1.89 (24%) |
| Xor16 | 10,000 | 19.747 | 1.61e-05 [1.45e-05, 1.8e-05] | 323 / 20,000,000 | 1.06 | 15.92 | 3.83 (24%) |
| Fuse8 | 10,000 | 10.067 | 0.00392 [0.00386, 0.00398] | 15,685 / 4,000,000 | 1.00 | 7.99 | 2.07 (26%) |
| Fuse16 | 10,000 | 20.102 | 1.33e-05 [1.18e-05, 1.5e-05] | 266 / 20,000,000 | 0.87 | 16.20 | 3.90 (24%) |
| rbloom 2^-8 | 10,000 | 11.542 | 0.00396 [0.00389, 0.00402] | 15,823 / 4,000,000 | 1.01 | 7.98 | 3.56 (45%) |
| rbloom 2^-16 | 10,000 | 23.083 | 1.6e-05 [1.43e-05, 1.78e-05] | 319 / 20,000,000 | 1.05 | 15.94 | 7.15 (45%) |
| pyribbon fp8 | 1,000,000 | 8.993 | 0.00389 [0.00383, 0.00395] | 15,545 / 4,000,000 | 0.99 | 8.01 | 0.99 (12%) |
| pyribbon fp16 | 1,000,000 | 17.986 | 1.52e-05 [1.35e-05, 1.7e-05] | 303 / 20,000,000 | 0.99 | 16.01 | 1.98 (12%) |
| Xor8 | 1,000,000 | 9.840 | 0.0039 [0.00383, 0.00396] | 15,581 / 4,000,000 | 1.00 | 8.00 | 1.84 (23%) |
| Xor16 | 1,000,000 | 19.681 | 1.56e-05 [1.4e-05, 1.74e-05] | 312 / 20,000,000 | 1.02 | 15.97 | 3.71 (23%) |
| Fuse8 | 1,000,000 | 9.044 | 0.00392 [0.00386, 0.00398] | 15,671 / 4,000,000 | 1.00 | 8.00 | 1.05 (13%) |
| Fuse16 | 1,000,000 | 18.088 | 1.69e-05 [1.52e-05, 1.88e-05] | 338 / 20,000,000 | 1.11 | 15.85 | 2.24 (14%) |
| rbloom 2^-8 | 1,000,000 | 11.542 | 0.00393 [0.00387, 0.00399] | 15,714 / 4,000,000 | 1.01 | 7.99 | 3.55 (44%) |
| rbloom 2^-16 | 1,000,000 | 23.083 | 1.55e-05 [1.39e-05, 1.74e-05] | 311 / 20,000,000 | 1.02 | 15.97 | 7.11 (45%) |

### Build time (median [min, max] of the repeats; includes hashing the keys)

| Filter | n | seconds | ns/key |
| --- | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 0.000562 [0.000557, 0.00109] | 56.2 [55.7, 109] |
| pyribbon fp16 | 10,000 | 0.000726 [0.000691, 0.000838] | 72.6 [69.1, 83.8] |
| Xor8 | 10,000 | 0.00434 [0.00426, 0.00443] | 434 [426, 443] |
| Xor16 | 10,000 | 0.00463 [0.00445, 0.00613] | 463 [445, 613] |
| Fuse8 | 10,000 | 0.00505 [0.00439, 0.0102] | 505 [439, 1.02e+03] |
| Fuse16 | 10,000 | 0.00449 [0.00434, 0.0051] | 449 [434, 510] |
| rbloom 2^-8 | 10,000 | 0.00367 [0.00359, 0.00493] | 367 [359, 493] |
| rbloom 2^-16 | 10,000 | 0.00437 [0.00419, 0.00484] | 437 [419, 484] |
| pyribbon fp8 | 1,000,000 | 0.0581 [0.0577, 0.0632] | 58.1 [57.7, 63.2] |
| pyribbon fp16 | 1,000,000 | 0.073 [0.072, 0.0794] | 73 [72, 79.4] |
| Xor8 | 1,000,000 | 0.544 [0.535, 0.556] | 544 [535, 556] |
| Xor16 | 1,000,000 | 0.539 [0.53, 0.563] | 539 [530, 563] |
| Fuse8 | 1,000,000 | 0.476 [0.472, 0.479] | 476 [472, 479] |
| Fuse16 | 1,000,000 | 0.48 [0.471, 0.483] | 480 [471, 483] |
| rbloom 2^-8 | 1,000,000 | 0.379 [0.369, 0.387] | 379 [369, 387] |
| rbloom 2^-16 | 1,000,000 | 0.44 [0.428, 0.472] | 440 [428, 472] |

### Single query: ns per `key in f` call, loop overhead subtracted (median [min, max])

| Filter | n | member | non-member | member, loop overhead not subtracted |
| --- | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | 46.2 [45.8, 46.7] | 41.3 [40.4, 46.3] | 53.6 |
| pyribbon fp16 | 10,000 | 65.8 [64.3, 68.9] | 40.5 [37.8, 42] | 73.1 |
| Xor8 | 10,000 | 581 [571, 609] | 571 [568, 576] | 589 |
| Xor16 | 10,000 | 584 [573, 614] | 610 [574, 665] | 592 |
| Fuse8 | 10,000 | 609 [600, 880] | 632 [587, 717] | 619 |
| Fuse16 | 10,000 | 592 [586, 602] | 598 [585, 629] | 600 |
| rbloom 2^-8 | 10,000 | 380 [372, 386] | 345 [344, 373] | 388 |
| rbloom 2^-16 | 10,000 | 446 [431, 480] | 347 [341, 361] | 454 |
| pyribbon fp8 | 1,000,000 | 53.6 [52.4, 58.2] | 51.5 [49.5, 54.3] | 60.9 |
| pyribbon fp16 | 1,000,000 | 72 [69.4, 90.1] | 50 [49.1, 69.7] | 79.3 |
| Xor8 | 1,000,000 | 590 [585, 622] | 587 [585, 671] | 598 |
| Xor16 | 1,000,000 | 599 [595, 891] | 599 [595, 741] | 606 |
| Fuse8 | 1,000,000 | 594 [590, 693] | 608 [588, 629] | 602 |
| Fuse16 | 1,000,000 | 608 [604, 703] | 602 [601, 698] | 616 |
| rbloom 2^-8 | 1,000,000 | 386 [382, 483] | 353 [351, 362] | 393 |
| rbloom 2^-16 | 1,000,000 | 443 [439, 522] | 359 [354, 367] | 450 |

### Batch query: million keys per second (median)

| Filter | n | API | members | non-members | 50/50 mix |
| --- | ---: | ---: | ---: | ---: | ---: |
| pyribbon fp8 | 10,000 | `contains_many` | 20.4 | 23.3 | 21.8 |
| pyribbon fp16 | 10,000 | `contains_many` | 14.8 | 23.2 | 18.1 |
| Xor8 | 10,000 | per-key loop | 1.71 | 1.71 | 1.7 |
| Xor16 | 10,000 | per-key loop | 1.45 | 1.55 | 1.34 |
| Fuse8 | 10,000 | per-key loop | 1.61 | 1.6 | 1.59 |
| Fuse16 | 10,000 | per-key loop | 1.66 | 1.63 | 1.64 |
| rbloom 2^-8 | 10,000 | per-key loop | 2.56 | 2.79 | 2.67 |
| rbloom 2^-16 | 10,000 | per-key loop | 2.19 | 2.73 | 2.41 |
| pyribbon fp8 | 1,000,000 | `contains_many` | 19.5 | 21.9 | 20.8 |
| pyribbon fp16 | 1,000,000 | `contains_many` | 13.7 | 22.6 | 17 |
| Xor8 | 1,000,000 | per-key loop | 1.6 | 1.66 | 1.63 |
| Xor16 | 1,000,000 | per-key loop | 1.61 | 1.66 | 1.62 |
| Fuse8 | 1,000,000 | per-key loop | 1.64 | 1.65 | 1.65 |
| Fuse16 | 1,000,000 | per-key loop | 1.62 | 1.61 | 1.6 |
| rbloom 2^-8 | 1,000,000 | per-key loop | 2.51 | 2.73 | 2.59 |
| rbloom 2^-16 | 1,000,000 | per-key loop | 2.18 | 2.72 | 2.41 |

### Diagnostic: Python-side hashing separated from the filter probe

| Variant | n | Build | Member ns | Non-member ns | Batch Mkeys/s (50/50 mix) |
| --- | ---: | ---: | ---: | ---: | ---: |
| rbloom 2^-8, builtin hash() | 10,000 | 73.3 [72.9, 74.6] build ns/key | 86.3 [83.3, 87.5] | 55.4 [53.4, 82.7] | 12.1 |
| rbloom 2^-16, builtin hash() | 10,000 | 137 [131, 137] build ns/key | 142 [140, 166] | 53.6 [52.2, 57.7] | 9.24 |
| pyfusefilter: Python hashing only | 10,000 | 139 [133, 178] build ns/key | 124 [119, 142] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.5 [31.1, 39.2] build ns/key | 125 [124, 155] | 129 [122, 150] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 31.4 [30.8, 31.7] build ns/key | 125 [122, 154] | 124 [121, 150] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28.1 [27.7, 31.2] build ns/key | 123 [121, 136] | 127 [121, 166] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 10,000 | 28 [27.5, 30.2] build ns/key | 126 [121, 152] | 135 [122, 159] | n/a |
| rbloom: `hash_func` call only | 10,000 | n/a | 208 [198, 210] | (same keys) | n/a |
| rbloom 2^-8, builtin hash() | 1,000,000 | 78.4 [77.8, 83.8] build ns/key | 95.9 [93.9, 124] | 67.1 [66.4, 69.3] | 11 |
| rbloom 2^-16, builtin hash() | 1,000,000 | 140 [140, 150] build ns/key | 155 [154, 212] | 72.9 [70.2, 83] | 8.1 |
| pyfusefilter: Python hashing only | 1,000,000 | 146 [143, 152] build ns/key | 121 [119, 132] | (same keys) | n/a |
| pyfusefilter xor8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 90.9 [87.8, 97.8] build ns/key | 131 [130, 134] | 131 [130, 136] | n/a |
| pyfusefilter xor16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 99.1 [89.5, 109] build ns/key | 140 [136, 158] | 138 [136, 142] | n/a |
| pyfusefilter fuse8: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 38.4 [37.3, 39.5] build ns/key | 131 [128, 138] | 129 [128, 137] | n/a |
| pyfusefilter fuse16: C core only (pre-hashed keys; probe via cffi call) | 1,000,000 | 39.3 [38.3, 47.5] build ns/key | 137 [136, 144] | 141 [136, 142] | n/a |
| rbloom: `hash_func` call only | 1,000,000 | n/a | 207 [204, 211] | (same keys) | n/a |

## Notes and caveats

- Every filter is built from the same keys, and its FPR is measured on the same disjoint negative probes (4,000,000 for the 8-bit class, 20,000,000 for the 16-bit class). The probe keys differ from all members by construction. Fingerprint widths are discrete (8 or 16 bits) and Bloom filters are continuous, so each Bloom filter is sized for 2^-8 or 2^-16 and its FPR is then measured. Bits/key is reported with the measured FPR and with the overhead above the information-theoretic minimum of log2(1/FPR) bits/key, which lets filters with slightly different FPRs be compared.
- The intervals are 95% Wilson intervals for the stated number of probes. The 16-bit filters have only a few hundred expected false positives, so their FPR, and therefore their 'above minimum' column, is known only to roughly 5-10%.
- All measured FPRs are within 0.5x-2x of 2^-bits.
- `pyfusefilter` hashes every key in Python (`str(key).encode()` then `xxhash.xxh64_intdigest`) on every call and has no batch query. `pyribbon` hashes inside the C call. The headline numbers include these costs because a user pays them. The diagnostic tables separate the Python hashing from the filter probe. The probe-only rows call the library's C function through cffi with a pre-hashed key. The sum of the hashing and probe rows is a lower bound on the shipped call, and the remainder is Python call overhead. pyribbon cannot be split this way because its hash is part of the C call.
- rbloom hashes keys with Python's `hash()` unless it is given a `hash_func`. For `str` and `bytes` that hash is salted per process (and cached in the str object), so it cannot be persisted and it flatters repeated lookups of the same objects. The headline rbloom rows therefore pass an explicit deterministic `hash_func` (ints: a 64-bit multiplicative hash; str: xxh64 of the UTF-8 bytes). Its Python call cost is included in those rows and listed in the diagnostics. The 'builtin hash()' rows in the diagnostics use no callback and show rbloom's own probe cost. For int keys that is a sound configuration, so the win/loss summary counts it among the competitors. A check on 10,000 sequential ints and 1,000,000 probes (target 3.91e-03) gives FPR 4.68e-03 with the default hash() and 4.32e-03 with our hash_func, so rbloom's FPR is sane with either.
- Only pyribbon has a batch API (`contains_many`). For every other library the batch figure is a per-key list comprehension, `[k in f for k in keys]`, marked as such in the table. The 50/50 mix is the throughput of one member batch plus one non-member batch.
- Single-query latency is measured with a tight Python `for` loop over 100,000 random member keys (sampled with replacement) or non-member keys. The same loop without the call is timed in the same repeat and subtracted (median 6.77 ns per empty iteration here). What remains still includes the `k in f` bytecodes, a few ns. The unsubtracted figure is in the last column.
- Timing uses `time.perf_counter_ns` with GC disabled while timed and one warm-up pass. The figures are the median and min/max of 7 repeats (3 at n = 10^7, with no warm-up build there). Keys are generated before timing. Build time includes allocation and hashing but not key generation.
- `int` keys are distinct pseudo-random 63-bit integers from a fixed-seed bijective mixer. `str` keys are `user:` plus 11 digits, with members 0..n-1 and probes from 10^10 upwards. Query keys are fresh objects created in query order, so members and non-members have the same memory layout, and they are the same objects in every repeat (CPython caches a str's hash, which only matters for rbloom's builtin hash rows).
- Numbers are comparable between libraries within this run and not across machines. A `powersave` or `ondemand` governor adds noise. Run on an otherwise idle machine, with turbo and the governor fixed if you can.
