/* Unit tests for the C core. No dependencies; exit status is non-zero on any failure. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rb_internal.h"
#include "ribbon.h"
#include "vectors.h"

static int g_checks, g_failed;
#define CHECK(cond)                                                                      \
  do {                                                                                   \
    g_checks++;                                                                          \
    if (!(cond)) {                                                                       \
      g_failed++;                                                                        \
      fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);                    \
    }                                                                                    \
  } while (0)
#define CHECK_EQ(a, b) CHECK((a) == (b))

/* xorshift64* test PRNG (deterministic) */
static uint64_t g_rng = 0x2545F4914F6CDD1Dull;
static uint64_t rnd(void) {
  g_rng ^= g_rng >> 12;
  g_rng ^= g_rng << 25;
  g_rng ^= g_rng >> 27;
  return g_rng * 0x2545F4914F6CDD1Dull;
}

static uint64_t *make_hashes(size_t n, uint64_t seed, uint64_t first) {
  uint64_t *h = (uint64_t *)malloc((n ? n : 1) * sizeof *h);
  for (size_t i = 0; i < n; i++) h[i] = rb_hash_i64((int64_t)(first + i), seed);
  return h;
}

/* ---- bit operations (run in both the builtin and the RB_PORTABLE=1 build) ---- */
static unsigned naive_ctz(uint64_t x) {
  unsigned n = 0;
  while (!(x & 1u)) { x >>= 1; n++; }
  return n;
}
static uint64_t naive_parity(uint64_t x) {
  uint64_t p = 0;
  for (; x; x >>= 1) p ^= x & 1u;
  return p;
}
static uint64_t ref_mulhi(uint64_t a, uint64_t b) { /* schoolbook on 16-bit limbs */
  uint64_t limbs[8] = {0};
  for (unsigned i = 0; i < 4; i++)
    for (unsigned j = 0; j < 4; j++) {
      uint64_t prod = ((a >> (16 * i)) & 0xffffu) * ((b >> (16 * j)) & 0xffffu);
      uint64_t carry = prod;
      for (unsigned k = i + j; k < 8 && carry; k++) {
        carry += limbs[k];
        limbs[k] = carry & 0xffffu;
        carry >>= 16;
      }
    }
  return limbs[4] | limbs[5] << 16 | limbs[6] << 32 | limbs[7] << 48;
}
static void test_bitops(void) {
  for (unsigned i = 0; i < 64; i++) {
    CHECK_EQ(rb_ctz64(UINT64_C(1) << i), i);
    CHECK_EQ(rb_parity64(UINT64_C(1) << i), 1u);
  }
  CHECK_EQ(rb_parity64(0), 0u);
  CHECK_EQ(rb_parity64(~UINT64_C(0)), 0u);
  for (int t = 0; t < 20000; t++) {
    unsigned shift = (unsigned)(rnd() % 64); /* sequenced: C leaves the order of operands unspecified */
    uint64_t x = rnd() >> shift;
    if (x) CHECK_EQ(rb_ctz64(x), naive_ctz(x));
    CHECK_EQ(rb_parity64(x), naive_parity(x));
    uint64_t y = rnd();
    CHECK_EQ(rb_mulhi64(x, y), ref_mulhi(x, y));
  }
  CHECK_EQ(rb_mulhi64(~UINT64_C(0), ~UINT64_C(0)), ~UINT64_C(0) - 1u);
  CHECK_EQ(rb_mulhi64(0, ~UINT64_C(0)), 0u);
  uint8_t buf[9] = {0xff, 1, 2, 3, 4, 5, 6, 7, 8};
  CHECK_EQ(rb_load_le64(buf + 1), UINT64_C(0x0807060504030201));
  uint8_t out[8];
  rb_store_le64(out, UINT64_C(0x1122334455667788));
  CHECK_EQ(out[0], 0x88);
  CHECK_EQ(out[7], 0x11);
}

