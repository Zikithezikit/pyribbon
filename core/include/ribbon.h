/*
 * ribbon.h - public C API of the pyribbon core: a static approximate-membership
 * ("ribbon") filter. Standard ribbon, width w = 64, interleaved column layout.
 *
 * Algorithm: P. C. Dillinger and S. Walzer, "Ribbon filter: practically smaller than
 * Bloom and Xor", arXiv:2103.02515 (cited as [R] in the sources). Design and format:
 * docs/internals.md. No false negatives; false-positive rate 2^-fp_bits.
 *
 * Thread safety: an rb_filter is immutable after rb_build / rb_from_buffer returns, so
 * any number of threads may query it concurrently. There is no global state, so separate
 * calls to rb_build, rb_serialize and the hash functions may also run in parallel. Freeing a
 * filter while another thread still queries it is a data race, as for any C object, and so is
 * writing to a buffer that a filter from rb_from_buffer views.
 */
#ifndef RIBBON_H
#define RIBBON_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

#define RB_FORMAT_VERSION 1
#define RB_HEADER_SIZE 64u        /* bytes before the payload in the serialized form */
#define RB_WIDTH 64u              /* ribbon width w, in rows */
#define RB_MIN_FP_BITS 1u
#define RB_MAX_FP_BITS 32u
#define RB_DEFAULT_FP_BITS 8u
#define RB_DEFAULT_MAX_ATTEMPTS 32u
#define RB_MAX_ATTEMPTS 255u
#define RB_MAX_ROWS (UINT64_C(1) << 40) /* largest num_rows a loader accepts */
#define RB_MAX_KEYS (UINT64_C(1) << 38) /* rb_build rejects more keys than this with RB_E_TOO_LARGE */

typedef struct rb_filter rb_filter; /* opaque */

typedef enum {
  RB_OK = 0,
  RB_E_INVALID_ARG, /* null pointer, parameter out of range, destination buffer too small */
  RB_E_NOMEM,       /* an allocation failed */
  RB_E_CONSTRUCT,   /* every construction attempt failed */
  RB_E_TOO_LARGE,   /* more than RB_MAX_KEYS keys, or a size computation would exceed the supported range */
  RB_E_TRUNCATED,   /* buffer shorter than the header or the declared payload */
  RB_E_MAGIC,       /* the first 8 bytes are not the magic number */
  RB_E_VERSION,     /* format version other than RB_FORMAT_VERSION */
  RB_E_FORMAT,      /* inconsistent or unsupported header field, trailing bytes */
  RB_E_CHECKSUM     /* header checksum mismatch, or payload checksum mismatch when it was requested */
} rb_status;

/* Key kinds for rb_hash_bytes. The kind is part of the hash, so the same bytes hashed as RB_KEY_BYTES, RB_KEY_STR
 * and RB_KEY_BIGINT are three different keys. Integers in [-2^63, 2^63) use rb_hash_i64. For an integer outside
 * that range, pass its little-endian two's complement bytes (docs/internals.md section 3.1) with RB_KEY_BIGINT. */
typedef enum { RB_KEY_BYTES = 0, RB_KEY_STR = 1, RB_KEY_BIGINT = 2 } rb_key_kind;

typedef struct {
  uint32_t fp_bits;      /* 1..32; false-positive rate is about 2^-fp_bits */
  uint32_t max_attempts; /* 1..255; 0 selects RB_DEFAULT_MAX_ATTEMPTS */
  double overhead;       /* extra rows as a fraction of n, at most 4; negative selects rb_default_overhead(n) */
  uint64_t seed;         /* stored in the filter; the keys must have been hashed with this same seed */
} rb_params;

typedef struct {
  uint32_t attempts; /* attempts used, including the successful one; 0 for an empty filter */
  uint64_t num_rows; /* rows in the table; 0 for an empty filter */
} rb_build_info;

/* Parameters with every field at its default. */
rb_params rb_params_default(void);

/* Short description of a status code. The string is static and never NULL ("unknown status" for a value that is not
 * an rb_status), so the caller must not free or modify it. */
