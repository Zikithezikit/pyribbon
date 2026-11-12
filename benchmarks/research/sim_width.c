/* Throwaway simulation: banded GF(2) elimination (Ribbon paper Alg. 1), W = 64*NW bit window.
 * For each slot count m: insert random equations until the first failure; j = keys added.
 * P(success for n keys) = P(j >= n), so overhead for 95% success = m / q05(j) - 1.  */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifndef NW
#define NW 1
#endif
#define WBITS (64 * NW)
static uint64_t rs[4];
static inline uint64_t rotl(uint64_t x, int k) { return (x << k) | (x >> (64 - k)); }
static inline uint64_t rnd(void) { /* xoshiro256** */
  uint64_t r = rotl(rs[1] * 5, 7) * 9, t = rs[1] << 17;
  rs[2] ^= rs[0]; rs[3] ^= rs[1]; rs[1] ^= rs[2]; rs[0] ^= rs[3]; rs[2] ^= t; rs[3] = rotl(rs[3], 45);
  return r;
}
static void seed(uint64_t s) { for (int i = 0; i < 4; i++) { s += 0x9e3779b97f4a7c15ull; uint64_t z = s; z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ull; z = (z ^ (z >> 27)) * 0x94d049bb133111ebull; rs[i] = z ^ (z >> 31); } }
static double now(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t); return t.tv_sec + 1e-9 * t.tv_nsec; }

static uint64_t *coef; static uint32_t *res;
/* returns 1 ok, 0 fail */
static int insert(size_t i, uint64_t *c, uint32_t b) {
  for (;;) {
    uint64_t *s = coef + i * NW;
    int empty = 1; for (int k = 0; k < NW; k++) if (s[k]) { empty = 0; break; }
    if (empty) { memcpy(s, c, NW * 8); res[i] = b; return 1; }
    int nz = 0;
    for (int k = 0; k < NW; k++) { c[k] ^= s[k]; nz |= c[k] != 0; }
    b ^= res[i];
    if (!nz) return b == 0;
    int j = 0;
#if NW == 1
    j = __builtin_ctzll(c[0]); c[0] >>= j;
#else
    if (c[0]) { j = __builtin_ctzll(c[0]); } else { j = 64 + __builtin_ctzll(c[1]); }
    if (j >= 64) { c[0] = c[1] >> (j - 64); c[1] = 0; }
    else if (j) { c[0] = (c[0] >> j) | (c[1] << (64 - j)); c[1] >>= j; }
#endif
    i += (size_t)j;
  }
}
static int cmp(const void *a, const void *b) { size_t x = *(const size_t *)a, y = *(const size_t *)b; return x < y ? -1 : x > y; }
int main(int argc, char **argv) {
  int kmin = atoi(argv[1]), kmax = atoi(argv[2]);
  seed(12345);
  printf("W=%d  (trials; q05/q50 of keys-added j; overhead%% = m/q-1; ns/key insert)\n", WBITS);
  printf("%5s %9s %7s %9s %9s %9s %9s %8s\n", "log2m", "m", "trials", "ovh@95%", "ovh@50%", "mean_ovh", "fill@q05", "ns/key");
  for (int k = kmin; k <= kmax; k++) {
    size_t m = (size_t)1 << k;
    int trials = k <= 13 ? 4000 : k <= 15 ? 2000 : k <= 17 ? 1000 : k <= 19 ? 400 : k <= 21 ? 200 : 100;
    coef = calloc(m * NW, 8); res = calloc(m, 4);
    size_t *js = malloc(trials * sizeof *js); double tot = 0; size_t totk = 0;
    for (int t = 0; t < trials; t++) {
      memset(coef, 0, m * NW * 8);
      size_t j = 0; double t0 = now();
      for (;; j++) {
        uint64_t c[NW]; for (int q = 0; q < NW; q++) c[q] = rnd(); c[0] |= 1;
        size_t start = (size_t)(((unsigned __int128)rnd() * (m - WBITS + 1)) >> 64);
        if (!insert(start, c, (uint32_t)rnd())) break;
        if (j >= m) break;
      }
      tot += now() - t0; totk += j + 1; js[t] = j;
    }
    qsort(js, trials, sizeof *js, cmp);
    size_t q05 = js[(size_t)(0.05 * trials)], q50 = js[trials / 2]; double mean = 0; for (int t = 0; t < trials; t++) mean += js[t]; mean /= trials;
    printf("%5d %9zu %7d %8.2f%% %8.2f%% %8.2f%% %8.3f %8.1f\n", k, m, trials, 100.0 * ((double)m / q05 - 1), 100.0 * ((double)m / q50 - 1), 100.0 * (m / mean - 1), (double)q05 / m, 1e9 * tot / totk);
    fflush(stdout); free(coef); free(res); free(js);
  }
  return 0;
}