/* ---- hashes and derivation against the Python reference (known-answer vectors) ---- */
static void test_vectors_hash(void) {
  CHECK_EQ(rb_mix64(RB_GAMMA), UINT64_C(0xe220a8397b1dcdaf)); /* published SplitMix64 output for seed 0 */
  for (size_t i = 0; i < sizeof vec_xxh3_tbl / sizeof *vec_xxh3_tbl; i++)
    CHECK_EQ(rb_xxh3_64(vec_xxh3_tbl[i].data, vec_xxh3_tbl[i].len), vec_xxh3_tbl[i].xxh3);
  const unsigned char *msgs[] = {vec_msg0, vec_msg1, vec_msg2, vec_msg3, vec_msg4, vec_msg5,
                                 vec_msg6, vec_msg7, vec_msg8, vec_msg9, vec_msg10, vec_msg11};
  for (size_t i = 0; i < sizeof vec_hash_tbl / sizeof *vec_hash_tbl; i++) {
    const vec_hash *v = &vec_hash_tbl[i];
    CHECK_EQ(rb_hash_bytes(msgs[v->msg], vec_xxh3_tbl[v->msg].len, v->seed, (rb_key_kind)v->kind), v->hash);
  }
  for (size_t i = 0; i < sizeof vec_i64_tbl / sizeof *vec_i64_tbl; i++)
    CHECK_EQ(rb_hash_i64(vec_i64_tbl[i].value, vec_i64_tbl[i].seed), vec_i64_tbl[i].hash);
  for (size_t i = 0; i < sizeof vec_derive_tbl / sizeof *vec_derive_tbl; i++) {
    const vec_derive *v = &vec_derive_tbl[i];
    rb_eq eq = rb_derive(v->h, rb_attempt_salt(v->attempt), v->rows - 63u, v->r);
    CHECK_EQ(eq.start, v->start);
    CHECK_EQ(eq.coeff, v->coeff);
    CHECK_EQ(eq.fp, v->fp);
    CHECK(eq.start <= v->rows - 64u);
    CHECK(eq.coeff & 1u);
  }
  /* key kinds are distinct keys */
  CHECK(rb_hash_bytes("a", 1, 0, RB_KEY_BYTES) != rb_hash_bytes("a", 1, 0, RB_KEY_STR));
  CHECK(rb_hash_bytes("a", 1, 0, RB_KEY_BYTES) != rb_hash_i64(97, 0));
  CHECK(rb_hash_bytes(NULL, 0, 0, RB_KEY_BYTES) == rb_hash_bytes("", 0, 0, RB_KEY_BYTES));
}

/* ---- whole filters must match the Python reference byte for byte ---- */
static void test_vectors_filters(void) {
  for (size_t t = 0; t < sizeof vec_filter_tbl / sizeof *vec_filter_tbl; t++) {
    const vec_filter *v = &vec_filter_tbl[t];
    uint64_t *h = make_hashes(v->n, v->seed, 0);
    rb_params p = rb_params_default();
    p.fp_bits = v->r;
    p.seed = v->seed;
    p.overhead = v->overhead;
    rb_filter *f = NULL;
    rb_build_info info;
    CHECK_EQ(rb_build(h, v->n, &p, &f, &info), RB_OK);
    CHECK(f != NULL);
    if (f) {
      CHECK_EQ(info.attempts, v->attempt + 1u);
      CHECK_EQ(info.num_rows, v->rows);
      size_t sz = rb_serialized_size(f);
      CHECK_EQ(sz, v->len);
      uint8_t *buf = (uint8_t *)malloc(sz);
      CHECK_EQ(rb_serialize(f, buf, sz), RB_OK);
      CHECK(memcmp(buf, v->bytes, v->len) == 0);
      free(buf);
      rb_free(f);
    }
    /* and the reference bytes load and answer correctly */
    rb_filter *g = NULL;
    CHECK_EQ(rb_from_buffer(v->bytes, v->len, 1, &g), RB_OK);
    if (g) {
      for (size_t i = 0; i < v->n; i++) CHECK(rb_contains(g, h[i]));
      CHECK_EQ(rb_num_keys(g), v->n);
      rb_free(g);
    }
    free(h);
  }
}