const char *rb_strerror(rb_status status);

/* Key hashing (hash id 1, docs/internals.md section 3.1). The result is the 64-bit master hash
 * that rb_build / rb_contains consume. The seed must equal the one given to rb_build.
 * `data` may be NULL when `len` is 0. Pure functions: no allocation, no failure. */
uint64_t rb_hash_bytes(const void *data, size_t len, uint64_t seed, rb_key_kind kind);
uint64_t rb_hash_i64(int64_t value, uint64_t seed);

/* Overhead (extra rows / n) used when params.overhead < 0, before the row count is rounded up to a multiple of 64
 * (minimum 128 rows). */
double rb_default_overhead(uint64_t n);

/* Build a filter from n master hashes (duplicates are allowed and harmless). `hashes` is only read during the call
 * and may be NULL when n is 0, which gives a valid empty filter that contains nothing. `params` may be NULL for
 * defaults; `info` may be NULL and is written only on success. On success *out is a filter that owns its memory: release it with rb_free. On failure
 * *out is NULL and the status is RB_E_INVALID_ARG (bad parameter, NULL `out`, NULL `hashes` with n > 0),
 * RB_E_TOO_LARGE, RB_E_NOMEM or RB_E_CONSTRUCT. Temporary memory during the call: 16 bytes per row. */
rb_status rb_build(const uint64_t *hashes, size_t n, const rb_params *params, rb_filter **out, rb_build_info *info);

/* View a serialized filter without copying. `buf` must stay valid and unmodified until rb_free(filter) has
 * returned; rb_free never frees `buf`. `len` must be exactly the serialized size: a longer buffer fails with
 * RB_E_FORMAT, so pass a slice when the filter is embedded in something larger. `buf` needs no particular
 * alignment. The header is validated against `len` in O(1); the payload checksum (which reads every byte) is checked
 * only when `verify_payload` is non-zero. Without it a damaged payload loads and can only change query answers.
 * Serialized input is untrusted: this never reads outside [buf, buf+len). On failure *out is NULL. */
rb_status rb_from_buffer(const void *buf, size_t len, int verify_payload, rb_filter **out);

/* Release a filter from rb_build or rb_from_buffer; accepts NULL. For a filter from rb_from_buffer this frees only the
 * small handle, never the buffer it views. */
void rb_free(rb_filter *filter);

/* Membership test for a master hash, which must be made with the filter's seed: 1 = possibly present, 0 = definitely
 * absent. Never allocates and cannot fail. `filter` must not be NULL. */
int rb_contains(const rb_filter *filter, uint64_t hash);

/* rb_contains for n hashes: out[i] is 0 or 1 for hashes[i]. `out` must have room for n bytes. Gives the same answers as a
 * loop of rb_contains, faster for large n. */
void rb_contains_many(const rb_filter *filter, const uint64_t *hashes, size_t n, uint8_t *out);

/* Exact length in bytes of the serialized filter: RB_HEADER_SIZE plus the payload. */
size_t rb_serialized_size(const rb_filter *filter);

/* Write the serialized filter (docs/internals.md section 5) to `dst`. `capacity` must be at least rb_serialized_size(filter),
 * otherwise nothing is written and the status is RB_E_INVALID_ARG (also for a NULL `dst`). Writes exactly
 * rb_serialized_size(filter) bytes; `dst` needs no particular alignment. The bytes depend only on the hashes (in the order
 * given) and the parameters, not on the platform. */
rb_status rb_serialize(const rb_filter *filter, void *dst, size_t capacity);

uint64_t rb_num_keys(const rb_filter *filter); /* keys supplied to rb_build, duplicates included */
uint64_t rb_num_rows(const rb_filter *filter); /* rows in the table; 0 for an empty filter */
uint32_t rb_fp_bits(const rb_filter *filter);
uint64_t rb_seed(const rb_filter *filter);

#ifdef __cplusplus
}
#endif

#endif /* RIBBON_H */
