/*
 * ribbon.c - standard ribbon filter, width w = 64 or 128, interleaved column layout (ICML).
 *
 * Sources (see docs/research.md): [R] Dillinger & Walzer, arXiv:2103.02515, sections 2-5.
 *  - one equation per key: coeff . Z[start .. start+w-1] = fp, with bit 0 of coeff forced to 1 [R p3];
 *  - on-the-fly banded Gaussian elimination in arrival order, no sorting [R sec. 3, Alg. 1];
 *  - back-substitution from the last row to the first [R p4];
 *  - interleaved column-major storage: for each block of 64 rows, r words, word j = column j [R sec. 5.2];
 *  - failure is handled by retrying with a new seed or a slightly larger table [R sec. 5.3].
 * Format and derivation details: docs/internals.md sections 3-5.
 */
#include <stdlib.h>
#include <string.h>

#include "rb_internal.h"

struct rb_filter {
  uint64_t num_keys;
  uint64_t num_rows; /* 0, or a multiple of 64 and >= 2 * width */
  uint64_t seed;
  uint64_t payload_xxh3;
  uint64_t salt; /* rb_attempt_salt(attempt), derived (never read from the buffer) */
  uint32_t fp_bits;
  uint32_t attempt;
  uint32_t width;     /* RB_WIDTH_64 or RB_WIDTH_128, as a number */
  const uint8_t *payload; /* (num_rows / 64) * fp_bits little-endian 64-bit words */
  uint8_t *owned;         /* non-NULL when the filter owns its payload */
};

static const char rb_magic[8] = {'P', 'Y', 'R', 'I', 'B', 'B', 'O', 'N'};

/* ------------------------------------------------------------------------------------ */
/* parameters, status strings                                                           */

rb_params rb_params_default(void) {
  rb_params p;
  p.fp_bits = RB_DEFAULT_FP_BITS;
  p.max_attempts = RB_DEFAULT_MAX_ATTEMPTS;
  p.overhead = -1.0;
  p.seed = 0;
  p.width = RB_WIDTH_64;
  return p;
}

const char *rb_strerror(rb_status status) {
  switch (status) {
    case RB_OK: return "ok";
    case RB_E_INVALID_ARG: return "invalid argument";
    case RB_E_NOMEM: return "out of memory";
    case RB_E_CONSTRUCT: return "construction failed: every attempt hit an unsolvable system";
    case RB_E_TOO_LARGE: return "size out of the supported range";
    case RB_E_TRUNCATED: return "buffer too short";
    case RB_E_MAGIC: return "bad magic number: not a pyribbon filter";
    case RB_E_VERSION: return "unsupported format version";
    case RB_E_FORMAT: return "inconsistent or unsupported header";
    case RB_E_CHECKSUM: return "checksum mismatch";
  }
  return "unknown status";
}

/* ------------------------------------------------------------------------------------ */
/* sizing                                                                               */

/* Overhead (extra rows / n, in parts per million) at n = 2^k, target 97% per-attempt success (expected attempts ~1.03).
 * Measured with the real derivation and insertion code: `make calibrate` (core/tools/calibrate.c, 357..6000 trials per
 * size at width 64, 476..6000 at width 128) converted by core/tools/overhead_table.py from the 3rd percentile of the fill
 * reached at first failure. Sizing is integer arithmetic only, so the same keys give the same serialized bytes on every
 * platform (no floating-point contraction can change a row count). Width 64 is measured for k = 7..24, width 128 for
 * k = 7..22; above that the overhead is extrapolated at the slope measured over the last octaves. */
#define RB_PPM UINT64_C(1000000)
#define RB_WORD_BITS 64u /* rows per payload word */
#define RB_OVERHEAD_FIRST_K 7u
#define RB_OVERHEAD_LAST_K_64 24u
#define RB_OVERHEAD_LAST_K_128 22u
#define RB_OVERHEAD_SLOPE_PPM_64 7000  /* 0.7 pp per doubling */
#define RB_OVERHEAD_SLOPE_PPM_128 4000 /* 0.4 pp per doubling, from the measured 0.32 */
static const int64_t rb_overhead_ppm_64[RB_OVERHEAD_LAST_K_64 - RB_OVERHEAD_FIRST_K + 1u] = {
    66000, 54000, 54000, 53000, 58000, 64000, 71000, 78000, 87000,
    95000, 101000, 109000, 115000, 125000, 134000, 139000, 148000, 155000};
