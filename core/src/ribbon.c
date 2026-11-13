/*
 * ribbon.c - standard ribbon filter, width w = 64, interleaved column layout (ICML).
 *
 * Sources (see RESEARCH.md): [R] Dillinger & Walzer, arXiv:2103.02515, sections 2-5.
 *  - one equation per key: coeff . Z[start .. start+63] = fp, with bit 0 of coeff forced to 1 [R p3];
 *  - on-the-fly banded Gaussian elimination in arrival order, no sorting [R sec. 3, Alg. 1];
 *  - back-substitution from the last row to the first [R p4];
 *  - interleaved column-major storage: for each block of 64 rows, r words, word j = column j [R sec. 5.2];
 *  - failure is handled by retrying with a new seed or a slightly larger table [R sec. 5.3].
 * Format and derivation details: DESIGN.md sections 3-5.
 */
#include <stdlib.h>
#include <string.h>

#include "rb_internal.h"

struct rb_filter {
  uint64_t num_keys;
  uint64_t num_rows; /* 0, or a multiple of 64 and >= 128 */
  uint64_t seed;
  uint64_t payload_xxh3;
  uint64_t salt; /* rb_attempt_salt(attempt), derived (never read from the buffer) */
  uint32_t fp_bits;
  uint32_t attempt;
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

/* Overhead (extra rows / n, in parts per million) at n = 2^k for k = 7..24, target 97% per-attempt success (expected
 * attempts ~1.03). Measured with the real derivation and insertion code: `make calibrate` (core/tools/calibrate.c,
 * 357..6000 trials per size) converted by core/tools/overhead_table.py from the 3rd percentile of the fill reached at
 * first failure. Sizing is integer arithmetic only, so the same keys give the same serialized bytes on every platform
 * (no floating-point contraction can change a row count). */
#define RB_PPM UINT64_C(1000000)
#define RB_OVERHEAD_FIRST_K 7u
#define RB_OVERHEAD_LAST_K 24u
static const int64_t rb_overhead_ppm_table[18] = {66000, 54000, 54000, 53000, 58000, 64000, 71000, 78000, 87000, 95000, 101000, 109000, 115000, 125000, 134000, 139000, 148000, 155000};
/* Above 2^24 slots the overhead is extrapolated at the measured slope of the last octaves (0.7 pp per doubling). */
#define RB_OVERHEAD_SLOPE_PPM 7000

static uint64_t rb_default_overhead_ppm(uint64_t n) {
  if (n <= 128) return (uint64_t)rb_overhead_ppm_table[0];
  unsigned k = 0;
  for (uint64_t t = n; t > 1; t >>= 1) k++;
  uint64_t base = UINT64_C(1) << k, rem = n - base; /* n = base + rem, 0 <= rem < base */
  if (k >= RB_OVERHEAD_LAST_K) {
    uint64_t last = (uint64_t)rb_overhead_ppm_table[RB_OVERHEAD_LAST_K - RB_OVERHEAD_FIRST_K];
    return last + RB_OVERHEAD_SLOPE_PPM * (k - RB_OVERHEAD_LAST_K) + RB_OVERHEAD_SLOPE_PPM * rem / base;
  }
  int64_t lo = rb_overhead_ppm_table[k - RB_OVERHEAD_FIRST_K], hi = rb_overhead_ppm_table[k + 1u - RB_OVERHEAD_FIRST_K];
  /* |hi - lo| < 2**14 and rem < 2**38, so the product fits in int64; division truncates toward zero */
  return (uint64_t)(lo + (hi - lo) * (int64_t)rem / (int64_t)base);
}

double rb_default_overhead(uint64_t n) { return (double)rb_default_overhead_ppm(n) / 1e6; }

static uint64_t rb_round_up64(uint64_t x) { return (x + 63u) & ~UINT64_C(63); }

/* Rows for n keys: ceil(n (1 + overhead)) rounded up to a multiple of 64, at least 128. n <= 2**38 and
 * overhead_ppm <= 4e6, so n * (1e6 + overhead_ppm) < 2**61: no overflow. */
static rb_status rb_initial_rows(uint64_t n, uint64_t overhead_ppm, uint64_t *rows) {
  uint64_t scaled = n * (RB_PPM + overhead_ppm);
  uint64_t m = scaled / RB_PPM + (scaled % RB_PPM != 0);
  if (m >= RB_MAX_ROWS / 2) return RB_E_TOO_LARGE;
  m = rb_round_up64(m);
  if (m < 2u * RB_WIDTH) m = 2u * RB_WIDTH;
  *rows = m;
  return RB_OK;
}

/* Grow by about (w+1)/w, at least one block: the paper's alternative to reseeding [R p9]. */
static rb_status rb_grow_rows(uint64_t *rows) {
  uint64_t add = *rows / RB_WIDTH;
  if (add < RB_WIDTH) add = RB_WIDTH;
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

static size_t rb_payload_bytes(uint64_t rows, uint32_t r) { return (size_t)((rows >> 6) * r * 8u); }

static rb_filter *rb_new_filter(void) {
  rb_filter *f = (rb_filter *)calloc(1, sizeof *f);
  return f;
}

rb_status rb_build(const uint64_t *hashes, size_t n, const rb_params *params, rb_filter **out, rb_build_info *info) {
  if (!out) return RB_E_INVALID_ARG;
  *out = NULL;
  rb_params p = params ? *params : rb_params_default();
  if (p.fp_bits < RB_MIN_FP_BITS || p.fp_bits > RB_MAX_FP_BITS) return RB_E_INVALID_ARG;
  if (p.max_attempts == 0) p.max_attempts = RB_DEFAULT_MAX_ATTEMPTS;
  if (p.max_attempts > RB_MAX_ATTEMPTS) return RB_E_INVALID_ARG;
  if (p.overhead != p.overhead || p.overhead > 4.0) return RB_E_INVALID_ARG; /* NaN or absurd */
  if (n > 0 && !hashes) return RB_E_INVALID_ARG;
#if SIZE_MAX > RB_MAX_KEYS /* on a 32-bit size_t the limit cannot be exceeded, and the comparison would not compile warning-free */
  if ((uint64_t)n > RB_MAX_KEYS) return RB_E_TOO_LARGE;
#endif

  rb_filter *f = rb_new_filter();
  if (!f) return RB_E_NOMEM;
  f->num_keys = n;
  f->seed = p.seed;
  f->fp_bits = p.fp_bits;

  if (n == 0) { /* valid empty filter: header only, every query is false */
    f->payload_xxh3 = rb_xxh3_64(NULL, 0);
    f->payload = (const uint8_t *)"";
    if (info) { info->attempts = 0; info->num_rows = 0; }
    *out = f;
    return RB_OK;
  }

  uint64_t overhead_ppm = p.overhead < 0.0 ? rb_default_overhead_ppm(n) : (uint64_t)(p.overhead * 1e6 + 0.5);
  uint64_t rows;
  rb_status st = rb_initial_rows(n, overhead_ppm, &rows);
  rb_slot *slots = NULL;
  uint64_t alloc_rows = 0;
  for (uint32_t attempt = 0; st == RB_OK && attempt < p.max_attempts; attempt++) {
    if (attempt >= 2) { /* reseeding alone first; from the third attempt also grow the table */
      st = rb_grow_rows(&rows);
      if (st != RB_OK) break;
    }
    if (rows > alloc_rows) {
      if (rows > SIZE_MAX / sizeof(rb_slot)) { st = RB_E_TOO_LARGE; break; }
      free(slots);
      slots = (rb_slot *)calloc((size_t)rows, sizeof *slots);
      alloc_rows = rows;
      if (!slots) { st = RB_E_NOMEM; break; }
    } else {
      memset(slots, 0, (size_t)rows * sizeof *slots);
    }
    uint64_t num_starts = rows - RB_WIDTH + 1u;
    uint64_t salt = rb_attempt_salt(attempt);
    int solvable = 1;
    for (size_t i = 0; i < n && solvable; i += RB_CHUNK) {
      /* derive a chunk and prefetch its slots first: the random accesses then overlap instead of queueing.
       * Equations are still inserted in arrival order, so the result is identical to one-at-a-time insertion. */
      size_t cn = n - i < RB_CHUNK ? n - i : RB_CHUNK;
      rb_eq eqs[RB_CHUNK];
      for (size_t j = 0; j < cn; j++) {
        eqs[j] = rb_derive(hashes[i + j], salt, num_starts, p.fp_bits);
        rb_prefetch(&slots[eqs[j].start]);
      }
      for (size_t j = 0; j < cn; j++)
        if (!rb_band_insert(slots, eqs[j].start, eqs[j].coeff, eqs[j].fp)) { solvable = 0; break; }
    }
    if (!solvable) continue; /* unsolvable: next attempt (st stays RB_OK; exhaustion is reported after the loop) */

    size_t payload_len = rb_payload_bytes(rows, p.fp_bits);
    uint8_t *payload = (uint8_t *)malloc(payload_len);
    if (!payload) { st = RB_E_NOMEM; break; }
    rb_back_substitute(slots, rows, p.fp_bits, payload);
    f->num_rows = rows;
    f->attempt = attempt;
    f->salt = salt;
    f->owned = payload;
    f->payload = payload;
    f->payload_xxh3 = rb_xxh3_64(payload, payload_len);
    if (info) { info->attempts = attempt + 1u; info->num_rows = rows; }
    free(slots);
    *out = f;
    return RB_OK;
  }
  free(slots);
  free(f);
  return st == RB_OK ? RB_E_CONSTRUCT : st;
}

/* ------------------------------------------------------------------------------------ */
/* query                                                                                */

int rb_contains(const rb_filter *f, uint64_t hash) {
  if (f->num_rows == 0) return 0;
  uint32_t r = f->fp_bits;
  rb_eq eq = rb_derive(hash, f->salt, f->num_rows - RB_WIDTH + 1u, r);
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

void rb_contains_many(const rb_filter *f, const uint64_t *hashes, size_t n, uint8_t *out) {
  if (f->num_rows == 0 || n < 2 * RB_CHUNK) { /* tiny batches: nothing to overlap */
    for (size_t i = 0; i < n; i++) out[i] = (uint8_t)rb_contains(f, hashes[i]);
    return;
  }
  /* Prefetch the first words of the two blocks a probe reads for the NEXT chunk while answering the current one. */
  uint32_t r = f->fp_bits;
  uint64_t num_starts = f->num_rows - RB_WIDTH + 1u;
  size_t i = 0;
  for (; i + 2 * RB_CHUNK <= n; i += RB_CHUNK) {
    for (size_t j = 0; j < RB_CHUNK; j++) {
      rb_eq eq = rb_derive(hashes[i + RB_CHUNK + j], f->salt, num_starts, r);
      const uint8_t *blk = f->payload + (eq.start >> 6) * r * 8u;
      rb_prefetch(blk);
      rb_prefetch(blk + 8u * r);
    }
    for (size_t j = 0; j < RB_CHUNK; j++) out[i + j] = (uint8_t)rb_contains(f, hashes[i + j]);
  }
  for (; i < n; i++) out[i] = (uint8_t)rb_contains(f, hashes[i]);
}

/* ------------------------------------------------------------------------------------ */
/* serialization and loading (DESIGN.md section 5)                                      */

size_t rb_serialized_size(const rb_filter *f) { return RB_HEADER_SIZE + rb_payload_bytes(f->num_rows, f->fp_bits); }

rb_status rb_serialize(const rb_filter *f, void *dst, size_t capacity) {
  size_t payload_len = rb_payload_bytes(f->num_rows, f->fp_bits);
  if (!dst || capacity < RB_HEADER_SIZE + payload_len) return RB_E_INVALID_ARG;
  uint8_t *h = (uint8_t *)dst;
  memset(h, 0, RB_HEADER_SIZE);
  memcpy(h, rb_magic, 8);
  rb_store_le16(h + 8, RB_FORMAT_VERSION);
  rb_store_le16(h + 10, RB_HEADER_SIZE);
  h[12] = 6; /* width_log2 */
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
  if (h[12] != 6 || h[14] != 1 || h[15] != 0 || rb_load_le32(h + 44) != 0) return RB_E_FORMAT;
  uint32_t r = h[13];
  if (r < RB_MIN_FP_BITS || r > RB_MAX_FP_BITS) return RB_E_FORMAT;
  uint64_t num_keys = rb_load_le64(h + 16);
  uint64_t rows = rb_load_le64(h + 24);
  if (rows != 0 && ((rows & 63u) != 0 || rows < 2u * RB_WIDTH || rows > RB_MAX_ROWS)) return RB_E_FORMAT;
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
uint64_t rb_seed(const rb_filter *f) { return f->seed; }
