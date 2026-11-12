# RESEARCH

Background research for pyribbon, written 2026-11-12. Every claim carries a source tag. Anything I could not
verify is marked **unverified**, and my own derivations are marked *(inference)*. No number below comes from
pyribbon itself, because pyribbon has no code yet. Numbers from the papers or from other projects are their
authors' claims; we re-measure ours in Phase 2 (see DESIGN.md, "Evidence plan").

Source tags: **[R]** Dillinger & Walzer, *Ribbon filter: practically smaller than Bloom and Xor*, arXiv:2103.02515v2
(Mar 2021; no venue printed in the PDF, so treat as a preprint). **[B]** Dillinger, Hübschle-Schneider, Sanders,
Walzer, *Fast Succinct Retrieval and Approximate Membership using Ribbon*, arXiv:2109.01892v2 (SEA 2022,
LIPIcs 233, art. 4, DOI 10.4230/LIPIcs.SEA.2022.4; the venue comes from the Dagstuhl page, not from the PDF).
Page numbers are PDF pages. A research agent read both PDFs and the tables were checked visually; the notes with
the full page citations are kept outside the repo.

## 1. What a ribbon filter is

A static approximate-membership filter built by solving a linear system over GF(2). Each key `x` yields one
equation: a start position `s(x)`, a `w`-bit coefficient vector `c(x)` (forced to start with 1), and an `r`-bit
fingerprint `b(x)`. The solution `Z` (m rows of r bits) is the filter. A query recomputes `s, c, b`, XORs the rows of
`Z` selected by `c` inside the window `[s, s+w)`, and compares with `b` [R §2-3 p3; B §3 p6]. The matrix is *banded*
(every row touches only `w` consecutive columns), so the elimination is cheap and the memory access is local.

## 2. Variants

| Variant | Source | Summary | Fit for v0.1 |
|---|---|---|---|
| **Standard** | R §3; B §3.1, §8 | One equation per key with RHS = r-bit fingerprint. FP = 2^-r exactly (the fingerprint is independent of the equations). Construction can fail, so seeds are retried. | **Yes** |
| Standard + "smash" | R §3.1 p5, Table 1 | Not a separate filter. Start positions are biased toward the first and last columns so they are not starved. Helps small `m`. ~3 ns/query measured by the authors. | Optional tweak, deferred |
| **Homogeneous** | R §4; B §3.3, §9 | RHS is 0 for every key; unused rows get pseudo-random values; query is true iff the XOR is 0. Construction never fails. FP = p + (1-p)·2^-r, so it can exceed 2^-r, and small filters have high FP variance that cannot be detected at build time [R p5-6]. | Roadmap |
| Balanced (experimental) | R §6 p10-11 | Standard ribbon + soft sharding + greedy load balancing, two candidate locations per key plus per-bucket metadata. The paper says "implementation details see [26]" (a GitHub fork), so the PDF is not a full spec. Claims 1.005λ+0.008 bits/key at w=64. **My memory was right that it exists; it appears only in [R], never as a named variant in [B].** | Roadmap (needs the code, not just the paper) |
| **BuRR** | B §3.2, §10-11 | Overloaded table (m < n) plus per-bucket bumping of start-position ranges plus recursion over 4 layers. Overhead 0.06-1.4% in their tables. Needs a bucket sort by start position, row-level rollback, tuned thresholds per (w, r, b). | Roadmap |
| Bu1RR, sparse-coefficient BuRR | B §3.5, §11 | BuRR variants (bump-once: ~20% slower, slightly worse overhead; sparse coefficients: faster for large r). | Roadmap |

Sorted/in-order construction and sharding are techniques and have no row above [R §5.4 p9; B §5 p13].

## 3. Space overhead vs false-positive rate

Overhead is measured against the information-theoretic bound `λ = log2(1/f)` bits per key [R §4 p5].

* Competitors (their numbers): Bloom ≥ 44% [R §1 p1; B §12 p36]; blocked Bloom ≥ ~50% at 1% [R Table 2 p11]; Xor
  23% (Xor+ 14%) [R Table 2; B p36].
