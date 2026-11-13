/*
 * bench_build.c - build throughput of rb_build, in nanoseconds per key.
 *
 *   bench_build [-n 1000,10000,...] [-r 8,16] [-runs 9]
 *
 * Keys are the integers 0..n-1 hashed with rb_hash_i64; only rb_build is timed (not hashing). Small n is
 * repeated inside one sample so that every sample lasts a few milliseconds at least. Each line reports the
 * median, minimum and maximum of the samples, the attempts the build used, and a checksum of the serialized
 * filter, so two versions of the core can be shown to produce the same bytes.
 *
 * The machine's other load moves absolute numbers by 10 percent or more. Compare two builds only by running them
 * alternately in one session: tools/ab_build.sh does that. Pin the process with `taskset -c N` (make bench-build does).
 */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#include "rb_internal.h"

static double now_ns(void) {
  struct timespec ts;
  clock_gettime(CLOCK_MONOTONIC, &ts);
  return (double)ts.tv_sec * 1e9 + (double)ts.tv_nsec;
}

static int cmp_double(const void *a, const void *b) {
  double x = *(const double *)a, y = *(const double *)b;
  return (x > y) - (x < y);
}

static size_t parse_list(const char *s, size_t *out, size_t cap) {
  size_t k = 0;
  while (*s && k < cap) {
    char *end;
    out[k++] = (size_t)strtod(s, &end); /* strtod so that 1e6 works */
    s = *end == ',' ? end + 1 : end;
    if (end == s && *s) break;
  }
  return k;
}

int main(int argc, char **argv) {
  size_t ns[16] = {1000, 10000, 100000, 1000000, 10000000}, nn = 5;
  size_t rs[16] = {8, 16}, nr = 2;
  size_t runs = 9;
  for (int a = 1; a + 1 < argc; a += 2) {
    if (!strcmp(argv[a], "-n")) nn = parse_list(argv[a + 1], ns, 16);
    else if (!strcmp(argv[a], "-r")) nr = parse_list(argv[a + 1], rs, 16);
    else if (!strcmp(argv[a], "-runs")) runs = (size_t)atoi(argv[a + 1]);
    else { fprintf(stderr, "usage: bench_build [-n list] [-r list] [-runs N]\n"); return 2; }
  }
  if (runs < 1 || runs > 99) return 2;

  printf("%10s %3s %8s %8s %8s %4s %16s\n", "n", "r", "med_ns", "min_ns", "max_ns", "att", "checksum");
  for (size_t ni = 0; ni < nn; ni++) {
    size_t n = ns[ni];
    uint64_t *h = (uint64_t *)malloc(n * sizeof *h);
    if (!h) return 1;
    for (size_t i = 0; i < n; i++) h[i] = rb_hash_i64((int64_t)i, 0);
    size_t reps = 3000000 / n + 1;
    for (size_t ri = 0; ri < nr; ri++) {
      rb_params p = rb_params_default();
      p.fp_bits = (uint32_t)rs[ri];
      double samples[100];
      uint32_t attempts = 0;
      uint64_t sum = 0;
      for (size_t s = 0; s < runs + 1; s++) { /* sample 0 is a warm-up */
        double t0 = now_ns();
        for (size_t k = 0; k < reps; k++) {
          rb_filter *f;
          rb_build_info info;
          if (rb_build(h, n, &p, &f, &info) != RB_OK) { fprintf(stderr, "build failed\n"); return 1; }
          if (s == 0 && k == 0) {
            size_t len = rb_serialized_size(f);
            uint8_t *buf = (uint8_t *)malloc(len);
            if (!buf || rb_serialize(f, buf, len) != RB_OK) return 1;
            sum = rb_xxh3_64(buf, len);
            free(buf);
            attempts = info.attempts;
          }
          rb_free(f);
        }
        double t = (now_ns() - t0) / (double)(reps * n);
        if (s > 0) samples[s - 1] = t;
      }
      qsort(samples, runs, sizeof samples[0], cmp_double);
      printf("%10zu %3zu %8.1f %8.1f %8.1f %4u %016llx\n", n, rs[ri], samples[runs / 2], samples[0], samples[runs - 1],
             attempts, (unsigned long long)sum);
      fflush(stdout);
    }
    free(h);
  }
  return 0;
}
