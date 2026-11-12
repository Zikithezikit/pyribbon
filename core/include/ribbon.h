/*
 * ribbon.h - public C API of the pyribbon core: a static approximate-membership
 * ("ribbon") filter. Standard ribbon, width w = 64, interleaved column layout.
 *
 * Algorithm: P. C. Dillinger and S. Walzer, "Ribbon filter: practically smaller than
 * Bloom and Xor", arXiv:2103.02515 (cited as [R] in the sources). Design and format:
 * DESIGN.md. No false negatives; false-positive rate 2^-fp_bits.
 *
 * Thread safety: an rb_filter is immutable after rb_build / rb_from_buffer returns, so
 * any number of threads may query it concurrently. There is no global state. Freeing a
 * filter while another thread still queries it is a data race, as for any C object.
 */
#ifndef RIBBON_H
#define RIBBON_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RB_FORMAT_VERSION 1
#define RB_HEADER_SIZE 64u
#define RB_WIDTH 64u              /* ribbon width w, in rows */
#define RB_MIN_FP_BITS 1u
#define RB_MAX_FP_BITS 32u
#define RB_DEFAULT_FP_BITS 8u
#define RB_DEFAULT_MAX_ATTEMPTS 32u
#define RB_MAX_ATTEMPTS 255u
#define RB_MAX_ROWS (UINT64_C(1) << 40)
#define RB_MAX_KEYS (UINT64_C(1) << 38)

typedef struct rb_filter rb_filter; /* opaque */

typedef enum {
  RB_OK = 0,
  RB_E_INVALID_ARG, /* null pointer, parameter out of range */
  RB_E_NOMEM,
  RB_E_CONSTRUCT,   /* every construction attempt failed */
  RB_E_TOO_LARGE,   /* size computation would exceed the supported range */
  RB_E_TRUNCATED,   /* buffer shorter than the header or the declared payload */
  RB_E_MAGIC,
  RB_E_VERSION,
  RB_E_FORMAT,      /* inconsistent or unsupported header field, trailing bytes */
  RB_E_CHECKSUM
} rb_status;

/* Key kinds for rb_hash_bytes; integers in [-2^63, 2^63) use rb_hash_i64. */
typedef enum { RB_KEY_BYTES = 0, RB_KEY_STR = 1, RB_KEY_BIGINT = 2 } rb_key_kind;

typedef struct {
  uint32_t fp_bits;      /* 1..32; false-positive rate is about 2^-fp_bits */
  uint32_t max_attempts; /* 1..255; 0 selects RB_DEFAULT_MAX_ATTEMPTS */
  double overhead;       /* extra rows as a fraction of n; negative selects rb_default_overhead(n) */
  uint64_t seed;         /* mixed into every key hash; stored in the filter */
} rb_params;

typedef struct {
  uint32_t attempts; /* attempts used, including the successful one */
  uint64_t num_rows;
} rb_build_info;

/* Parameters with every field at its default. */
rb_params rb_params_default(void);

/* Short constant string for a status code. */
const char *rb_strerror(rb_status status);

/* Key hashing (hash id 1, DESIGN.md section 3.1). The result is the 64-bit master hash
 * that rb_build / rb_contains consume. The seed must equal the one given to rb_build. */
uint64_t rb_hash_bytes(const void *data, size_t len, uint64_t seed, rb_key_kind kind);
uint64_t rb_hash_i64(int64_t value, uint64_t seed);

/* Overhead (extra rows / n) used when params.overhead < 0. */
double rb_default_overhead(uint64_t n);

/* Build a filter from n master hashes (duplicates are allowed and harmless). On failure
 * *out is NULL. `params` may be NULL for defaults; `info` may be NULL. */
rb_status rb_build(const uint64_t *hashes, size_t n, const rb_params *params, rb_filter **out, rb_build_info *info);

/* View a serialized filter without copying. `buf` must stay valid and unmodified for the
 * lifetime of the filter. The header is validated against `len` in O(1); the payload
 * checksum (which reads every byte) is checked only when `verify_payload` is non-zero.
 * Serialized input is untrusted: this never reads outside [buf, buf+len). */
rb_status rb_from_buffer(const void *buf, size_t len, int verify_payload, rb_filter **out);

void rb_free(rb_filter *filter); /* accepts NULL */

/* Membership test for a master hash: 1 = possibly present, 0 = definitely absent. */
int rb_contains(const rb_filter *filter, uint64_t hash);
void rb_contains_many(const rb_filter *filter, const uint64_t *hashes, size_t n, uint8_t *out);

size_t rb_serialized_size(const rb_filter *filter);
rb_status rb_serialize(const rb_filter *filter, void *dst, size_t capacity);

uint64_t rb_num_keys(const rb_filter *filter); /* keys supplied to rb_build, duplicates included */
uint64_t rb_num_rows(const rb_filter *filter);
uint32_t rb_fp_bits(const rb_filter *filter);
uint64_t rb_seed(const rb_filter *filter);

#ifdef __cplusplus
}
#endif

#endif /* RIBBON_H */
