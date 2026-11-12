/* Measures construction failure against overhead with the real core (make ovh-sweep).
 * Per-attempt failure = fraction of builds with max_attempts = 1 that fail; mean attempts uses the default
 * retry budget. Sizes and trial counts are chosen to finish in a few minutes. */
#include <stdio.h>
#include <stdlib.h>

#include "ribbon.h"

/* Each trial uses its own key range: trials that share keys share hash values and are correlated, which biases
 * the failure-rate estimate (an early version of this tool re-used [0, n) with different seeds and overestimated it). */
static uint64_t *keys(size_t n, size_t first) {
  uint64_t *h = (uint64_t *)malloc(n * sizeof *h);
  for (size_t i = 0; i < n; i++) h[i] = rb_hash_i64((int64_t)(first + i), 0);
  return h;
}

int main(int argc, char **argv) {
  size_t max_n = argc > 1 ? (size_t)strtoull(argv[1], NULL, 10) : 1000000;
  const size_t sizes[] = {100, 300, 1000, 3000, 10000, 100000, 1000000, 10000000};
  printf("%10s %8s %9s %14s %14s %12s\n", "n", "trials", "overhead", "fail/attempt", "mean attempts", "bits/key r=8");
  for (size_t s = 0; s < sizeof sizes / sizeof *sizes; s++) {
    size_t n = sizes[s];
    if (n > max_n) break;
    int trials = n <= 1000 ? 4000 : n <= 10000 ? 1500 : n <= 100000 ? 300 : n <= 1000000 ? 60 : 12;
    /* the default overhead, and the default shifted down/up by 1 and 2 percentage points */
    for (int shift = -2; shift <= 2; shift++) {
      double eps = rb_default_overhead(n) + 0.01 * shift;
      if (eps < 0.0) continue;
      int failed = 0;
      double attempts = 0.0, rows = 0.0;
      for (int t = 0; t < trials; t++) {
        uint64_t *h = keys(n, (size_t)t * n);
        rb_params p = rb_params_default();
        p.overhead = eps;
        p.max_attempts = 1;
        rb_filter *f = NULL;
        rb_build_info info;
        if (rb_build(h, n, &p, &f, &info) != RB_OK) failed++;
        else { rows += (double)info.num_rows; rb_free(f); }
        p.max_attempts = 0;
        if (rb_build(h, n, &p, &f, &info) == RB_OK) { attempts += info.attempts; rb_free(f); }
        else attempts += 32;
        free(h);
      }
      double ok = (double)(trials - failed);
      printf("%10zu %8d %8.2f%% %13.2f%% %14.3f %12.3f%s\n", n, trials, 100.0 * eps, 100.0 * failed / trials,
             attempts / trials, ok > 0 ? 8.0 * rows / ok / (double)n : 0.0, shift == 0 ? "   <- default" : "");
      fflush(stdout);
    }
  }
  return 0;
}
