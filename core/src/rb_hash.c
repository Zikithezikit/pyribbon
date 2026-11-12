/*
 * rb_hash.c - key -> 64-bit master hash (hash id 1, DESIGN.md section 3.1).
 *
 *   bytes:  h0 = XXH3_64bits(data)            str: h0 = XXH3_64bits(utf8) ^ TAG_STR
 *   int64:  h0 = (uint64)value ^ TAG_INT      bigint: h0 = XXH3_64bits(le bytes) ^ TAG_BIGINT
 *   H = mix64(h0 + mix64(seed + GAMMA))
 *
 * The seed is pre-mixed and ADDED. Mixing it in by XOR let dense integer keys collide across seeds: the set of
 * values {i ^ seed} is nearly the same for nearby seeds, so seed=1 rebuilt (almost) the filter of seed=0. A random
 * 64-bit offset makes every seed an independent hash universe (found by measurement, see DESIGN.md section 3.1).
 *
 * XXH3 is vendored (BSD-2-Clause, core/vendor/xxhash.h). Configuration: inline-only, no
 * streaming API, scalar code path and the memcpy memory-access mode (the default mode lets
 * GCC miscompile unaligned reads; see RESEARCH.md section 10). Output is identical on every
 * platform by xxHash's design.
 */
#define XXH_INLINE_ALL
#define XXH_NO_STREAM
#define XXH_FORCE_MEMORY_ACCESS 0
#define XXH_VECTOR 0 /* XXH_SCALAR */
#include "xxhash.h"

#include "rb_internal.h"

#define RB_TAG_STR UINT64_C(0x6a09e667f3bcc908)    /* SHA-512 initial values: nothing-up-my-sleeve */
#define RB_TAG_INT UINT64_C(0xbb67ae8584caa73b)
#define RB_TAG_BIGINT UINT64_C(0x3c6ef372fe94f82b)

uint64_t rb_xxh3_64(const void *data, size_t len) {
  static const unsigned char empty[1] = {0};
  return (uint64_t)XXH3_64bits(len ? data : empty, len);
}

static uint64_t rb_seed_offset(uint64_t seed) { return rb_mix64(seed + RB_GAMMA); }

uint64_t rb_hash_bytes(const void *data, size_t len, uint64_t seed, rb_key_kind kind) {
  uint64_t h0 = rb_xxh3_64(data, len);
  if (kind == RB_KEY_STR) h0 ^= RB_TAG_STR;
  else if (kind == RB_KEY_BIGINT) h0 ^= RB_TAG_BIGINT;
  return rb_mix64(h0 + rb_seed_offset(seed));
}

uint64_t rb_hash_i64(int64_t value, uint64_t seed) {
  /* Conversion of a negative int64 to uint64 is defined (modulo 2^64): two's complement. */
  uint64_t h0 = (uint64_t)value ^ RB_TAG_INT;
  return rb_mix64(h0 + rb_seed_offset(seed));
}