static const int64_t rb_overhead_ppm_128[RB_OVERHEAD_LAST_K_128 - RB_OVERHEAD_FIRST_K + 1u] = {
    40000, 28000, 27000, 25000, 25000, 26000, 28000, 30000,
    33000, 36000, 40000, 44000, 48000, 52000, 55000, 57000};

typedef struct {
  const int64_t *ppm; /* overhead at n = 2^k, k = RB_OVERHEAD_FIRST_K .. last_k */
  unsigned last_k;
  uint64_t slope_ppm; /* above 2^last_k slots: extrapolated at this slope per doubling of n */
} rb_overhead_table;

static const rb_overhead_table rb_overhead_64 = {rb_overhead_ppm_64, RB_OVERHEAD_LAST_K_64, RB_OVERHEAD_SLOPE_PPM_64};
static const rb_overhead_table rb_overhead_128 = {rb_overhead_ppm_128, RB_OVERHEAD_LAST_K_128, RB_OVERHEAD_SLOPE_PPM_128};

static uint64_t rb_default_overhead_ppm(uint64_t n, rb_width_kind width) {
  const rb_overhead_table *t = width == RB_WIDTH_128 ? &rb_overhead_128 : &rb_overhead_64;
  if (n <= 128) return (uint64_t)t->ppm[0];
  unsigned k = 0;
  for (uint64_t x = n; x > 1; x >>= 1) k++;
  uint64_t base = UINT64_C(1) << k, rem = n - base; /* n = base + rem, 0 <= rem < base */
  if (k >= t->last_k) {
    uint64_t last = (uint64_t)t->ppm[t->last_k - RB_OVERHEAD_FIRST_K];
    return last + t->slope_ppm * (k - t->last_k) + t->slope_ppm * rem / base;
  }
  int64_t lo = t->ppm[k - RB_OVERHEAD_FIRST_K], hi = t->ppm[k + 1u - RB_OVERHEAD_FIRST_K];
  /* |hi - lo| < 2**14 and rem < 2**38, so the product fits in int64; division truncates toward zero */
  return (uint64_t)(lo + (hi - lo) * (int64_t)rem / (int64_t)base);
}

double rb_default_overhead_width(uint64_t n, rb_width_kind width) { return (double)rb_default_overhead_ppm(n, width) / 1e6; }
double rb_default_overhead(uint64_t n) { return rb_default_overhead_width(n, RB_WIDTH_64); }

static uint64_t rb_round_up64(uint64_t x) { return (x + 63u) & ~UINT64_C(63); }

/* Rows for n keys: ceil(n (1 + overhead)) rounded up to a multiple of 64, at least 2 * width. n <= 2**38 and
 * overhead_ppm <= 4e6, so n * (1e6 + overhead_ppm) < 2**61: no overflow. */
static rb_status rb_initial_rows(uint64_t n, uint64_t overhead_ppm, uint32_t width, uint64_t *rows) {
  uint64_t scaled = n * (RB_PPM + overhead_ppm);
  uint64_t m = scaled / RB_PPM + (scaled % RB_PPM != 0);
  if (m >= RB_MAX_ROWS / 2) return RB_E_TOO_LARGE;
  m = rb_round_up64(m);
  if (m < 2u * width) m = 2u * width;
  *rows = m;
  return RB_OK;
}

/* Grow by about (w+1)/w, at least one block of 64 rows: the paper's alternative to reseeding [R p9]. */
static rb_status rb_grow_rows(uint64_t *rows, uint32_t width) {
  uint64_t add = *rows / width;
  if (add < RB_WORD_BITS) add = RB_WORD_BITS;
  uint64_t m = rb_round_up64(*rows + add);
  if (m > RB_MAX_ROWS) return RB_E_TOO_LARGE;
  *rows = m;
  return RB_OK;
}

/* ------------------------------------------------------------------------------------ */
/* construction                                                                         */

