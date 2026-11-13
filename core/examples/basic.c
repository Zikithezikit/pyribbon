/*
 * basic.c - the C API from start to finish: hash keys, build a filter, query it, serialize it, load it back
 * without copying, and trigger every error a caller can get.
 *
 * Run it with `make -C core example` (the same flags as the unit tests), or by hand from core/:
 *   cc -std=c11 -Iinclude -isystem vendor examples/basic.c src/ribbon.c src/rb_hash.c -o basic && ./basic
 * It exits 0 when every check holds and 1 on the first one that does not.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ribbon.h"

#define COUNT(a) (sizeof(a) / sizeof((a)[0]))

/* A call that must succeed. */
static void check(rb_status st, const char *what) {
  if (st != RB_OK) {
    fprintf(stderr, "%s failed: %s\n", what, rb_strerror(st));
    exit(1);
  }
}

/* A call that must fail with one particular status. */
static void expect(rb_status got, rb_status want, const char *what) {
  printf("  %-46s -> %s\n", what, rb_strerror(got));
  if (got != want) {
    fprintf(stderr, "%s: expected \"%s\"\n", what, rb_strerror(want));
    exit(1);
  }
}

static void require(int ok, const char *what) {
  if (!ok) {
    fprintf(stderr, "check failed: %s\n", what);
    exit(1);
  }
}

static void *xmalloc(size_t n) {
  void *p = malloc(n);
  if (!p) {
    fputs("out of memory\n", stderr);
    exit(1);
  }
  return p;
}