/* ---- no false negatives across sizes and parameters ---- */
static void build_and_check(size_t n, uint32_t r, uint64_t seed, double overhead) {
  uint64_t *h = make_hashes(n, seed, 0);
  rb_params p = rb_params_default();
  p.fp_bits = r;
  p.seed = seed;
  p.overhead = overhead;
  rb_filter *f = NULL;
  rb_build_info info;
  rb_status st = rb_build(h, n, &p, &f, &info);
  CHECK_EQ(st, RB_OK);
  if (st == RB_OK) {
    int missing = 0;
    for (size_t i = 0; i < n; i++) missing += !rb_contains(f, h[i]);
    CHECK_EQ(missing, 0);
    uint8_t *out = (uint8_t *)malloc(n ? n : 1);
    rb_contains_many(f, h, n, out);
    for (size_t i = 0; i < n; i++) missing += out[i] != 1;
    CHECK_EQ(missing, 0);
    free(out);
    CHECK_EQ(rb_num_keys(f), n);
    CHECK_EQ(rb_fp_bits(f), r);
    CHECK(n == 0 ? rb_num_rows(f) == 0 : (rb_num_rows(f) % 64 == 0 && rb_num_rows(f) >= 128 && rb_num_rows(f) >= n));
    rb_free(f);
  }
  free(h);
}
static void test_no_false_negatives(void) {
  const size_t sizes[] = {0, 1, 2, 3, 63, 64, 65, 127, 128, 129, 1000, 4097, 100000};
  for (size_t i = 0; i < sizeof sizes / sizeof *sizes; i++) build_and_check(sizes[i], 8, 0, -1.0);
  for (uint32_t r = 1; r <= 32; r++) build_and_check(777, r, r * 31u, -1.0);
  build_and_check(5000, 8, 99, 0.12);
  build_and_check(2000, 1, 0, 0.0);
  build_and_check(1000000, 8, 0, -1.0);
}

static void test_duplicates(void) {
  size_t n = 3000;
  uint64_t *h = (uint64_t *)malloc(3 * n * sizeof *h);
  uint64_t *base = make_hashes(n, 0, 0);
  for (size_t i = 0; i < n; i++) h[i] = h[n + i] = h[2 * n + i] = base[i]; /* every key three times */
  rb_filter *f = NULL;
  CHECK_EQ(rb_build(h, 3 * n, NULL, &f, NULL), RB_OK);
  if (f) {
    for (size_t i = 0; i < n; i++) CHECK(rb_contains(f, base[i]));
    CHECK_EQ(rb_num_keys(f), 3 * n); /* inputs counted, duplicates included */
    rb_free(f);
  }
  /* n identical hashes: a single distinct equation */
  uint64_t same[500];
  for (int i = 0; i < 500; i++) same[i] = base[7];
  CHECK_EQ(rb_build(same, 500, NULL, &f, NULL), RB_OK);
  if (f) {
    CHECK(rb_contains(f, base[7]));
    rb_free(f);
  }
  free(base);
  free(h);
}

static void test_failure_is_reported(void) {
  /* overhead 0 and one attempt cannot succeed for 100k keys: must fail cleanly, never return a filter */
  uint64_t *h = make_hashes(100000, 0, 0);
  rb_params p = rb_params_default();
  p.overhead = 0.0;
  p.max_attempts = 1;
  rb_filter *f = (rb_filter *)0x1;
  CHECK_EQ(rb_build(h, 100000, &p, &f, NULL), RB_E_CONSTRUCT);
  CHECK(f == NULL);
  /* with the default retry budget the same overhead succeeds (growth kicks in from the third attempt) */
  p.max_attempts = 0;
  rb_build_info info;
  CHECK_EQ(rb_build(h, 100000, &p, &f, &info), RB_OK);
  if (f) {
    CHECK(info.attempts > 2);
    for (size_t i = 0; i < 100000; i += 7) CHECK(rb_contains(f, h[i]));
    rb_free(f);
  }
  free(h);
}

static void test_param_validation(void) {
  uint64_t h[4] = {1, 2, 3, 4};
  rb_filter *f = NULL;
  rb_params p = rb_params_default();
  CHECK_EQ(rb_build(h, 4, &p, NULL, NULL), RB_E_INVALID_ARG);
  p.fp_bits = 0;
  CHECK_EQ(rb_build(h, 4, &p, &f, NULL), RB_E_INVALID_ARG);
  p.fp_bits = 33;
  CHECK_EQ(rb_build(h, 4, &p, &f, NULL), RB_E_INVALID_ARG);
  p = rb_params_default();
  p.max_attempts = 256;
  CHECK_EQ(rb_build(h, 4, &p, &f, NULL), RB_E_INVALID_ARG);
  p = rb_params_default();
  p.overhead = NAN;
  CHECK_EQ(rb_build(h, 4, &p, &f, NULL), RB_E_INVALID_ARG);
  p.overhead = 5.0;
  CHECK_EQ(rb_build(h, 4, &p, &f, NULL), RB_E_INVALID_ARG);
  CHECK_EQ(rb_build(NULL, 4, NULL, &f, NULL), RB_E_INVALID_ARG);
  CHECK(f == NULL);
  rb_free(NULL);
  CHECK(strlen(rb_strerror(RB_E_CHECKSUM)) > 0);
}