/* One row of the banded system: 16 bytes, so an insertion touches one cache line instead of two. */
typedef struct {
  uint64_t coeff; /* coefficient word whose bit 0 is the pivot; 0 = empty slot */
  uint32_t res;   /* r-bit result */
  uint32_t pad;
} rb_slot;

#define RB_CHUNK 16u /* keys derived and prefetched together before being inserted or probed */

/* Insert one equation. Slot i holds a coefficient word whose bit 0 is its pivot (0 = empty)
 * and a result word. Both the incoming and the stored word have bit 0 set, so after the XOR
 * bit 0 is clear: the shift below is by 1..63 and never reaches the word width [R Alg. 1].
 * Returns 1 on success (including a redundant equation), 0 if the system became unsolvable. */
static int rb_band_insert(rb_slot *slots, uint64_t i, uint64_t c, uint32_t b) {
  for (;;) {
    uint64_t stored = slots[i].coeff;
    if (stored == 0) {
      slots[i].coeff = c;
      slots[i].res = b;
      return 1;
    }
    c ^= stored;
    b ^= slots[i].res;
    if (c == 0) return b == 0; /* duplicate / dependent but consistent equation, or a contradiction */
    unsigned j = rb_ctz64(c);  /* 1..63 */
    i += j;
    c >>= j;
  }
}

/* Width 128: the coefficient is two words, lo = rows start .. start+63 and hi = start+64 .. start+127. A stored slot
 * has bit 0 of lo set (its pivot), so lo == 0 marks an empty slot. 24 bytes per row. */
typedef struct {
  uint64_t lo;
  uint64_t hi;
  uint32_t res;
  uint32_t pad;
} rb_slot128;

/* rb_band_insert for width 128. After the XOR bit 0 of lo is clear, so when lo != 0 the shift is 1..63; when lo == 0
 * the pivot is in hi and moves down by 64 + ctz(hi), a shift of 0..63 of hi alone. */
static int rb_band_insert_wide(rb_slot128 *slots, uint64_t i, uint64_t lo, uint64_t hi, uint32_t b) {
  for (;;) {
    rb_slot128 *s = &slots[i];
    if (s->lo == 0) {
      s->lo = lo;
      s->hi = hi;
      s->res = b;
      return 1;
    }
    lo ^= s->lo;
    hi ^= s->hi;
    b ^= s->res;
    if (lo == 0 && hi == 0) return b == 0; /* duplicate / dependent but consistent equation, or a contradiction */
    if (lo != 0) {
      unsigned j = rb_ctz64(lo); /* 1..63 */
      i += j;
      lo = (lo >> j) | (hi << (64u - j));
      hi >>= j;
    } else {
      unsigned j = rb_ctz64(hi); /* 0..63 */
      i += 64u + j;
      lo = hi >> j;
      hi = 0;
    }
  }
}

/* Large tables are filled bucket by bucket. For a table whose slots do not fit in the caches, a key's slot is a random
 * memory access and the build is bound by memory latency. The system's solution does not depend on the order in which the
 * equations arrive (docs/internals.md section 4), so the keys are first grouped by start row (a counting sort on start >> shift,
 * one extra 8-byte word per key) and then inserted bucket after bucket: the slots of one bucket stay in cache and the
 * elimination walks memory in increasing order. Smaller tables keep the plain arrival-order loop. */
#ifndef RB_BUCKET_MIN_ROWS
#define RB_BUCKET_MIN_ROWS (UINT64_C(1) << 18)
#endif
#ifndef RB_BUCKET_MIN_SHIFT
#define RB_BUCKET_MIN_SHIFT 12u /* at least 4096 rows (64 KiB of slots) per bucket */
#endif
#ifndef RB_BUCKET_MAX
#define RB_BUCKET_MAX 1024u /* at most this many buckets: the scatter then keeps one open cache line per bucket in L1/L2 */
#endif

