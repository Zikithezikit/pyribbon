/* Regenerates the default-overhead table (make calibrate). For slot counts m = 2^k it inserts equations derived
 * exactly as in the library (rb_derive, rb_band_insert) until the first failure, and records the fill j/m at that
 * point. A random key set of n keys builds in one attempt iff j >= n, so the fill quantiles give the success
 * probability directly. Prints the fill at the 50th/5th/3rd/1st percentile and the overhead 1/f - 1 for each.
 * Usage: calibrate KMIN KMAX [TRIALS_BUDGET_OPS]. Single translation unit with ribbon.c on purpose (static helpers). */
#include "../src/ribbon.c"

#include <stdio.h>

static int cmp_size(const void *a, const void *b) {
  size_t x = *(const size_t *)a, y = *(const size_t *)b;
  return x < y ? -1 : x > y;
}

int main(int argc, char **argv) {
  int kmin = argc > 1 ? atoi(argv[1]) : 7, kmax = argc > 2 ? atoi(argv[2]) : 22;
  double budget = argc > 3 ? atof(argv[3]) : 2e9;
  printf("%3s %10s %7s %8s %8s %8s %8s   %8s %8s %8s %8s\n", "k", "m", "trials", "f50", "f05", "f03", "f01", "ovh50",
         "ovh05", "ovh03", "ovh01");
  for (int k = kmin; k <= kmax; k++) {
    uint64_t m = UINT64_C(1) << (unsigned)k;
    int trials = (int)(budget / (double)m);
    if (trials > 6000) trials = 6000;
    if (trials < 300) trials = 300;
    uint64_t *coeff = (uint64_t *)calloc((size_t)m, sizeof *coeff);
    uint32_t *res = (uint32_t *)calloc((size_t)m, sizeof *res);
    size_t *js = (size_t *)malloc((size_t)trials * sizeof *js);
    uint64_t state = UINT64_C(0x1234567) + (uint64_t)k;
    for (int t = 0; t < trials; t++) {
      memset(coeff, 0, (size_t)m * sizeof *coeff);
      memset(res, 0, (size_t)m * sizeof *res);
      size_t j = 0;
      for (; j < m; j++) {
        state += RB_GAMMA;
        rb_eq eq = rb_derive(rb_mix64(state), 0, m - RB_WIDTH + 1u, 32);
        if (!rb_band_insert(coeff, res, eq.start, eq.coeff, eq.fp)) break;
      }
      js[t] = j;
    }
    qsort(js, (size_t)trials, sizeof *js, cmp_size);
    double f50 = (double)js[trials / 2] / (double)m, f05 = (double)js[(size_t)(0.05 * trials)] / (double)m,
           f03 = (double)js[(size_t)(0.03 * trials)] / (double)m, f01 = (double)js[(size_t)(0.01 * trials)] / (double)m;
    printf("%3d %10llu %7d %8.4f %8.4f %8.4f %8.4f   %7.2f%% %7.2f%% %7.2f%% %7.2f%%\n", k, (unsigned long long)m, trials,
           f50, f05, f03, f01, 100 * (1 / f50 - 1), 100 * (1 / f05 - 1), 100 * (1 / f03 - 1), 100 * (1 / f01 - 1));
    fflush(stdout);
    free(coeff);
    free(res);
    free(js);
  }
  return 0;
}