/* ---- the sizing table is integer arithmetic and must match the Python reference exactly ---- */
static void test_default_overhead_ppm_vectors(void) {
  for (size_t i = 0; i < sizeof vec_ppm_tbl / sizeof *vec_ppm_tbl; i++)
    CHECK_EQ((uint64_t)(rb_default_overhead(vec_ppm_tbl[i].n) * 1e6 + 0.5), vec_ppm_tbl[i].ppm);
}

/* ---- default overhead table ---- */
static void test_default_overhead(void) {
  double prev = 0.0;
  CHECK(rb_default_overhead(1) > 0.0);
  for (uint64_t n = 1u << 10; n < (UINT64_C(1) << 36); n = n + n / 3 + 1) {
    double e = rb_default_overhead(n);
    CHECK(e >= 0.04 && e < 0.35);
    CHECK(e >= prev - 1e-12); /* non-decreasing from 2^10 up */
    prev = e;
  }
}

/* ---- seeds give independent hash universes, even for dense integer keys ---- */
static int cmp_u64(const void *a, const void *b) {
  uint64_t x = *(const uint64_t *)a, y = *(const uint64_t *)b;
  return x < y ? -1 : x > y;
}
static void test_seed_independence(void) {
  /* Mixing the seed in by XOR made {i ^ seed} nearly the same set for nearby seeds, so seed 1 rebuilt (almost)
   * the filter of seed 0 for keys 0..n-1. Guard: the hash sets must be disjoint and the false positives independent. */
  const size_t n = 20000, probes = 200000;
  uint64_t *a = make_hashes(n, 0, 0), *b = make_hashes(n, 1, 0);
  uint64_t *a2 = (uint64_t *)malloc(n * sizeof *a2), *b2 = (uint64_t *)malloc(n * sizeof *b2);
  memcpy(a2, a, n * sizeof *a2);
  memcpy(b2, b, n * sizeof *b2);
  qsort(a2, n, sizeof *a2, cmp_u64);
  qsort(b2, n, sizeof *b2, cmp_u64);
  size_t i = 0, j = 0, common = 0;
  while (i < n && j < n) {
    if (a2[i] == b2[j]) { common++; i++; j++; }
    else if (a2[i] < b2[j]) i++;
    else j++;
  }
  CHECK_EQ(common, 0u);
  rb_params p = rb_params_default();
  p.fp_bits = 4;
  rb_filter *fa = NULL, *fb = NULL;
  p.seed = 0;
  CHECK_EQ(rb_build(a, n, &p, &fa, NULL), RB_OK);
  p.seed = 1;
  CHECK_EQ(rb_build(b, n, &p, &fb, NULL), RB_OK);
  if (fa && fb) {
    size_t both = 0;
    for (size_t k = 0; k < probes; k++) {
      int in_a = rb_contains(fa, rb_hash_i64((int64_t)(n + k), 0));
      int in_b = rb_contains(fb, rb_hash_i64((int64_t)(n + k), 1));
      both += (size_t)(in_a && in_b);
    }
    printf("  seed independence: %zu of %zu probes are false positives in both filters (expected ~%zu)\n", both, probes,
           probes / 256);
    CHECK(both > 400 && both < 1200); /* independent: 781 +- 28; identical filters would give ~12500 */
  }
  rb_free(fa);
  rb_free(fb);
  free(a); free(b); free(a2); free(b2);
}