/* Insert every equation of `keys` in order; the chunked prefetch overlaps the cache misses of random slots. */
static int rb_insert_keys(rb_slot *slots, const uint64_t *keys, size_t n, uint64_t salt, uint64_t num_starts, uint32_t r) {
  for (size_t i = 0; i < n; i += RB_CHUNK) {
    /* derive a chunk and prefetch its slots first: the random accesses then overlap instead of queueing. */
    size_t cn = n - i < RB_CHUNK ? n - i : RB_CHUNK;
    rb_eq eqs[RB_CHUNK];
    for (size_t j = 0; j < cn; j++) {
      eqs[j] = rb_derive(keys[i + j], salt, num_starts, r);
      rb_prefetch(&slots[eqs[j].start]);
    }
    for (size_t j = 0; j < cn; j++)
      if (!rb_band_insert(slots, eqs[j].start, eqs[j].coeff, eqs[j].fp)) return 0;
  }
  return 1;
}

static int rb_insert_keys_wide(rb_slot128 *slots, const uint64_t *keys, size_t n, uint64_t salt, uint64_t num_starts,
                               uint32_t r) {
  for (size_t i = 0; i < n; i += RB_CHUNK) {
    size_t cn = n - i < RB_CHUNK ? n - i : RB_CHUNK;
    rb_eq eqs[RB_CHUNK];
    uint64_t hi[RB_CHUNK];
    for (size_t j = 0; j < cn; j++) {
      eqs[j] = rb_derive(keys[i + j], salt, num_starts, r);
      hi[j] = rb_derive_coeff_hi(keys[i + j], salt);
      rb_prefetch(&slots[eqs[j].start]);
    }
    for (size_t j = 0; j < cn; j++)
      if (!rb_band_insert_wide(slots, eqs[j].start, eqs[j].coeff, hi[j], eqs[j].fp)) return 0;
  }
  return 1;
}

/* Insert `keys` in order into `slots`, an rb_slot array, or an rb_slot128 array when `wide`. */
static int rb_insert_run(void *slots, const uint64_t *keys, size_t n, uint64_t salt, uint64_t num_starts, uint32_t r,
                         int wide) {
  return wide ? rb_insert_keys_wide((rb_slot128 *)slots, keys, n, salt, num_starts, r)
              : rb_insert_keys((rb_slot *)slots, keys, n, salt, num_starts, r);
}

/* Group `hashes` by bucket (start >> shift) into `sorted` (room for n words), then insert bucket by bucket. */
static int rb_insert_bucketed(void *slots, const uint64_t *hashes, size_t n, uint64_t salt, uint64_t num_starts,
                              uint32_t r, uint64_t *sorted, int wide) {
  size_t counts[RB_BUCKET_MAX + 1u];
  unsigned shift = RB_BUCKET_MIN_SHIFT;
  while (((num_starts - 1u) >> shift) >= RB_BUCKET_MAX) shift++;
  size_t nb = (size_t)((num_starts - 1u) >> shift) + 1u;
  memset(counts, 0, (nb + 1u) * sizeof *counts);
  for (size_t i = 0; i < n; i++) counts[(rb_derive_start(hashes[i], salt, num_starts) >> shift) + 1u]++;
  for (size_t b = 0; b < nb; b++) counts[b + 1u] += counts[b];
  for (size_t i = 0; i < n; i++) sorted[counts[rb_derive_start(hashes[i], salt, num_starts) >> shift]++] = hashes[i];
  /* counts[b] is now the end of bucket b, i.e. the start of bucket b + 1 */
  size_t lo = 0;
  for (size_t b = 0; b < nb; b++) {
    if (!rb_insert_run(slots, sorted + lo, counts[b] - lo, salt, num_starts, r, wide)) return 0;
    lo = counts[b];
  }
  return 1;
}

/* Back-substitution into the interleaved layout [R p4, sec. 5.2]. st[j] holds, at bit k, the
 * solution bit of column j at row i + k; when i is a multiple of 64 it is exactly the word
 * for block i / 64, column j. Rows are processed from the last to the first. */
static void rb_back_substitute(const rb_slot *slots, uint64_t rows, uint32_t r, uint8_t *payload) {
  uint64_t st[RB_MAX_FP_BITS] = {0};
  for (uint64_t i = rows; i-- > 0;) {
    uint64_t c = slots[i].coeff;
    uint32_t b = slots[i].res;
    for (uint32_t j = 0; j < r; j++) {
      st[j] <<= 1; /* bit 0 = row i, still unknown (0): the dot product below excludes it */
      uint64_t v = rb_parity64(st[j] & c) ^ (uint64_t)((b >> j) & 1u);
      st[j] |= v;
    }
    if ((i & 63u) == 0) {
      uint8_t *block = payload + (i >> 6) * r * 8u;
      for (uint32_t j = 0; j < r; j++) rb_store_le64(block + 8u * j, st[j]);
    }
  }
}

