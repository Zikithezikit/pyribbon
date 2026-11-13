/* Allocation-failure tests for the C core. Build with -Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc (see Makefile).
 *
 * Every call into the core is repeated with the 0th, 1st, 2nd ... allocation failing, until a run needs fewer
 * allocations than the failing index and succeeds. Each failed run must return RB_E_NOMEM and no object; run under
 * ASan (make nomem) a leak or double free on any of those paths fails the test. Production code is untouched. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "ribbon.h"

static long g_fail_at = -1; /* 0-based index of the allocation to fail; -1 = none */
static long g_seen;         /* allocations made since the failure was armed */

void *__real_malloc(size_t n);
void *__real_calloc(size_t n, size_t m);
void *__real_realloc(void *p, size_t n);
void *__wrap_malloc(size_t n);
void *__wrap_calloc(size_t n, size_t m);
void *__wrap_realloc(void *p, size_t n);

static int should_fail(void) { return g_fail_at >= 0 && g_seen++ == g_fail_at; }
void *__wrap_malloc(size_t n) { return should_fail() ? NULL : __real_malloc(n); }
void *__wrap_calloc(size_t n, size_t m) { return should_fail() ? NULL : __real_calloc(n, m); }
void *__wrap_realloc(void *p, size_t n) { return should_fail() ? NULL : __real_realloc(p, n); }

static int g_checks, g_failed;
#define CHECK(cond)                                                       \
  do {                                                                    \
    g_checks++;                                                           \
    if (!(cond)) {                                                        \
      g_failed++;                                                         \
      fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);     \
    }                                                                     \
  } while (0)

static uint64_t *make_hashes(size_t n) {
  uint64_t *h = (uint64_t *)malloc((n ? n : 1) * sizeof *h);
  for (size_t i = 0; i < n; i++) h[i] = rb_hash_i64((int64_t)i, 0);
  return h;
}

/* Fail allocation k of rb_build for k = 0, 1, ... until it succeeds; returns how many allocations a success makes. */
static long sweep_build(const uint64_t *h, size_t n, const rb_params *p) {
  for (long k = 0;; k++) {
    rb_filter *f = (rb_filter *)0x1;
    g_seen = 0;
    g_fail_at = k;
    rb_status st = rb_build(h, n, p, &f, NULL);
    g_fail_at = -1;
    if (st == RB_OK) {
      CHECK(f != NULL);
      for (size_t i = 0; i < n && i < 50; i++) CHECK(rb_contains(f, h[i]));
      rb_free(f);
      return k;
    }
    CHECK(st == RB_E_NOMEM);
    CHECK(f == NULL);
    if (k > 1000) { CHECK(0 && "build kept failing"); return k; }
  }
}

static void test_build(void) {
  uint64_t *h = make_hashes(100000);
  rb_params p = rb_params_default();
  CHECK(sweep_build(h, 0, &p) == 1);   /* an empty filter: only the struct */
  CHECK(sweep_build(h, 1000, &p) == 3); /* struct, slot table, payload */
  /* overhead 0 forces retries; from the third attempt the table grows, so the slot table is allocated again */
  p.overhead = 0.0;
  CHECK(sweep_build(h, 100000, &p) > 3);
  free(h);
}

static void test_from_buffer(void) {
  uint64_t *h = make_hashes(500);
  rb_filter *f = NULL;
  CHECK(rb_build(h, 500, NULL, &f, NULL) == RB_OK);
  size_t len = rb_serialized_size(f);
  uint8_t *buf = (uint8_t *)malloc(len);
  CHECK(rb_serialize(f, buf, len) == RB_OK);
  rb_free(f);
  for (long k = 0;; k++) {
    rb_filter *g = (rb_filter *)0x1;
    g_seen = 0;
    g_fail_at = k;
    rb_status st = rb_from_buffer(buf, len, 1, &g);
    g_fail_at = -1;
    if (st == RB_OK) {
      CHECK(k == 1); /* the filter struct is the only allocation */
      rb_free(g);
      break;
    }
    CHECK(st == RB_E_NOMEM);
    CHECK(g == NULL);
    if (k > 10) { CHECK(0 && "from_buffer kept failing"); break; }
  }
  free(buf);
  free(h);
}

int main(void) {
  test_build();
  test_from_buffer();
  printf("nomem: %d checks, %d failed\n", g_checks, g_failed);
  return g_failed ? 1 : 0;
}