/* ---- statistical false-positive rate ---- */
static void test_fpr(void) {
  const size_t n = 20000, probes = 2000000;
  const uint32_t rs[] = {1, 2, 4, 8, 12};
  for (size_t t = 0; t < sizeof rs / sizeof *rs; t++) {
    uint32_t r = rs[t];
    uint64_t *h = make_hashes(n, 11, 0);
    rb_params p = rb_params_default();
    p.fp_bits = r;
    p.seed = 11;
    rb_filter *f = NULL;
    CHECK_EQ(rb_build(h, n, &p, &f, NULL), RB_OK);
    if (f) {
      size_t fp = 0;
      for (size_t i = 0; i < probes; i++) fp += (size_t)rb_contains(f, rb_hash_i64((int64_t)(n + i), 11));
      double pr = 1.0 / (double)(UINT64_C(1) << r);
      double mean = pr * (double)probes, sigma = sqrt((double)probes * pr * (1.0 - pr));
      printf("  fpr r=%2u: %zu false positives of %zu probes, expected %.1f +- %.1f (measured %.3g, 2^-r %.3g)\n", r, fp,
             probes, mean, sigma, (double)fp / (double)probes, pr);
      CHECK(fabs((double)fp - mean) < 6.0 * sigma);
      rb_free(f);
    }
    free(h);
  }
}

/* ---- serialization round trip, zero-copy view, unaligned buffers ---- */
static void test_roundtrip_and_view(void) {
  const size_t sizes[] = {0, 1, 64, 1000, 20000};
  for (size_t s = 0; s < sizeof sizes / sizeof *sizes; s++) {
    size_t n = sizes[s];
    uint64_t *h = make_hashes(n, 5, 0);
    rb_params p = rb_params_default();
    p.seed = 5;
    p.fp_bits = 9;
    rb_filter *f = NULL;
    CHECK_EQ(rb_build(h, n, &p, &f, NULL), RB_OK);
    size_t sz = rb_serialized_size(f);
    uint8_t *raw = (uint8_t *)malloc(sz + 8);
    uint8_t *buf = raw + 1; /* deliberately misaligned */
    CHECK_EQ(rb_serialize(f, buf, sz - 1), RB_E_INVALID_ARG);
    CHECK_EQ(rb_serialize(f, buf, sz), RB_OK);
    rb_filter *g = NULL;
    CHECK_EQ(rb_from_buffer(buf, sz, 1, &g), RB_OK);
    if (g) {
      CHECK_EQ(rb_num_keys(g), n);
      CHECK_EQ(rb_num_rows(g), rb_num_rows(f));
      CHECK_EQ(rb_fp_bits(g), 9u);
      CHECK_EQ(rb_seed(g), 5u);
      CHECK_EQ(rb_serialized_size(g), sz);
      for (size_t i = 0; i < n; i++) CHECK(rb_contains(g, h[i]));
      for (size_t i = 0; i < 2000; i++) {
        uint64_t q = rb_hash_i64((int64_t)(n + i), 5);
        CHECK_EQ(rb_contains(g, q), rb_contains(f, q));
      }
      uint8_t *buf2 = (uint8_t *)malloc(sz); /* a view re-serializes to identical bytes */
      CHECK_EQ(rb_serialize(g, buf2, sz), RB_OK);
      CHECK(memcmp(buf, buf2, sz) == 0);
      free(buf2);
      rb_free(g);
    }
    CHECK_EQ(rb_from_buffer(buf, sz, 0, &g), RB_OK);
    rb_free(g);
    free(raw);
    rb_free(f);
    free(h);
  }
}

/* ---- the loader treats input as untrusted ---- */
static void fix_header_checksum(uint8_t *h) { rb_store_le64(h + 56, rb_xxh3_64(h, 56)); }

static rb_status load(const uint8_t *buf, size_t len, int verify) {
  rb_filter *f = NULL;
  rb_status st = rb_from_buffer(buf, len, verify, &f);
  CHECK((st == RB_OK) == (f != NULL));
  if (f) { /* whatever loads must be safe to query */
    for (uint64_t i = 0; i < 200; i++) (void)rb_contains(f, rb_mix64(i));
    rb_free(f);
  }
  return st;
}