/* rb_back_substitute for width 128: the running window per column is two words, rows i..i+63 and i+64..i+127. */
static void rb_back_substitute_wide(const rb_slot128 *slots, uint64_t rows, uint32_t r, uint8_t *payload) {
  uint64_t lo[RB_MAX_FP_BITS] = {0}, hi[RB_MAX_FP_BITS] = {0};
  for (uint64_t i = rows; i-- > 0;) {
    uint64_t cl = slots[i].lo, ch = slots[i].hi;
    uint32_t b = slots[i].res;
    for (uint32_t j = 0; j < r; j++) {
      hi[j] = (hi[j] << 1) | (lo[j] >> 63);
      lo[j] <<= 1; /* bit 0 = row i, still unknown (0): the dot product below excludes it */
      lo[j] |= rb_parity64(lo[j] & cl) ^ rb_parity64(hi[j] & ch) ^ (uint64_t)((b >> j) & 1u);
    }
    if ((i & 63u) == 0) {
      uint8_t *block = payload + (i >> 6) * r * 8u;
      for (uint32_t j = 0; j < r; j++) rb_store_le64(block + 8u * j, lo[j]);
    }
  }
}

static size_t rb_payload_bytes(uint64_t rows, uint32_t r) { return (size_t)((rows >> 6) * r * 8u); }

static rb_filter *rb_new_filter(void) {
  rb_filter *f = (rb_filter *)calloc(1, sizeof *f);
  return f;
}

rb_status rb_build(const uint64_t *hashes, size_t n, const rb_params *params, rb_filter **out, rb_build_info *info) {
  return rb_build_ex(hashes, n, params, -1, out, info);
}

