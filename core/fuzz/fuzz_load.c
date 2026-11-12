/* Fuzz harness for the buffer loader. Built two ways:
 *   - libFuzzer (clang -fsanitize=fuzzer,address,undefined): LLVMFuzzerTestOneInput + a custom mutator;
 *   - the built-in driver (-DFUZZ_DRIVER, any compiler with ASan/UBSan): same harness, deterministic PRNG.
 * Both repair the header checksum after mutating, half of the time, so the deeper field rules are exercised
 * instead of every input dying at the checksum.  Properties checked: the loader never crashes, never reads
 * outside the buffer (ASan), a status of RB_OK implies a filter and vice versa, whatever loads can be queried,
 * and a filter that loads re-serializes to a buffer that loads again. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "rb_internal.h"
#include "ribbon.h"

static void repair_header_checksum(uint8_t *data, size_t size) {
  if (size >= RB_HEADER_SIZE) rb_store_le64(data + 56, rb_xxh3_64(data, 56));
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size);
int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  for (int verify = 0; verify < 2; verify++) {
    rb_filter *f = NULL;
    rb_status st = rb_from_buffer(data, size, verify, &f);
    if ((st == RB_OK) != (f != NULL)) abort();
    if (!f) continue;
    for (uint64_t i = 0; i < 64; i++) (void)rb_contains(f, rb_mix64(i * 0x9e3779b97f4a7c15ull));
    uint64_t hs[16];
    uint8_t out[16];
    for (unsigned i = 0; i < 16; i++) hs[i] = rb_mix64(i + 1000u);
    rb_contains_many(f, hs, 16, out);
    size_t sz = rb_serialized_size(f);
    if (sz != size) abort(); /* the loader requires an exact length, so re-serializing must match it */
    uint8_t *copy = (uint8_t *)malloc(sz);
    if (!copy) abort();
    if (rb_serialize(f, copy, sz) != RB_OK) abort();
    rb_filter *g = NULL;
    if (rb_from_buffer(copy, sz, 0, &g) != RB_OK || !g) abort();
    for (unsigned i = 0; i < 16; i++) if (rb_contains(g, hs[i]) != out[i]) abort();
    rb_free(g);
    free(copy);
    rb_free(f);
  }
  return 0;
}

#ifdef FUZZ_DRIVER
static uint64_t g_state = 0x9e3779b97f4a7c15ull;
static uint64_t rnd(void) {
  g_state ^= g_state << 13;
  g_state ^= g_state >> 7;
  g_state ^= g_state << 17;
  return g_state;
}

static uint8_t *seed_filter(size_t n, uint32_t r, size_t *len) {
  uint64_t *h = (uint64_t *)malloc((n ? n : 1) * sizeof *h);
  for (size_t i = 0; i < n; i++) h[i] = rb_hash_i64((int64_t)i, 1);
  rb_params p = rb_params_default();
  p.fp_bits = r;
  p.seed = 1;
  rb_filter *f = NULL;
  if (rb_build(h, n, &p, &f, NULL) != RB_OK) abort();
  *len = rb_serialized_size(f);
  uint8_t *buf = (uint8_t *)malloc(*len);
  if (rb_serialize(f, buf, *len) != RB_OK) abort();
  rb_free(f);
  free(h);
  return buf;
}

int main(int argc, char **argv) {
  unsigned long iters = argc > 1 ? strtoul(argv[1], NULL, 10) : 1000000ul;
  size_t lens[4];
  uint8_t *seeds[4] = {seed_filter(0, 8, &lens[0]), seed_filter(50, 4, &lens[1]), seed_filter(400, 8, &lens[2]),
                       seed_filter(1000, 32, &lens[3])};
  const uint64_t interesting[] = {0, 1, 63, 64, 65, 127, 128, 129, 0xffffffffull, 1ull << 40, (1ull << 40) + 64,
                                  1ull << 63, ~0ull, ~0ull - 63u};
  unsigned long accepted = 0;
  for (unsigned long it = 0; it < iters; it++) {
    unsigned s = (unsigned)(rnd() % 4);
    size_t len = lens[s];
    /* worst case: 4 mutations, each of which may append up to 70 bytes (case 3 below) */
    uint8_t *buf = (uint8_t *)malloc(len + 4 * 70 + 8);
    memcpy(buf, seeds[s], len);
    unsigned muts = 1u + (unsigned)(rnd() % 4);
    for (unsigned m = 0; m < muts; m++) {
      switch (rnd() % 7) {
        case 0: if (len) buf[rnd() % len] ^= (uint8_t)(1u << (rnd() % 8)); break;               /* bit flip */
        case 1: if (len) buf[rnd() % len] = (uint8_t)rnd(); break;                              /* byte set */
        case 2: if (len > 1) len = rnd() % len; break;                                          /* truncate */
        case 3: for (unsigned k = 0; k < 1u + rnd() % 70; k++) buf[len++] = (uint8_t)rnd(); break; /* extend */
        case 4: if (len >= RB_HEADER_SIZE) rb_store_le64(buf + 16 + 8 * (rnd() % 2), interesting[rnd() % 14]); break;
        case 5: if (len >= RB_HEADER_SIZE) buf[8 + rnd() % 8] = (uint8_t)(rnd() % 80); break;   /* version/size/width/r/... */
        default: if (len >= RB_HEADER_SIZE) rb_store_le32(buf + 40, (uint32_t)rnd()); break;      /* attempt */
      }
    }
    if (rnd() & 1u) repair_header_checksum(buf, len);
    rb_filter *probe = NULL;
    if (rb_from_buffer(buf, len, 0, &probe) == RB_OK) accepted++;
    rb_free(probe);
    LLVMFuzzerTestOneInput(buf, len);
    free(buf);
  }
  printf("fuzz driver: %lu iterations, %lu inputs accepted by the loader, no crashes\n", iters, accepted);
  for (int i = 0; i < 4; i++) free(seeds[i]);
  return 0;
}
#else
size_t LLVMFuzzerMutate(uint8_t *data, size_t size, size_t max_size);
size_t LLVMFuzzerCustomMutator(uint8_t *data, size_t size, size_t max_size, unsigned int seed);
size_t LLVMFuzzerCustomMutator(uint8_t *data, size_t size, size_t max_size, unsigned int seed) {
  size = LLVMFuzzerMutate(data, size, max_size);
  if (seed & 1u) repair_header_checksum(data, size);
  return size;
}
#endif
