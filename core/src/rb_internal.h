/*
 * rb_internal.h - internal helpers: portable bit operations, byte-order-independent
 * loads and stores, the SplitMix64 mixer, and the key-hash -> ribbon-coordinate derivation.
 *
 * Bit operations use compiler builtins where available and pure-C fallbacks otherwise.
 * Compile with -DRB_PORTABLE=1 to force the fallbacks (CI does, to keep them tested).
 */
#ifndef RB_INTERNAL_H
#define RB_INTERNAL_H

#include <stddef.h>
#include <stdint.h>

#include "ribbon.h"

#if !defined(RB_PORTABLE) && (defined(__GNUC__) || defined(__clang__))
#define RB_GNU 1
#elif !defined(RB_PORTABLE) && defined(_MSC_VER) && (defined(_M_X64) || defined(_M_ARM64))
#include <intrin.h>
#define RB_MSVC 1
#endif

/* Count trailing zeros. Precondition: x != 0. */
static inline unsigned rb_ctz64(uint64_t x) {
#if defined(RB_GNU)
  return (unsigned)__builtin_ctzll(x);
#elif defined(RB_MSVC)
  unsigned long index;
  _BitScanForward64(&index, x);
  return (unsigned)index;
#else
  unsigned n = 0;
  if ((x & 0xffffffffu) == 0) { n += 32; x >>= 32; }
  if ((x & 0xffffu) == 0) { n += 16; x >>= 16; }
  if ((x & 0xffu) == 0) { n += 8; x >>= 8; }
  if ((x & 0xfu) == 0) { n += 4; x >>= 4; }
  if ((x & 0x3u) == 0) { n += 2; x >>= 2; }
  if ((x & 0x1u) == 0) { n += 1; }
  return n;
#endif
}

/* Parity (XOR of all bits) of x: 0 or 1. */
static inline uint64_t rb_parity64(uint64_t x) {
#if defined(RB_GNU)
  return (uint64_t)__builtin_parityll(x);
#else
  x ^= x >> 32;
  x ^= x >> 16;
  x ^= x >> 8;
  x ^= x >> 4;
  return (0x6996u >> (x & 0xfu)) & 1u;
#endif
}

/* Hint that the cache line holding p will be read soon. A no-op where no prefetch instruction is known. */
static inline void rb_prefetch(const void *p) {
#if defined(RB_GNU)
  __builtin_prefetch(p, 0, 3);
#elif defined(RB_MSVC) && defined(_M_X64)
  _mm_prefetch((const char *)p, _MM_HINT_T0);
#elif defined(RB_MSVC) && defined(_M_ARM64)
  __prefetch(p);
#else
  (void)p;
#endif
}

/* High 64 bits of the 128-bit product a * b. */
static inline uint64_t rb_mulhi64(uint64_t a, uint64_t b) {
#if defined(RB_GNU) && defined(__SIZEOF_INT128__)
  return (uint64_t)(((unsigned __int128)a * b) >> 64);
#elif defined(RB_MSVC) && defined(_M_X64)
  unsigned __int64 high;
  (void)_umul128(a, b, &high);
  return high;
#elif defined(RB_MSVC) && defined(_M_ARM64)
  return __umulh(a, b);
#else
  uint64_t a_lo = a & 0xffffffffu, a_hi = a >> 32;
  uint64_t b_lo = b & 0xffffffffu, b_hi = b >> 32;
  uint64_t p0 = a_lo * b_lo, p1 = a_lo * b_hi, p2 = a_hi * b_lo, p3 = a_hi * b_hi;
  uint64_t mid = (p0 >> 32) + (p1 & 0xffffffffu) + (p2 & 0xffffffffu);
  return p3 + (p1 >> 32) + (p2 >> 32) + (mid >> 32);
#endif
}

/* Little-endian loads and stores, independent of host byte order and alignment. */
static inline uint64_t rb_load_le64(const uint8_t *p) {
  return (uint64_t)p[0] | (uint64_t)p[1] << 8 | (uint64_t)p[2] << 16 | (uint64_t)p[3] << 24 |
         (uint64_t)p[4] << 32 | (uint64_t)p[5] << 40 | (uint64_t)p[6] << 48 | (uint64_t)p[7] << 56;
}
static inline uint32_t rb_load_le32(const uint8_t *p) {
  return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}
static inline uint16_t rb_load_le16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static inline void rb_store_le64(uint8_t *p, uint64_t v) {
  for (unsigned i = 0; i < 8; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static inline void rb_store_le32(uint8_t *p, uint32_t v) {
  for (unsigned i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i));
}
static inline void rb_store_le16(uint8_t *p, uint16_t v) {
  p[0] = (uint8_t)v;
  p[1] = (uint8_t)(v >> 8);
}

#define RB_GAMMA UINT64_C(0x9e3779b97f4a7c15)

/* SplitMix64 finalizer (Vigna, public domain): a bijection on 2^64 with full avalanche. */
static inline uint64_t rb_mix64(uint64_t z) {
  z = (z ^ (z >> 30)) * UINT64_C(0xbf58476d1ce4e5b9);
  z = (z ^ (z >> 27)) * UINT64_C(0x94d049bb133111eb);
  return z ^ (z >> 31);
}

/* One equation of the ribbon system: row `start`, coefficient window `coeff` (bit k selects
 * row start + k, bit 0 always set), and r-bit fingerprint `fp`. docs/internals.md section 3.2. */
typedef struct {
  uint64_t start;
  uint64_t coeff;
  uint32_t fp;
} rb_eq;

/* Per-attempt salt: depends only on the attempt index, so it is computed once per build attempt / per filter. */
static inline uint64_t rb_attempt_salt(uint32_t attempt) { return rb_mix64(((uint64_t)attempt + 1u) * RB_GAMMA); }

/* Only the start row of rb_derive (one mix instead of three), for grouping keys before insertion. */
static inline uint64_t rb_derive_start(uint64_t hash, uint64_t salt, uint64_t num_starts) {
  return rb_mulhi64(rb_mix64((hash ^ salt) + RB_GAMMA), num_starts);
}

/* num_starts = num_rows - RB_WIDTH + 1; 1 <= r <= 32; salt = rb_attempt_salt(attempt). */
static inline rb_eq rb_derive(uint64_t hash, uint64_t salt, uint64_t num_starts, uint32_t r) {
  uint64_t state = hash ^ salt;
  uint64_t z0 = rb_mix64(state + RB_GAMMA);
  uint64_t z1 = rb_mix64(state + 2u * RB_GAMMA);
  uint64_t z2 = rb_mix64(state + 3u * RB_GAMMA);
  rb_eq eq;
  eq.start = rb_mulhi64(z0, num_starts); /* floor(z0 * num_starts / 2^64): uniform in [0, num_starts) */
  eq.coeff = z1 | 1u;                    /* the equation always involves its own start row */
  eq.fp = (uint32_t)(z2 >> (64u - r));   /* top r bits; r <= 32 so the shift is 32..63 */
  return eq;
}

/* XXH3-64 of a byte string (seed 0, default secret); used for key hashing and checksums. */
uint64_t rb_xxh3_64(const void *data, size_t len);

/* rb_build with the insertion order forced: bucket < 0 picks by table size (what rb_build does), 0 inserts keys in
 * arrival order, > 0 groups them by start row first. The serialized filter is the same in every mode; tests compare them. */
rb_status rb_build_ex(const uint64_t *key_hashes, size_t n, const rb_params *p, int bucket, rb_filter **out,
                      rb_build_info *info);

#endif /* RB_INTERNAL_H */