rb_status rb_build_ex(const uint64_t *hashes, size_t n, const rb_params *params, int bucket, rb_filter **out,
                      rb_build_info *info) {
  if (!out) return RB_E_INVALID_ARG;
  *out = NULL;
  rb_params p = params ? *params : rb_params_default();
  if (p.fp_bits < RB_MIN_FP_BITS || p.fp_bits > RB_MAX_FP_BITS) return RB_E_INVALID_ARG;
  if (p.max_attempts == 0) p.max_attempts = RB_DEFAULT_MAX_ATTEMPTS;
  if (p.max_attempts > RB_MAX_ATTEMPTS) return RB_E_INVALID_ARG;
  if (p.overhead != p.overhead || p.overhead > 4.0) return RB_E_INVALID_ARG; /* NaN or absurd */
  if (p.width != RB_WIDTH_64 && p.width != RB_WIDTH_128) return RB_E_INVALID_ARG;
  const int wide = p.width == RB_WIDTH_128;
  const size_t slot_size = wide ? sizeof(rb_slot128) : sizeof(rb_slot);
  if (n > 0 && !hashes) return RB_E_INVALID_ARG;
#if SIZE_MAX > RB_MAX_KEYS /* on a 32-bit size_t the limit cannot be exceeded, and the comparison would not compile warning-free */
  if ((uint64_t)n > RB_MAX_KEYS) return RB_E_TOO_LARGE;
#endif

  rb_filter *f = rb_new_filter();
  if (!f) return RB_E_NOMEM;
  f->num_keys = n;
  f->seed = p.seed;
  f->fp_bits = p.fp_bits;
  f->width = p.width;

  if (n == 0) { /* valid empty filter: header only, every query is false */
    f->payload_xxh3 = rb_xxh3_64(NULL, 0);
    f->payload = (const uint8_t *)"";
    if (info) { info->attempts = 0; info->num_rows = 0; }
    *out = f;
    return RB_OK;
  }

  uint64_t overhead_ppm = p.overhead < 0.0 ? rb_default_overhead_ppm(n, p.width) : (uint64_t)(p.overhead * 1e6 + 0.5);
  uint64_t rows;
  rb_status st = rb_initial_rows(n, overhead_ppm, p.width, &rows);
  void *slots = NULL; /* rb_slot or rb_slot128 */
  uint64_t *sorted = NULL; /* keys grouped by start row, for large tables only */
  uint64_t alloc_rows = 0;
  for (uint32_t attempt = 0; st == RB_OK && attempt < p.max_attempts; attempt++) {
    if (attempt >= 2) { /* reseeding alone first; from the third attempt also grow the table */
      st = rb_grow_rows(&rows, p.width);
      if (st != RB_OK) break;
    }
    if (rows > alloc_rows) {
      if (rows > SIZE_MAX / slot_size) { st = RB_E_TOO_LARGE; break; }
      free(slots);
      slots = calloc((size_t)rows, slot_size);
      alloc_rows = rows;
      if (!slots) { st = RB_E_NOMEM; break; }
    } else {
      memset(slots, 0, (size_t)rows * slot_size);
    }
    uint64_t num_starts = rows - p.width + 1u;
    uint64_t salt = rb_attempt_salt(attempt);
    int bucketed = bucket > 0 || (bucket < 0 && rows >= RB_BUCKET_MIN_ROWS);
    if (bucketed && !sorted) {
      if (n > SIZE_MAX / sizeof *sorted) { st = RB_E_TOO_LARGE; break; }
      sorted = (uint64_t *)malloc(n * sizeof *sorted);
      if (!sorted) { st = RB_E_NOMEM; break; }
    }
    int solvable = bucketed ? rb_insert_bucketed(slots, hashes, n, salt, num_starts, p.fp_bits, sorted, wide)
                            : rb_insert_run(slots, hashes, n, salt, num_starts, p.fp_bits, wide);
    if (!solvable) continue; /* unsolvable: next attempt (st stays RB_OK; exhaustion is reported after the loop) */

    size_t payload_len = rb_payload_bytes(rows, p.fp_bits);
    uint8_t *payload = (uint8_t *)malloc(payload_len);
    if (!payload) { st = RB_E_NOMEM; break; }
    if (wide) rb_back_substitute_wide((const rb_slot128 *)slots, rows, p.fp_bits, payload);
    else rb_back_substitute((const rb_slot *)slots, rows, p.fp_bits, payload);
    f->num_rows = rows;
    f->attempt = attempt;
    f->salt = salt;
    f->owned = payload;
    f->payload = payload;
    f->payload_xxh3 = rb_xxh3_64(payload, payload_len);
    if (info) { info->attempts = attempt + 1u; info->num_rows = rows; }
    free(slots);
    free(sorted);
    *out = f;
    return RB_OK;
  }
  free(slots);
  free(sorted);
  free(f);
  return st == RB_OK ? RB_E_CONSTRUCT : st;
}

/* ------------------------------------------------------------------------------------ */
/* query                                                                                */

/* Width 128: the coefficient shifted by off = start & 63 spans up to three words: lo << off, (lo >> (64 - off)) |
 * (hi << off), hi >> (64 - off). start <= num_rows - 128, so the third word exists whenever off > 0. */
static inline int rb_contains_wide(const rb_filter *f, uint64_t hash) {
  uint32_t r = f->fp_bits;
  rb_eq eq = rb_derive(hash, f->salt, f->num_rows - RB_WIDTH_128 + 1u, r);
  uint64_t hi = rb_derive_coeff_hi(hash, f->salt), lo = eq.coeff;
  unsigned off = (unsigned)(eq.start & 63u);
  const uint8_t *blk = f->payload + (eq.start >> 6) * r * 8u;
  uint64_t a0 = lo << off, a1 = hi, a2 = 0;
  if (off != 0) { /* a shift by 64 is undefined behaviour */
    a1 = (lo >> (64u - off)) | (hi << off);
    a2 = hi >> (64u - off);
  }
  for (uint32_t j = 0; j < r; j++) {
    uint64_t bit = rb_parity64(rb_load_le64(blk + 8u * j) & a0) ^ rb_parity64(rb_load_le64(blk + 8u * (r + j)) & a1);
    if (off != 0) bit ^= rb_parity64(rb_load_le64(blk + 8u * (2u * r + j)) & a2);
    if (bit != (uint64_t)((eq.fp >> j) & 1u)) return 0;
  }
  return 1;
}

