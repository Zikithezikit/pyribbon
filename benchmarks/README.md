# Benchmarks

`bench.py` compares `pyribbon` (fp_bits 8 and 16, default sizing) with `pyfusefilter` (Xor8, Xor16, Fuse8, Fuse16) and
`rbloom` (a Rust Bloom filter sized for 2^-8 and 2^-16). It measures bits/key at the *measured* false-positive rate,
build time, single-query latency and batch throughput, then writes:

* `docs/benchmark.md`: machine info, run parameters, an auto-generated win/loss summary, all tables and caveats;
* `docs/benchmark.png`: six panels for the int keys (space above the minimum, build, FPR, latency for non-members and
  members, batch throughput);
* `docs/benchmark.json`: every raw repeat.

## Run

```
make bench                                    # installs '.[bench]', full run, writes docs/benchmark.{png,md,json}
python benchmarks/bench.py --quick --out-dir /tmp/bench-quick   # smoke test, about 10 s, numbers are not meaningful
python benchmarks/bench.py --sizes 1000 100000 --repeats 9 --out-dir /tmp/bench-mine
```

Run the full benchmark on an otherwise idle machine (it pins itself to one CPU, but cannot stop other load).
Expect roughly 6 minutes for sizes 1e3..1e6 and about 4 more for 1e7 (an estimate; on a shared machine it is slower).
`python benchmarks/bench.py --help` works without any of the optional packages; a missing library is skipped with a
message and listed in the report.

## Method

* **Keys.** Ints: distinct pseudo-random 63-bit values from a fixed-seed bijective mixer. Strs: `user:` plus an 11-digit
  counter (16 characters), at n = 1e4 and 1e6. Members are counters `0..n-1`, negative probes start at counter 10^10, so
  the two sets are disjoint by construction. Query keys are fresh objects created in query order (so members and
  non-members have the same memory layout); all keys are generated before any timing.
* **Same measured FPR.** Every filter is built from the same keys and its FPR is counted on the same probe stream
  (4e6 probes for the 8-bit class, 2e7 for the 16-bit class by default, `--probes`). Reported with a 95% Wilson interval,
  the false-positive count, and the overhead above the information-theoretic minimum log2(1/FPR). For pyfusefilter the
  probes use its own `hash()` plus its C probe function (hashing shared by the four filters); the script asserts that
  this gives exactly the same count as `key in f` on 20 000 probes before using it.
* **Timing.** `perf_counter_ns`, GC off while timed, pinned to one CPU, one warm-up, median and min/max of 7 repeats
  (3 at n = 1e7). Latency is a tight `for k in keys: k in f` loop over 1e5 keys; the empty loop over the same keys is
  timed in the same repeat and subtracted (the unsubtracted figure is also reported). Batch throughput uses
  `contains_many` for pyribbon and `[k in f for k in keys]` for libraries without a batch API (marked in the table).
* **As shipped.** pyfusefilter hashes every key in Python (`str(key).encode()` + xxhash) on every call and build; pyribbon
  hashes in C. The headline numbers include this. The "Diagnostic" table separates Python hashing from the C probe and
  C-only build for pyfusefilter, and shows rbloom's `hash_func` callback cost.
* **rbloom hashing.** The headline rbloom rows pass an explicit deterministic `hash_func` (ints: multiplicative hash;
  str: xxh64) because the default hash of `str`/`bytes` is salted per process. Rows with `builtin hash()` use no callback;
  for int keys that is sound (a check on sequential ints is printed in the notes), so the summary counts them as
  competitors. In smoke runs rbloom's measured FPR was within roughly 0.8x-1.3x of its target (see the `FPR / 2^-bits` column).
* **Sizes.** 1e7 is in the default run: at 1e6 the baselines build in about 0.6 s (flat at about 600 ns/key from 1e3 up),
  so 1e7 costs them about 6-7 s per build, 3 repeats each; peak memory is a few GB. Use `--sizes` to drop it. Only
  pyribbon's and the baselines' 1e6 cells were timed during development; the 1e7 cell has not been run.
* **Not measured:** a Python `set` as the exact-membership baseline, `fastbloom-rs` (its batch API would be the only
  Bloom batch comparison), memory use of the Python wrappers, or other platforms.

If a run fails in a late cell, the reports are still written from the finished cells and marked INCOMPLETE.