int main(void) {
  /* 1. Hash the keys. The filter stores only these 64-bit values, never the keys. The seed must be the same here
   *    and in every later query. A string and a byte string with the same content are different keys. */
  const uint64_t seed = 7;
  const char *words[] = {"apple", "banana", "cherry"};
  const int64_t numbers[] = {42, -7, 1000000};
  uint64_t hashes[COUNT(words) + COUNT(numbers)];
  size_t n = 0;
  for (size_t i = 0; i < COUNT(words); i++) hashes[n++] = rb_hash_bytes(words[i], strlen(words[i]), seed, RB_KEY_STR);
  for (size_t i = 0; i < COUNT(numbers); i++) hashes[n++] = rb_hash_i64(numbers[i], seed);

  /* 2. Build. Start from the defaults and change what you need. `info` is optional. */
  rb_params params = rb_params_default();
  params.fp_bits = 10; /* false-positive rate about 2^-10 */
  params.seed = seed;
  rb_filter *f = NULL;
  rb_build_info info;
  check(rb_build(hashes, n, &params, &f, &info), "rb_build");
  printf("built: %llu keys, %llu rows, %u attempt(s), %zu bytes serialized\n", (unsigned long long)rb_num_keys(f),
         (unsigned long long)rb_num_rows(f), (unsigned)info.attempts, rb_serialized_size(f));

  /* 3. Query. A key that was added is always found; a key that was not is found with probability about 2^-fp_bits. */
  for (size_t i = 0; i < n; i++) require(rb_contains(f, hashes[i]), "a member is always found");
  const uint64_t absent[] = {rb_hash_bytes("durian", 6, seed, RB_KEY_STR), rb_hash_i64(43 + 1, seed),
                             rb_hash_bytes("apple", 5, seed, RB_KEY_BYTES)}; /* "apple" as bytes is a new key */
  const char *absent_names[] = {"\"durian\" (string)", "44 (int)", "\"apple\" (bytes)"};
  for (size_t i = 0; i < COUNT(absent); i++)
    printf("  %-18s -> %s\n", absent_names[i], rb_contains(f, absent[i]) ? "possibly present" : "absent");

  /* Many hashes at once: faster than a loop of rb_contains for large batches. */
  uint8_t found[COUNT(hashes)];
  rb_contains_many(f, hashes, n, found);
  for (size_t i = 0; i < n; i++) require(found[i] == 1, "rb_contains_many finds every member");

  /* How often does a non-member pass? Count over 100000 integers that were not added. */
  size_t false_positives = 0;
  for (int64_t v = 100; v < 100100; v++) false_positives += (size_t)rb_contains(f, rb_hash_i64(v, seed));
  printf("false positives: %zu of 100000 (expected about %d)\n", false_positives, 100000 >> params.fp_bits);

  /* 4. Serialize into a buffer you own. The size is known in advance. */
  size_t size = rb_serialized_size(f);
  uint8_t *buf = (uint8_t *)xmalloc(size);
  check(rb_serialize(f, buf, size), "rb_serialize");

  /* 5. Load it back without copying. `g` points into `buf`, so `buf` must outlive `g` and must not change.
   *    verify_payload = 1 reads every byte once to check the payload checksum. */
  rb_filter *g = NULL;
  check(rb_from_buffer(buf, size, 1, &g), "rb_from_buffer");
  for (size_t i = 0; i < n; i++) require(rb_contains(g, hashes[i]), "the loaded filter finds every member");
  require(rb_num_keys(g) == rb_num_keys(f) && rb_seed(g) == seed && rb_fp_bits(g) == 10, "metadata survives the trip");
  printf("loaded: %llu keys, seed %llu, fp_bits %u\n", (unsigned long long)rb_num_keys(g),
         (unsigned long long)rb_seed(g), (unsigned)rb_fp_bits(g));
  rb_free(g); /* free the filter before the buffer it views */

  /* 6. Every error a caller can get. A failed call sets *out to NULL, so there is nothing to free. */
  puts("errors:");
  uint8_t *bad = (uint8_t *)xmalloc(size + 1);
  rb_filter *h = NULL;

  /* rb_build */
  rb_params bad_params = params;
  bad_params.fp_bits = 0;
  expect(rb_build(hashes, n, &bad_params, &h, NULL), RB_E_INVALID_ARG, "rb_build, fp_bits = 0");
  require(h == NULL, "*out is NULL after a failed build");
  bad_params.fp_bits = RB_MAX_FP_BITS + 1u;
  expect(rb_build(hashes, n, &bad_params, &h, NULL), RB_E_INVALID_ARG, "rb_build, fp_bits = 33");
  expect(rb_build(NULL, n, &params, &h, NULL), RB_E_INVALID_ARG, "rb_build, NULL hashes");
#if SIZE_MAX > UINT32_MAX
  expect(rb_build(hashes, (size_t)RB_MAX_KEYS + 1u, &params, &h, NULL), RB_E_TOO_LARGE, "rb_build, 2^38 + 1 keys");
#endif
  {
    /* No spare rows and a single attempt: banding fails. A real caller would retry with another seed or the
     * default overhead. The hashes and the seed are fixed, so this always ends the same way. */
    enum { MANY = 4000 };
    uint64_t *many = (uint64_t *)xmalloc(MANY * sizeof *many);
    for (int64_t i = 0; i < MANY; i++) many[i] = rb_hash_i64(i, seed);
    rb_params tight = params;
    tight.overhead = 0.0;
    tight.max_attempts = 1;
    expect(rb_build(many, MANY, &tight, &h, NULL), RB_E_CONSTRUCT, "rb_build, no overhead, one attempt");
    free(many);
  }
  /* RB_E_NOMEM (an allocation failed) cannot be provoked portably; handle it the way the others are handled. */

  /* rb_serialize */
  expect(rb_serialize(f, buf, size - 1), RB_E_INVALID_ARG, "rb_serialize, buffer one byte short");

  /* rb_from_buffer */
  expect(rb_from_buffer(buf, RB_HEADER_SIZE - 1u, 0, &h), RB_E_TRUNCATED, "rb_from_buffer, shorter than the header");
  expect(rb_from_buffer(buf, size - 1u, 0, &h), RB_E_TRUNCATED, "rb_from_buffer, payload cut short");
  expect(rb_from_buffer(NULL, size, 0, &h), RB_E_INVALID_ARG, "rb_from_buffer, NULL buffer");

  memcpy(bad, buf, size);
  bad[size] = 0;
  expect(rb_from_buffer(bad, size + 1u, 0, &h), RB_E_FORMAT, "rb_from_buffer, one trailing byte");

  memcpy(bad, buf, size);
  bad[0] ^= 1u;
  expect(rb_from_buffer(bad, size, 0, &h), RB_E_MAGIC, "rb_from_buffer, wrong magic");

  memcpy(bad, buf, size);
  bad[8] = 2; /* the version field */
  expect(rb_from_buffer(bad, size, 0, &h), RB_E_VERSION, "rb_from_buffer, unknown version");

  memcpy(bad, buf, size);
  bad[16] ^= 1u; /* num_keys: the header checksum no longer matches */
  expect(rb_from_buffer(bad, size, 0, &h), RB_E_CHECKSUM, "rb_from_buffer, damaged header");

  memcpy(bad, buf, size);
  bad[RB_HEADER_SIZE] ^= 1u; /* the first payload byte */
  expect(rb_from_buffer(bad, size, 1, &h), RB_E_CHECKSUM, "rb_from_buffer, damaged payload, verify = 1");
  /* With verify_payload = 0 the same buffer loads: only the header was checked, so answers may be wrong. */
  check(rb_from_buffer(bad, size, 0, &h), "rb_from_buffer, damaged payload, verify = 0");
  printf("  %-46s -> %s\n", "rb_from_buffer, damaged payload, verify = 0", rb_strerror(RB_OK));
  rb_free(h);

  /* RB_E_FORMAT also covers a header that passes its checksum but holds an unsupported field value. Only a
   * writer that recomputes the header checksum can produce one, so there is nothing to simulate here. */

  /* 7. Clean up. rb_free(NULL) is allowed, so a cleanup path can free unconditionally. */
  free(bad);
  free(buf);
  rb_free(f);
  puts("ok");
  return 0;
}