static void test_loader_hostile(void) {
  uint64_t *h = make_hashes(300, 3, 0);
  rb_params p = rb_params_default();
  p.seed = 3;
  rb_filter *f = NULL;
  CHECK_EQ(rb_build(h, 300, &p, &f, NULL), RB_OK);
  size_t sz = rb_serialized_size(f);
  uint8_t *good = (uint8_t *)malloc(sz);
  CHECK_EQ(rb_serialize(f, good, sz), RB_OK);
  CHECK_EQ(load(good, sz, 1), RB_OK);

  /* every truncation length */
  for (size_t len = 0; len < sz; len++) CHECK(load(good, len, 1) == RB_E_TRUNCATED);
  rb_filter *tmp = NULL;
  CHECK_EQ(rb_from_buffer(NULL, 0, 1, &tmp), RB_E_TRUNCATED);
  CHECK(tmp == NULL);
  /* trailing bytes */
  uint8_t *longer = (uint8_t *)malloc(sz + 1);
  memcpy(longer, good, sz);
  longer[sz] = 0;
  CHECK_EQ(load(longer, sz + 1, 1), RB_E_FORMAT);
  free(longer);

  /* every single-bit flip in the header is rejected (by a field rule or a checksum) */
  uint8_t *bad = (uint8_t *)malloc(sz);
  for (size_t byte = 0; byte < RB_HEADER_SIZE; byte++)
    for (unsigned bit = 0; bit < 8; bit++) {
      memcpy(bad, good, sz);
      bad[byte] ^= (uint8_t)(1u << bit);
      CHECK(load(bad, sz, 0) != RB_OK);
    }
  /* a payload flip: caught with verify, memory-safe without */
  for (size_t byte = RB_HEADER_SIZE; byte < sz; byte += 17) {
    memcpy(bad, good, sz);
    bad[byte] ^= 0x10;
    CHECK_EQ(load(bad, sz, 1), RB_E_CHECKSUM);
    CHECK_EQ(load(bad, sz, 0), RB_OK);
  }
  /* specific classes, with the header checksum repaired so the field rules are what rejects them */
  struct { size_t off; uint8_t val; rb_status want; } tweaks[] = {
      {8, 2, RB_E_VERSION}, {10, 65, RB_E_FORMAT}, {12, 7, RB_E_FORMAT}, {13, 0, RB_E_FORMAT},
      {13, 33, RB_E_FORMAT}, {14, 2, RB_E_FORMAT}, {15, 1, RB_E_FORMAT}, {44, 1, RB_E_FORMAT},
  };
  for (size_t t = 0; t < sizeof tweaks / sizeof *tweaks; t++) {
    memcpy(bad, good, sz);
    bad[tweaks[t].off] = tweaks[t].val;
    fix_header_checksum(bad);
    CHECK_EQ(load(bad, sz, 0), tweaks[t].want);
  }
  memcpy(bad, good, 8);
  memcpy(bad, "PYRIBBOX", 8);
  CHECK_EQ(load(bad, sz, 0), RB_E_MAGIC);
  /* hostile sizes: rows not a multiple of 64, too small, huge, overflowing; num_keys with zero rows */
  const uint64_t rows_bad[] = {1, 63, 65, 64, 127, 130, UINT64_C(1) << 40 | 64, UINT64_C(1) << 41, ~UINT64_C(0),
                               ~UINT64_C(0) - 63u, UINT64_C(0x8000000000000000)};
  for (size_t t = 0; t < sizeof rows_bad / sizeof *rows_bad; t++) {
    memcpy(bad, good, sz);
    rb_store_le64(bad + 24, rows_bad[t]);
    fix_header_checksum(bad);
    CHECK_EQ(load(bad, sz, 1), RB_E_FORMAT);
  }
  /* rows = 64 with a payload of exactly matching length: only the minimum-size rule (>= 128) can reject it */
  uint8_t tiny[RB_HEADER_SIZE + 64];
  memset(tiny, 0, sizeof tiny);
  memcpy(tiny, good, RB_HEADER_SIZE);
  rb_store_le64(tiny + 24, 64);
  fix_header_checksum(tiny);
  CHECK_EQ(load(tiny, sizeof tiny, 0), RB_E_FORMAT);
  /* num_keys must be consistent with rows: non-empty filters have 1..rows keys, empty ones none */
  const uint64_t rows_good = rb_load_le64(good + 24);
  const struct { uint64_t keys; rb_status want; } key_cases[] = {
      {0, RB_E_FORMAT}, {1, RB_OK}, {rows_good, RB_OK}, {rows_good + 1, RB_E_FORMAT},
      {UINT64_C(1) << 63, RB_E_FORMAT}, {~UINT64_C(0), RB_E_FORMAT}};
  for (size_t t = 0; t < sizeof key_cases / sizeof *key_cases; t++) {
    memcpy(bad, good, sz);
    rb_store_le64(bad + 16, key_cases[t].keys);
    fix_header_checksum(bad);
    CHECK_EQ(load(bad, sz, 0), key_cases[t].want);
  }
  /* a valid-looking header that declares a 2^40-row payload on a 64-byte buffer must be truncated, not read */
  memcpy(bad, good, RB_HEADER_SIZE);
  rb_store_le64(bad + 24, UINT64_C(1) << 40);
  fix_header_checksum(bad);
  CHECK_EQ(load(bad, RB_HEADER_SIZE, 0), RB_E_TRUNCATED);
  memcpy(bad, good, RB_HEADER_SIZE);
  rb_store_le64(bad + 24, 0);
  fix_header_checksum(bad);
  CHECK_EQ(load(bad, RB_HEADER_SIZE, 0), RB_E_FORMAT); /* zero rows but num_keys != 0 */
  rb_store_le64(bad + 16, 0);
  fix_header_checksum(bad);
  CHECK_EQ(load(bad, RB_HEADER_SIZE, 0), RB_OK);       /* a genuine empty filter */
  free(bad);
  free(good);
  rb_free(f);
  free(h);
}