* Standard ribbon: `m = (1+ε)·n` rows of `r` bits, so `(1+ε)·r` bits/key and FP = 2^-r [R §2 p3]. How large ε must be
  to make construction succeed is §5 below.
* Homogeneous, measured, n = 1e6 [R Table 2 p11]: w=64 gives 8.0 / 10.1 / 12.7% at r = 3 / 7 / 11; w=128 gives
  4.2 / 5.1 / 7.3%; w=32 gives 16.1 / 20.6 / 28.0%. Rule of thumb ε ≈ (4 + r/4)/w, fitted at m = 3e7 [R eq. 7 p7].
* BuRR at r=7 [B Tables 2-3 p48-49]: w=64 0.21-0.48%, w=32 0.82-1.4%, w=128 0.06-0.18%.
* Authors' advice on width: w = 32 or 64 on a 64-bit machine; w=32 is only 15-20% faster than 64 for ~4x the
  overhead; w=128 pays "a large performance penalty for little additional gain" [B p11, p34].
* The papers use three different ε conventions (`m=(1+ε)n` in [R §2]; `m = n/(1-ε) + w - 1` in
  [R Thm 3.2, B §8]; `ε = 1 - m/n` in [B §11-12]). DESIGN.md defines one convention and uses it throughout.

## 4. Construction algorithm (standard ribbon)

On-the-fly banded Gaussian elimination, "Rapid Incremental Boolean Banding ON the fly" [R §3 p3-4, Alg. 1; B §6
p14, Alg. 1]. State: `m` slots; slot `i` holds a `w`-bit coefficient word and an `r`-bit result; empty means
coefficient word 0; every non-empty slot's lowest bit is 1 (its pivot).

```
insert(x):  i = s(x); c = c(x); b = b(x)
  loop:
    if slot[i] empty:   slot[i] = (c, b); return OK
    c ^= slot[i].c;  b ^= slot[i].b            # lowest bit now 0
    if c == 0:          return (b == 0) ? OK_REDUNDANT : FAIL
    j = ctz(c);  i += j;  c >>= j              # re-anchor the window at the next pivot
```

(Paraphrase of the algorithm in the papers, not copied code.) The invariant is that the pending equation always has
the form `c · Z[i, i+w) = b` with lowest bit of `c` set, so the loop advances `i` at least once per iteration and ends
in at most `w-1` steps. The "first" coefficient is the least-significant bit and shifts are logical.

Back-substitution runs `i = m-1 .. 0`: if slot `i` is occupied, `Z[i] = b_i XOR (XOR of Z[i+k] for k ≥ 1 with bit k
of c_i set)`; an empty slot gets 0 for a standard filter [R p4; B Alg. 2 p19]. The pseudocode as printed in [B] is
shorthand (it omits `b_i` and has `Z_i` on both sides); the reading above follows from the invariant *(inference)*.

* Insertion order does not matter for success or work. The set of filled slots and the displacement sum are
  invariant to insertion order [R §3 p4-5; B §7.2 p16], so no pre-sort by start position is needed (unlike SGAUSS,
  its predecessor). Whether sorted order helps wall-clock through cache locality is **unverified**: neither paper
  measures it for standard ribbon. We can measure that ourselves.
* Insertions never modify existing rows, so a build can stop at the first failure and be rolled back [R p4]; this is
  what BuRR and Balanced Ribbon exploit.
* Alloc `m = n/(1-ε) + w - 1` (B) so every start in `[0, m-w]` keeps its window inside the table.
* The authors' preferred layout is the interleaved column-major one (ICML): `r` consecutive `w`-bit words
  hold the same column bit for `w` consecutive rows, so a query touches at most two `w`-bit words per result bit
  [R §5.2 p8, Fig. 6; B App. A.5 p42]. `m` must be a multiple of `w`. A query short-circuits at the first mismatching
  result bit, so a negative query fetches ~2 bits on average [B p6, p12].
* The papers use no SIMD and no intrinsics except builtins for prefetch, clz/ctz and parity [R §7 p11]; SIMD queries
  are stated future work [R §8 p12].

