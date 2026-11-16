# Limits


* A filter is static: nothing can be inserted or deleted after the build. Duplicate keys are harmless and counted by
  `len()`.
* It uses about `1.12 * fp_bits` bits per key at a million keys, against `1.44 * fp_bits` for Bloom filters. With width 64
  the overhead grows with the logarithm of the set size, so binary-fuse filters are smaller from about a million keys up
  (see [performance](performance.md)). `width=128` saves 4% to 8% of the space (about `1.05 * fp_bits` bits per key at a million
  keys), builds 1.2 to 1.5 times slower and queries slower. Sharding would flatten the growth further and is on the roadmap.
* Small sets are padded. The minimum is 128 rows (256 at width 128): 128 bytes plus a 64-byte header at `fp_bits=8`. Use a
  plain `set` for a few dozen keys.
* The build uses about 26 bytes per key temporarily (an array of hashes and the elimination state), about 33 at width 128. Its elimination is
  also slower than the bare C core of the fuse filters (see the build table in [performance](performance.md)).
* Hashes are 64-bit, so two distinct keys with the same hash are indistinguishable (probability about `n**2 / 2**65`).
* The timings here were measured on one Linux x86-64 machine. CI builds wheels and runs the tests on Linux (x86-64 and
  ARM, manylinux and musllinux), macOS (Intel and Apple silicon) and Windows (MSVC, x64) for Python 3.10 and newer.
  The C core tests and the fast Python tests also run on s390x (64-bit, big-endian), 32-bit x86 and armv7 in Debian
  containers (s390x and armv7 under QEMU emulation, so those runs say nothing about speed). CI also runs the fast tests on
  free-threaded 3.14t with the GIL forced off.