/* ---- status strings: one distinct, non-empty text per status, and a fallback for a value outside the enum ---- */
static void test_strerror(void) {
  const char *seen[RB_E_CHECKSUM + 1];
  for (int s = RB_OK; s <= RB_E_CHECKSUM; s++) {
    seen[s] = rb_strerror((rb_status)s);
    CHECK(strlen(seen[s]) > 0);
    CHECK(strcmp(seen[s], "unknown status") != 0);
    for (int t = RB_OK; t < s; t++) CHECK(strcmp(seen[s], seen[t]) != 0);
  }
  CHECK(strcmp(rb_strerror(RB_OK), "ok") == 0);
  CHECK(strcmp(rb_strerror((rb_status)(RB_E_CHECKSUM + 1)), "unknown status") == 0);
}

/* ---- sizes beyond the supported range are refused before anything is allocated or read ---- */
static void test_too_large(void) {
#if SIZE_MAX > UINT32_MAX
  uint64_t dummy = 0; /* never dereferenced: the checks come first */
  rb_filter *f = (rb_filter *)0x1;
  CHECK_EQ(rb_build(&dummy, (size_t)(RB_MAX_KEYS + 1u), NULL, &f, NULL), RB_E_TOO_LARGE);
  CHECK(f == NULL);
  rb_params p = rb_params_default();
  p.overhead = 4.0; /* RB_MAX_KEYS keys at 5x the rows is 2^40.3 rows: over RB_MAX_ROWS */
  f = (rb_filter *)0x1;
  CHECK_EQ(rb_build(&dummy, (size_t)RB_MAX_KEYS, &p, &f, NULL), RB_E_TOO_LARGE);
  CHECK(f == NULL);
#endif
}

/* ---- null and undersized arguments of the serialization functions ---- */
static void test_api_arguments(void) {
  uint64_t *h = make_hashes(300, 0, 0);
  rb_filter *f = NULL;
  CHECK_EQ(rb_build(h, 300, NULL, &f, NULL), RB_OK);
  size_t sz = rb_serialized_size(f);
  uint8_t *buf = (uint8_t *)malloc(sz);
  CHECK_EQ(rb_serialize(f, buf, sz), RB_OK);
  CHECK_EQ(rb_serialize(f, NULL, sz), RB_E_INVALID_ARG);
  CHECK_EQ(rb_serialize(f, buf, sz - 1), RB_E_INVALID_ARG);
  CHECK_EQ(rb_serialize(f, buf, 0), RB_E_INVALID_ARG);
  CHECK_EQ(rb_serialize(f, buf, sz + 100), RB_OK); /* a larger buffer is fine */
  rb_filter *g = (rb_filter *)0x1;
  CHECK_EQ(rb_from_buffer(buf, sz, 1, NULL), RB_E_INVALID_ARG);
  CHECK_EQ(rb_from_buffer(NULL, sz, 1, &g), RB_E_INVALID_ARG);
  CHECK(g == NULL);
  CHECK_EQ(rb_from_buffer(NULL, 0, 1, &g), RB_E_TRUNCATED); /* too short is reported before the null pointer */
  CHECK_EQ(rb_from_buffer(buf, sz, 0, &g), RB_OK);          /* verify_payload = 0 */
  rb_free(g);
  CHECK_EQ(rb_seed(f), 0u);
  free(buf);
  rb_free(f);
  free(h);
}