## 5. Construction failure vs overhead and width; retry

Standard-ribbon overhead needed for a target failure probability, from [R Table 1 p10] (ε as `(m-n)/n`, unsmashed
columns, `m` = slots; the header is ambiguous, so I read the large-`m` columns as unsmashed):

| w | failure target | m = 2^14 | m = 2^17 | m = 2^24 | slope per doubling of m |
|---|---|---|---|---|---|
| 128 | 50% | 1.1% | 2.2% | 4.7% | +0.38% |
| 128 | 5% | 2.6% | 3.7% | 5.9% | +0.38% |
| 128 | 0.1% | 4.6% | 5.8% | >7% | +0.38% |
| 64 | 50% | 3.8% | 6.3% | 11.7% | +0.83% |
| 64 | 5% | 7.0% | 9.4% | 15.0% | +0.83% |
| 64 | 0.1% | 11.5% | 13.8% | >19% | +0.83% |
| 32 | add-until-fail | 13.2% | 19.2% | 35.2% | +2% |

* The overhead needed grows with log n at fixed w, with no sharp threshold: "Ribbon does not exhibit sharp
  threshold behavior" [R §5.4 p9]. Theory: `w = Θ(log n / ε)` gives success w.h.p. [R Thm 3.1 p3; B Thm 4 p14].
* [B p6] independently: the smallest overhead for n = 1e6, w = 128 is "around 3.3% (for construction success
  rate 50%)", consistent with extrapolating [R Table 1] *(inference)*.
* The authors judge a ~5% failure chance a good space-time trade-off; "almost sure" success needs significantly more
  space [R §5.4 p9]. All their standard-ribbon configurations target ~99% success or better [R §7 p12].
* On any failed insertion, restart with new hash functions [B §8 p18, Alg. 2 p19]. Reseeding recipe: XOR
  the stock 64-bit hash with a pseudo-random seed, then multiply by a large odd constant; their testing found
  independent success probabilities [R §5.3 p9]. Alternative: grow `m` by a factor `(w+1)/w`, "similar or better"
  success probability than a fresh hash [R p9]. The maximum number of attempts is not given in either paper
  (**unverified**; we choose it ourselves and measure).
* Homogeneous ribbon avoids failure (the all-zero RHS is always solvable) but costs FP exactness and needs
  `ε·w` proportional to `r` [R p5; B Lemma 12-13 p21].
* For tiny sets, the failure and FP statements are asymptotic in `n ≫ w`. The tables start at
  `m = 2^10`. Behaviour for `n < w` is not covered by the papers (**unverified**), so v0.1 must handle small `n`
  by measurement (DESIGN.md).

## 6. Query path and hash requirements

* Standard query: for each of the `r` columns compute `parity(c AND window_j)`; the `r` parity bits form the
  result; return true iff result == `b(x)` (homogeneous: result == 0) [R eq. 1 p3, §4 p5]. Cost per column: a
  `w`-bit AND + popcount-parity over at most two adjacent words in ICML [R p8].
* Theory assumes fully random hash functions [B p2]. In practice everything is derived from one stock hash
  `H(x)`. `H` should be 64 bits: a 64-bit hash is "enough for almost all non-cryptographic applications" because
  `2^32` keys in one filter add a baseline FP floor of only `2^-32` [R §5.3 p9]. The start position uses fastrange
  (multiply-shift on the high bits of `H`), and the remaining bits must be uncorrelated with it: "multiplying H(x) by
  a large odd constant (as with Knuth multiplicative hash) seems to suffice" [R p9]. [B §12 p32] uses a 64-bit master
  hash code and derives more pseudo-random bits with an LCG whose multiplier is 1 mod 4 and whose summand is odd
  (a bijection on 2^64); linear combinations of two parts of the code "did not work well" for 64 bits.
* The coefficient vector is forced to start with 1 (the lowest bit, the row at `s(x)`); this also avoids failures from
  keys with `c(x) = 0^w` [R p3 and fn. 11; B p14].
