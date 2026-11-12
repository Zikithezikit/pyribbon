/* False-positive-rate report (make fpr-report): measured rate against 2^-r with many probes.
 * Members are the ints [0, n); negatives are the next `probes` ints (structured, sequential keys: the worst
 * case for a weak hash). Prints one row per (n, r) and flags anything beyond 5 sigma. */
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "ribbon.h"

int main(int argc, char **argv) {
  size_t big = argc > 1 ? (size_t)strtoull(argv[1], NULL, 10) : 100000000; /* probes for r >= 8 */
  const size_t ns[] = {1000, 100000, 1000000};
  const uint32_t rs[] = {1, 2, 4, 6, 8, 10, 12, 16, 20};
  int flagged = 0;
  printf("%9s %3s %12s %12s %12s %12s %7s %9s\n", "n", "r", "probes", "false pos", "measured", "2^-r", "z", "bits/key");
  for (size_t a = 0; a < sizeof ns / sizeof *ns; a++) {
    size_t n = ns[a];
    uint64_t *h = (uint64_t *)malloc(n * sizeof *h);
    for (size_t i = 0; i < n; i++) h[i] = rb_hash_i64((int64_t)i, 42);
    for (size_t b = 0; b < sizeof rs / sizeof *rs; b++) {
      uint32_t r = rs[b];
      size_t probes = r >= 8 ? big : big / 10;
      if (r > 12) probes = big; /* rare events need the most probes */
      rb_params p = rb_params_default();
      p.fp_bits = r;
      p.seed = 42;
      rb_filter *f = NULL;
      if (rb_build(h, n, &p, &f, NULL) != RB_OK) { fprintf(stderr, "build failed (n=%zu r=%u)\n", n, r); return 2; }
      size_t fp = 0, missing = 0;
      for (size_t i = 0; i < n; i++) missing += !rb_contains(f, h[i]);
      for (size_t i = 0; i < probes; i++) fp += (size_t)rb_contains(f, rb_hash_i64((int64_t)(n + i), 42));
      double pr = ldexp(1.0, -(int)r), mean = pr * (double)probes, sigma = sqrt((double)probes * pr * (1.0 - pr));
      double z = ((double)fp - mean) / sigma;
      printf("%9zu %3u %12zu %12zu %12.4g %12.4g %7.2f %9.3f%s%s\n", n, r, probes, fp, (double)fp / (double)probes, pr, z,
             8.0 * (double)rb_serialized_size(f) / (double)n, fabs(z) > 5.0 ? "  <-- OUTSIDE 5 sigma" : "",
             missing ? "  <-- FALSE NEGATIVES" : "");
      flagged += fabs(z) > 5.0 || missing;
      fflush(stdout);
      rb_free(f);
    }
    free(h);
  }
  return flagged ? 1 : 0;
}