/* ---- the insertion order is an implementation detail: grouped by start row or in arrival order, same filter ---- */
static void same_filter_in_every_mode(const uint64_t *h, size_t n, const rb_params *p, int bucket_a, int bucket_b) {
  rb_filter *fa = NULL, *fb = NULL;
  rb_build_info ia = {0, 0}, ib = {0, 0};
  rb_status sa = rb_build_ex(h, n, p, bucket_a, &fa, &ia), sb = rb_build_ex(h, n, p, bucket_b, &fb, &ib);
  CHECK_EQ(sa, sb);
  CHECK((fa == NULL) == (fb == NULL));
  if (!fa || !fb) { rb_free(fa); rb_free(fb); return; }
  CHECK_EQ(ia.attempts, ib.attempts);
  CHECK_EQ(ia.num_rows, ib.num_rows);
  size_t sz = rb_serialized_size(fa);
  CHECK_EQ(sz, rb_serialized_size(fb));
  uint8_t *ba = (uint8_t *)malloc(sz), *bb = (uint8_t *)malloc(sz);
  CHECK(rb_serialize(fa, ba, sz) == RB_OK && rb_serialize(fb, bb, sz) == RB_OK);
  CHECK(memcmp(ba, bb, sz) == 0);
  free(ba);
  free(bb);
  rb_free(fa);
  rb_free(fb);
}

static void test_insertion_order_does_not_change_the_filter(void) {
  static const size_t sizes[] = {1, 2, 63, 64, 65, 1000, 5000, 100000, 300000};
  static const uint32_t bits[] = {1, 8, 13, 32};
  for (size_t si = 0; si < sizeof sizes / sizeof *sizes; si++) {
    uint64_t *h = make_hashes(sizes[si], 7, 1000);
    for (size_t bi = 0; bi < sizeof bits / sizeof *bits; bi++) {
      if (sizes[si] == 300000 && bi != 1) continue;
      rb_params p = rb_params_default();
      p.fp_bits = bits[bi];
      p.seed = si;
      same_filter_in_every_mode(h, sizes[si], &p, 0, 1);
    }
    free(h);
  }
  /* automatic choice (above 2^18 rows the bucketed path) against arrival order */
  uint64_t *big = make_hashes(300000, 3, 0);
  same_filter_in_every_mode(big, 300000, NULL, -1, 0);
  free(big);
  /* failures and retries with growth: tight overhead, one attempt and the default budget */
  uint64_t *h = make_hashes(50000, 5, 0);
  rb_params p = rb_params_default();
  p.overhead = 0.0;
  p.max_attempts = 1;
  same_filter_in_every_mode(h, 50000, &p, 0, 1);
  p.max_attempts = 0;
  same_filter_in_every_mode(h, 50000, &p, 0, 1);
  p.overhead = 0.02;
  same_filter_in_every_mode(h, 50000, &p, 0, 1);
  /* duplicate keys and keys in descending order */
  uint64_t *d = (uint64_t *)malloc(60000 * sizeof *d);
  for (size_t i = 0; i < 60000; i++) d[i] = h[(59999 - i) % 20000];
  same_filter_in_every_mode(d, 60000, NULL, 0, 1);
  free(d);
  free(h);
  /* n = 0 */
  same_filter_in_every_mode(NULL, 0, NULL, 0, 1);
}

int main(void) {
  printf("pyribbon core tests (bit ops: %s)\n",
#if defined(RB_GNU)
         "compiler builtins"
#elif defined(RB_MSVC)
         "MSVC intrinsics"
#else
         "portable fallbacks"
#endif
  );
  test_bitops();
  test_vectors_hash();
  test_vectors_filters();
  test_no_false_negatives();
  test_duplicates();
  test_failure_is_reported();
  test_insertion_order_does_not_change_the_filter();
  test_param_validation();
  test_default_overhead();
  test_default_overhead_ppm_vectors();
  test_seed_independence();
  test_fpr();
  test_roundtrip_and_view();
  test_loader_hostile();
  test_strerror();
  test_too_large();
  test_api_arguments();
  printf("%d checks, %d failed\n", g_checks, g_failed);
  return g_failed ? 1 : 0;
}