* Neither paper gives a concrete split of one 64-bit hash. The need is about
  `log2(m) + (w-1) + r`, e.g. 30 + 63 + 8 = 101 bits for `m = 2^30`, `w = 64`, `r = 8`, so a straight slice is
  impossible and separate remixes are required *(inference)*. DESIGN.md specifies ours.
* Standard ribbon has FP = 2^-r only if `b(y)` is independent of `(s(y), c(y))` and of the stored
  equations [R §2 p3]. Any correlation between the fingerprint bits and the start/coefficient bits breaks the
  guarantee. Our statistical FP tests guard against that.

## 7. Parallel, SIMD, sharding (all roadmap)

* Hard sharding (hash-partition into shards) and soft sharding (one system, shards share the `w-1` overlap) are
  described in [R §5.4 p9]; natural shard size ≈ `w²/4` slots. Sharding also caps construction temp memory [B p31].
* Back-substitution is not efficiently parallelisable inside one system; [B §3.5 p9, §11.3 p30] suggests bumping `w`
  positions to cut it into independent blocks. Whether this was implemented is **unverified** (the paper only
  measures many independent filters: speedup 65-71 on 64 cores + hyperthreads [B §12 p34, Fig. 16 p51]).
* SIMD: the authors call row-major SIMD "not generally workable" and list AVX512-POPCNT / 8-bit ICML as
  future work [R §5.2 p8, §8 p12].

## 8. Open points (paper-level)

* Max retry count, and the n / failure probability behind Table 2's standard-ribbon "14;20" and "6;8" overheads:
  not stated (**unverified**).
* Balanced Ribbon internals: only in code, not in the PDF (**unverified**).
* Cache effect of sorted vs random insertion for standard ribbon: not measured in the papers (**unverified**).
* [R p8]'s "around 1% additional overhead" for fractional `r`: Table 2 does not isolate it (**unverified**).
* Typos found in the printed papers: `s(x) ∈ [m-w-1]` should be `[m-w+1]` (B Alg. 2 line 2 agrees); the printed BuRR
  bucket-size exponent and Theorem 3's `O()` (a lower bound on `w` is meant) look like typesetting slips.

## 9. RocksDB's implementation (read for ideas only)

Provenance: `github.com/facebook/rocksdb` now redirects to `github.com/meta/rocksdb`; read at commit
`ae03d4a88f7ea1529c8c9ec9c354f50d441d0a10` (2026-11-11) on 2026-11-12: `util/ribbon_alg.h`, `util/ribbon_impl.h`,
`util/ribbon_config.{h,cc}`, `table/block_based/filter_policy.cc`; the blog post
<https://rocksdb.org/blog/2021/12/29/ribbon-filter.html>; the RocksDB-Bloom-Filter wiki page.

RocksDB is "dual-licensed under both the GPLv2 ... and Apache 2.0 License", at the
licensee's option (README L25-27). `COPYING` is stock GPLv2 with no linking exception; the ribbon files carry only the
dual header; `filter_policy.cc` additionally carries LevelDB's BSD-3 notice. My reading, not legal advice: reading
the code to learn ideas creates no obligation, but copying or line-by-line porting (even C++ to C) would create a
derivative work. Apache-2.0 §3 grants a patent licence only to users of that code; I did not search for patents
on ribbon filters (**unverified** either way). Policy for pyribbon: no RocksDB code, no RocksDB constants, our own
seed mixing and naming; every algorithmic step cites [R]/[B].

What it does (paraphrased from the files above):

* Banding uses no sorting or bucketing: keys are inserted in arrival order, "resembling hash table insertion"; the
  first row to claim a pivot column keeps it; a row that reduces to zero is accepted iff its result is also zero
  (duplicate keys and equal hashes are harmless) (`ribbon_alg.h` L251-262, L590-595). This matches [R §3].