static inline int rb_contains_narrow(const rb_filter *f, uint64_t hash) {
  uint32_t r = f->fp_bits;
  rb_eq eq = rb_derive(hash, f->salt, f->num_rows - RB_WIDTH_64 + 1u, r);
  unsigned off = (unsigned)(eq.start & 63u);
  /* start <= num_rows - 64, so when off > 0 the next block exists: no read past the payload. */
  const uint8_t *blk = f->payload + (eq.start >> 6) * r * 8u;
  for (uint32_t j = 0; j < r; j++) {
    uint64_t bit = rb_parity64(rb_load_le64(blk + 8u * j) & (eq.coeff << off));
    if (off != 0) /* a shift by 64 is undefined behaviour, so the spill-over word is skipped at off == 0 */
      bit ^= rb_parity64(rb_load_le64(blk + 8u * (r + j)) & (eq.coeff >> (64u - off)));
    if (bit != (uint64_t)((eq.fp >> j) & 1u)) return 0; /* early exit: ~2 columns on average for a miss */
  }
  return 1;
}

int rb_contains(const rb_filter *f, uint64_t hash) {
  if (f->num_rows == 0) return 0;
  return f->width == RB_WIDTH_128 ? rb_contains_wide(f, hash) : rb_contains_narrow(f, hash);
}

void rb_contains_many(const rb_filter *f, const uint64_t *hashes, size_t n, uint8_t *out) {
  if (f->num_rows == 0 || n < 2 * RB_CHUNK) { /* tiny batches: nothing to overlap */
    for (size_t i = 0; i < n; i++) out[i] = (uint8_t)rb_contains(f, hashes[i]);
    return;
  }
  const int wide = f->width == RB_WIDTH_128;
  /* Prefetch the first words of the two blocks a probe reads for the NEXT chunk while answering the current one. */
  uint32_t r = f->fp_bits;
  uint64_t num_starts = f->num_rows - f->width + 1u;
  size_t i = 0;
  for (; i + 2 * RB_CHUNK <= n; i += RB_CHUNK) {
    for (size_t j = 0; j < RB_CHUNK; j++) {
      rb_eq eq = rb_derive(hashes[i + RB_CHUNK + j], f->salt, num_starts, r);
      const uint8_t *blk = f->payload + (eq.start >> 6) * r * 8u;
      rb_prefetch(blk);
      rb_prefetch(blk + 8u * r);
      if (wide) rb_prefetch(blk + 16u * r);
    }
    /* no shared helper here: it measured slower in this loop */
    for (size_t j = 0; j < RB_CHUNK; j++)
      out[i + j] = (uint8_t)(wide ? rb_contains_wide(f, hashes[i + j]) : rb_contains_narrow(f, hashes[i + j]));
  }
  for (; i < n; i++) out[i] = (uint8_t)(wide ? rb_contains_wide(f, hashes[i]) : rb_contains_narrow(f, hashes[i]));
}

/* ------------------------------------------------------------------------------------ */
/* serialization and loading (docs/internals.md section 5)                                      */

size_t rb_serialized_size(const rb_filter *f) { return RB_HEADER_SIZE + rb_payload_bytes(f->num_rows, f->fp_bits); }

rb_status rb_serialize(const rb_filter *f, void *dst, size_t capacity) {
  size_t payload_len = rb_payload_bytes(f->num_rows, f->fp_bits);
  if (!dst || capacity < RB_HEADER_SIZE + payload_len) return RB_E_INVALID_ARG;
  uint8_t *h = (uint8_t *)dst;
  memset(h, 0, RB_HEADER_SIZE);
  memcpy(h, rb_magic, 8);
  rb_store_le16(h + 8, RB_FORMAT_VERSION);
  rb_store_le16(h + 10, RB_HEADER_SIZE);
  h[12] = f->width == RB_WIDTH_128 ? 7 : 6; /* width_log2 */
  h[13] = (uint8_t)f->fp_bits;
  h[14] = 1; /* hash id */
  h[15] = 0; /* flags */
  rb_store_le64(h + 16, f->num_keys);
  rb_store_le64(h + 24, f->num_rows);
  rb_store_le64(h + 32, f->seed);
  rb_store_le32(h + 40, f->attempt);
  rb_store_le64(h + 48, f->payload_xxh3);
  rb_store_le64(h + 56, rb_xxh3_64(h, 56));
  if (payload_len) memcpy(h + RB_HEADER_SIZE, f->payload, payload_len);
  return RB_OK;
}