* Each key gets one 64-bit hash (XXH3-64), computed once and stored by the builder; every retry applies a seeded
  one-to-one mix to the stored hash rather than rehashing the key; start = multiply-high range reduction (top
  bits); coefficient row = the hash times an odd constant; result bits from the byte-swapped product
  (`ribbon_impl.h` L176-335, L394-436). Authors measured ~1.10 average attempts for r=128, ~1e5 keys (L403-406).
  Their weak-hash tests showed sequential seeds correlating with XXH3-preview/Murmur1, hence the seed pre-mix
  (L147-160).
* The layout is interleaved blocks of `w` slots with one `w`-bit segment per result column (ICML in [R]); fractional
  bits per key by mixing `b-1` and `b` columns across blocks; segments are little-endian on disk; the last valid start
  is bit 0 of the last block, so a query never reads past the buffer. `num_slots` must be a multiple of `w`; a
  filter with fewer than 2 blocks is rejected (`ribbon_alg.h` L875-1124; `filter_policy.cc` L1759-1766).
* The per-seed failure target is 1 in 20, with 256 seeds; on exhaustion it builds a Bloom filter instead
  (`filter_policy.cc` L757-769, L1004). Growing the table with the same seed is not independent, so they reseed
  (`ribbon_impl.h` L649-653).
* Homogeneous is implemented but disabled in RocksDB's filter (`kHomogeneous` false): "FP rate can quickly
  explode in cases where corresponding non-homogeneous filter would fail" (`ribbon_impl.h` L55-60).
* The config tables come from simulation ("we don't have good formulas", `ribbon_config.h` L35-37): they
  insert fresh keys until the first failure and take the 50th / 95th / 99.9th percentile of the fill level. Only
  `w` = 64 and 128 are configured. Past 2^17 slots RocksDB extrapolates log-linearly (+0.0083 overhead per doubling for
  w=64, +0.0038 for w=128); the 1e6-1e8 columns below are therefore extrapolated, with no simulation behind them (**unverified**).

Overhead `slots/n - 1` (percent) for a per-attempt success rate of 95%, no smash, derived by a research agent
from RocksDB's `ribbon_config.cc` data (before rounding slots up to a multiple of `w`):

| n | 1e3 | 1e4 | 1e5 | 1e6 | 1e7 | 1e8 |
|---|---:|---:|---:|---:|---:|---:|
| w = 64 | 4.9 | 6.6 | 9.3 | 12.0 | 14.8 | 17.6 |
| w = 128 | 2.3 | 2.5 | 3.5 | 4.8 | 6.1 | 7.3 |

Independent cross-check: at `m = 2^17`, [R Table 1] gives 9.4% (w=64) and 3.7% (w=128) for 5% failure, and
RocksDB's data gives 9.40% and 3.61%. Two sources agree, so these are the numbers I use to propose defaults; Phase 2
re-measures them.

RocksDB's blog claims (their numbers, **not reproduced**): "~30% space savings for 3-4x CPU", "100 million keys in
one filter saves 27% space vs. Bloom rather than 30% for 100,000 keys", temporary memory "~230 bits per key for
128-bit Ribbon vs. ~75 bits per key for Bloom".

My inferences from the RocksDB code: (a) the coefficient/start/fingerprint bits should come from independent words, because
RocksDB's r=128 row has only 64 bits of entropy from a 64-bit hash (works in their tests, but the analysis assumes
random rows); (b) small `n` is quantised badly (needs ≥ 2 blocks), so we need an explicit minimum size; (c) the
coefficient row must never be zero; (d) with `w = 64` the overhead at large `n` is much worse than with `w = 128`
(12% vs 4.8% at 1e6), which matters for the "honest comparison" with fuse filters.

## 10. Prior art and licensing

Surveyed 2026-11-12 by reading metadata, READMEs, licence files and headers (shallow clones; no builds, no tests
run). All speed/space/FPR figures quoted by these projects are **their claims, not reproduced**.

| Project | Lang | Licence (file read) | What it is |
|---|---|---|---|
| `integrallis/pleat` (crates.io 0.1.0) | Rust | MIT OR Apache-2.0 | Homogeneous w=64 + standard w=128, u64 keys only, serialization with magic + FNV-1a trailer. "Partition-instead-of-sort" = a counting pass that buckets keys by start window; the result is bit-identical to arrival-order construction, i.e. a build-speed trick only. "Verify by checksum" means a trailer over the serialized blob (integrity), **not** a membership check. Published 0.1.0 says "close to Bloom-filter speed"; repo HEAD says it "does not close" the gap, and its own table shows pleating *slower* at 1M keys (26.1 vs 23.8 ns/key). 25 downloads. |
| `WilliamRagstad/ribbon-filter` (0.2.0) | Rust | MIT OR Apache-2.0 | Standard + homogeneous, w ≤ 128, caller-supplied `BuildHasher` (so output is not portable), README: "not suitable for production use yet". |
| `FastFilter/fastfilter_cpp` | C++ | Apache-2.0 root; `src/ribbon/*.h` dual GPLv2/Apache | Contains Homog/Standard/Balanced ribbon (RocksDB-derived) but **not BuRR**. |
| `lorenzhs/fastfilter_cpp` (fork) → `lorenzhs/BuRR` | C++17 | Apache-2.0; vendored `rocksdb/*.h` dual GPLv2/Apache | The BuRR code lives in the standalone `lorenzhs/BuRR` repo, pulled in as a submodule of the fork. So your "fastfilter_cpp fork with BuRR" is right in substance. Its file format is native-endian with no checksum and does not record the hash function. |
| `RibbonFilter/ribbonGo` | Go | MIT | Standard ribbon only, no exported serialization. |
| `reflectt6/RibbonFilter`, `lorenzhs/retrieval-test` | C/C++ | **none** | All rights reserved: not consulted, not usable. |
| `bitwiseshiftleft/compressed_map` | Rust | MIT | Different variant ("frayed ribbon cascade"), research-grade. |

* I found no Python ribbon package or BuRR wrapper (PyPI index grep; GitHub repo and code
  search). Nearest neighbours: `pyfusefilter` 1.3.2 (Apache-2.0), `pyxorfilter` 1.1.2 (Apache-2.0), `binaryfuse` 0.1.2
  (MIT). A differently named wrapper could exist; the search was by name and keyword.
* pleat, ribbonGo and BuRR are derivatives of the RocksDB ribbon code; they share its
  multiplicative constant and say so in comments. So none of them is an independent reference. For pyribbon: do not
  reuse their constants, RocksDB's seed-mixing scheme or pleat's test vectors (generated from the reference kernel);
  choose our own and validate statistically. The agents that read these files are research-only; the implementation
  cites the papers.
* BuRR's source shows a hash-implementation hazard: xxHash's default `XXH_FORCE_MEMORY_ACCESS=1` on GCC let
  GCC delete stores at -O2 so every item got the same hash (xxHash issue #1126; I only saw BuRR's comment, I did not
  open the issue). If we vendor XXH3 we force the memcpy mode.

## 11. Hash functions

Requirement: a documented 64-bit hash with a permissive licence, vendorable as C11, identical output on every
platform (serialized filters are queried anywhere), key mapping defined on values, not memory bytes.

| Hash | Licence (file read) | Output byte-order independent | Frozen outputs / vectors | Verdict |
|---|---|---|---|---|
| **XXH3-64** (xxHash v0.8.4) | BSD-2-Clause (library) | yes, by design | README promises stable output since v0.8.0; spec doc; known-answer vectors in repo | **Chosen for byte keys** (vendored, `XXH_FORCE_MEMORY_ACCESS=0`, fixed seed) |
| SipHash-2-4 | CC0 / MIT / Apache-LLVM | yes | frozen by the paper; 64 official vectors | **Fallback**: keyed, 185 lines; ~5x slower on short keys (third-party numbers) |
| rapidhash V3 | MIT | yes | no spec or vectors; V3 outputs changed during development | Not chosen (unless copied and frozen) |
| polymur-hash 2.0 | zlib | yes | reference values; universality proof | Not chosen |
| wyhash 4.3 | Unlicense | yes | **not frozen** (default secret changed 2023) | Rejected |
| komihash 5.34 | MIT | claims yes | repeated big-endian bug fixes 2025-26; no cross-version promise | Rejected |
| CityHash / FarmHash / UMASH / mx3 | MIT / MIT / MIT / no licence file | n/a | C++, unstable API, needs CLMUL, or unlicensed | Rejected |