rb_status rb_from_buffer(const void *buf, size_t len, int verify_payload, rb_filter **out) {
  if (!out) return RB_E_INVALID_ARG;
  *out = NULL;
  if (len < RB_HEADER_SIZE) return RB_E_TRUNCATED;
  if (!buf) return RB_E_INVALID_ARG;
  /* Snapshot the header: every header byte is read exactly once, from this private copy, so a concurrent writer to the
   * buffer cannot make validation and use see different values whatever the compiler does. */
  uint8_t h[RB_HEADER_SIZE];
  memcpy(h, buf, RB_HEADER_SIZE);
  if (memcmp(h, rb_magic, 8) != 0) return RB_E_MAGIC;
  if (rb_load_le16(h + 8) != RB_FORMAT_VERSION) return RB_E_VERSION;
  if (rb_load_le16(h + 10) != RB_HEADER_SIZE) return RB_E_FORMAT;
  if (rb_load_le64(h + 56) != rb_xxh3_64(h, 56)) return RB_E_CHECKSUM;
  if ((h[12] != 6 && h[12] != 7) || h[14] != 1 || h[15] != 0 || rb_load_le32(h + 44) != 0) return RB_E_FORMAT;
  uint32_t width = h[12] == 7 ? RB_WIDTH_128 : RB_WIDTH_64;
  uint32_t r = h[13];
  if (r < RB_MIN_FP_BITS || r > RB_MAX_FP_BITS) return RB_E_FORMAT;
  uint64_t num_keys = rb_load_le64(h + 16);
  uint64_t rows = rb_load_le64(h + 24);
  if (rows != 0 && ((rows & 63u) != 0 || rows < 2u * width || rows > RB_MAX_ROWS)) return RB_E_FORMAT;
  /* An empty filter has no keys and a non-empty one has between 1 and `rows` (rows >= keys for every filter rb_build
   * makes, duplicates included); this also keeps len() of a loaded filter meaningful. */
  if ((rows == 0) != (num_keys == 0) || num_keys > rows) return RB_E_FORMAT;
  uint64_t payload_len = (rows >> 6) * r * 8u; /* rows <= 2^40, r <= 32: at most 2^42, no overflow */
  uint64_t have = (uint64_t)len - RB_HEADER_SIZE;
  if (have < payload_len) return RB_E_TRUNCATED;
  if (have > payload_len) return RB_E_FORMAT; /* trailing bytes: slice the buffer to embed a filter */
  const uint8_t *payload = (const uint8_t *)buf + RB_HEADER_SIZE;
  uint64_t checksum = rb_load_le64(h + 48);
  if (verify_payload && checksum != rb_xxh3_64(payload, (size_t)payload_len)) return RB_E_CHECKSUM;

  rb_filter *f = rb_new_filter();
  if (!f) return RB_E_NOMEM;
  /* Every header field is copied here and never re-read from the buffer, so later changes to
   * the buffer can alter query answers but not the bounds of any memory access. */
  f->num_keys = num_keys;
  f->num_rows = rows;
  f->seed = rb_load_le64(h + 32);
  f->payload_xxh3 = checksum;
  f->fp_bits = r;
  f->width = width;
  f->attempt = rb_load_le32(h + 40);
  f->payload = payload;
  f->salt = rb_attempt_salt(f->attempt);
  *out = f;
  return RB_OK;
}

void rb_free(rb_filter *f) {
  if (!f) return;
  free(f->owned);
  free(f);
}

uint64_t rb_num_keys(const rb_filter *f) { return f->num_keys; }
uint64_t rb_num_rows(const rb_filter *f) { return f->num_rows; }
uint32_t rb_fp_bits(const rb_filter *f) { return f->fp_bits; }
rb_width_kind rb_width(const rb_filter *f) { return (rb_width_kind)f->width; }
uint64_t rb_seed(const rb_filter *f) { return f->seed; }