* SMHasher results are third-party and cover older versions: XXH3-64 fails 27 of 250 tests, mostly in *seeded* and
  bit-independence tests; SipHash and rapidhash pass. So do not use XXH3's own seed to create the
  independent hash functions needed for retries. Hash once with a fixed seed, then derive per-attempt values with our
  own remix. (A seed added *before* the mixer is also a trap: keys `k` and `k+1` under seeds `s+1` and `s` then share
  hashes, so retries are almost perfectly correlated.)
* For integer keys there are public-domain bijective mixers on 2^64: SplitMix64's finalizer (Vigna, CC0-style dedication) and
  MurmurHash3's `fmix64` (placed in the public domain). Both map 0 to 0 bare, so add a seed-derived constant first.
  The mapping must be defined on the numeric value (shifts and multiplies), never on memory bytes. BuRR hashes the raw
  bytes of integer keys, so its integer hashes depend on host endianness.
* In one agent's own test (2^20 samples, mixers only, not a ribbon test), first-order avalanche of
  `fmix64` and the SplitMix64 finalizer is at noise level (max |p-0.5| ≈ 0.002; ideal rms 0.0005). A bare
  multiply-by-odd-constant has no avalanche (max deviation 0.5): the "multiply by an odd constant" recipe in
  [R p9] is only sound after a full-avalanche pre-hash.
* A 64-bit hash gives expected colliding pairs ≈ n²/2^65: about 0.027 at n = 1e9. Identical hashes give identical
  equations, which are redundant and cause no failure (§4).

## 12. Python binding, packaging, baselines

Verified by a research agent on this machine (Linux x86_64, i7-7700, governor `powersave`, CPython 3.14.4, gcc 15.2,
extra interpreters via `uv`). Per-call numbers are a rough decision aid and not benchmark results (single
machine, 9 repeats, median, spread ≤ 1.3 ns; the empty `for` loop costs ~12 ns and is not subtracted).

Binding approaches:

| Approach | ns per `key in f` / method call | Notes |
|---|---:|---|
| Hand-written C extension, limited API (abi3) | 32 / 34 | same as full API (32 / 34.5): the limited API costs nothing measurable |
| Cython 3.3 | 30 (`__contains__`) / 41 (`def`) | `__contains__` slot matches hand-written C; `def` methods pay ~6 ns arg parsing |
| cffi API-mode | 175 raw, 267 through a Python class | cannot define type slots; releases the GIL on every call |
| Batch call (one call, many keys) | ~1.9 per key | per-call overhead disappears: API design matters more than binding choice |

* `Py_buffer`, `PyObject_GetBuffer` and `PyBuffer_Release` joined the stable ABI in 3.11 (`Misc/stable_abi.toml`;
  What's New 3.11). Building a limited-API extension against 3.10 fails with "unknown type name 'Py_buffer'".
  Python 3.10 reached end of life on 2026-10-01 (devguide).
* Free-threaded builds have no abi3 before 3.15. On 3.14t `Python.h` errors under `Py_LIMITED_API`; a GIL-build
  abi3 `.so` fails to import (`SystemError`); setuptools refuses `py_limited_api` there; pip/uv skip abi3 wheels.
  abi3t (PEP 803) is 3.15-only and needs source changes. Free-threaded users need separate `cp314t` wheels.
* GIL release (`Py_BEGIN_ALLOW_THREADS`) is in the stable ABI. Measured with a 16 MiB batch loop: GIL released,
  4 threads take 1.10x the 1-thread time; GIL held, 3.99x. Between the macros: no Python objects, refcounts,
  `PyErr_*`, or `PyMem_*`/`PyObject_*` allocators. A single-key call costs ~34 ns, so releasing the GIL per call
  would cost more than the work.
* Holding a buffer in an object works. For `bytearray` the resize is blocked (`BufferError`) while the filter
  exists, but in-place writes still succeed (`PyBUF_SIMPLE` does not refuse writable sources). `mmap` close and
  resize are blocked while exported. Non-contiguous memoryviews raise `BufferError`.
* For build backends (single C file + a C library that must also build with a plain Makefile), setuptools needs
  no extra build dependency, `sdist` builds with only a C compiler, and ~10 lines of conditional logic select
  limited vs. full API by interpreter. scikit-build-core works (sdist build fetches cmake and ninja from PyPI if
  missing). meson-python is rejected: `meson dist` needs a VCS checkout, the abi3 tag follows the build interpreter,
  and it fails on 3.10 and 3.14t.

cibuildwheel 4.3.5 (2026-10-27) builds cp310-cp315 and cp314t/cp315t by default; cp313t no longer
exists. For an abi3 project it builds the first abi3 wheel once and only *tests* it on later interpreters (read in
source, not run), so per platform: cp310 (non-limited) + cp311-abi3 (+ cp314t/cp315t if free-threaded is wanted).
Identifier selection was checked with `--print-build-identifiers`; no wheel was built end to end (no container
images were pulled) and nothing was built on macOS or Windows.

On MSVC (from Microsoft docs; nothing compiled): `/std:c11` exists since VS 2019 16.8; no C11 atomics
without `/experimental:c11atomics` (the core is read-only after build and needs none); `__builtin_*` and
`__int128` are not available; `_umul128` is x64-only (`__umulh` on ARM64); `_BitScanForward64` is x64/ARM64;
`__popcnt64` is x64-only and needs POPCNT. `long` is 32-bit on Win64, so use `uint64_t` everywhere. Portable
fallbacks must be selected by `#if` and tested on Linux by forcing the macro.

Baselines (sanity checks only: 1e5 keys, 1e6 probes):

| Package | State | Finding |
|---|---|---|
| `pyxorfilter` 1.1.2 | **do not use** | cffi over `xor_singleheader`; wheels only up to cp312; sdist build fails (`lib/xor_singleheader/include/xorfilter.h` missing); `populate` raises `TypeError` with xxhash 4.x; no `__contains__`, so `99 in f` never terminates; keys go through `str()`, so `51` and `"51"` collide. Classes `Xor8/Xor16/Fuse8/Fuse16` exist as you remembered. |
| **`pyfusefilter` 1.3.2** (2026-10-31, Apache-2.0) | maintained successor, same design | wheels cp39-cp315 incl. 3.14t. Measured on 3.14.4: Xor8 9.84 bits/key, FPR 0.0039; Xor16 19.69, 1.4e-5; **Fuse8 9.51, 0.0039**; Fuse16 19.01, 9e-6; 0 false negatives; ~660-715 ns/call including the Python loop; no batch query. |
| `binaryfuse` 0.1.2 | **do not use** | abi3 wheel segfaults on 3.14.4 at construction; works on 3.12/3.13. |
| **`rbloom` 1.5.4** (Rust, MIT) | Bloom baseline | abi3 wheels 3.10-3.14; `Bloom(expected_items, fpr, hash_func)`; `size_in_bits`; FPR 0.0093, 9.585 bits/key; ~80 ns/probe. Caveat: `hash()` of `int` is the identity and of `bytes`/`str` is salted per process, so the benchmark must pass an explicit `hash_func` or pre-hashed ints. No batch query. |
| `fastbloom-rs` 0.5.10 (Apache-2.0) | optional second Bloom | the only one with batch query (`contains_*_batch`, ~83 ns/probe); thinner wheel matrix, no sdist. |
| `pybloomfiltermmap3`, `pyprobables`, `bloom-filter2`, `pybloom-live` | not chosen | mmap-backed C but no Windows wheels; or pure Python (1.5-13 µs/probe, a straw man); or stale (2021-22). |

A side effect of the research run (not in the repo): the agent installed a uv-managed free-threaded CPython 3.14.7t
and the symlink `~/.local/bin/python3.14t`. Remove with `uv python uninstall 3.14t` if unwanted.
