# Vendored code

`xxhash.h`: xxHash v0.8.4 (https://github.com/Cyan4973/xxHash, tag `v0.8.4`, commit `c87183a77d`), copied unmodified.
SHA-256 `3dc8d161e867a62d3417f7885b55fdaded8b7b497e2f165d05c94f4fe24f2ca4`. Library licence: BSD 2-Clause, see
`LICENSES/xxhash-BSD-2-Clause.txt` (shipped in the sdist and wheels). Used only for `XXH3_64bits` (seed 0, default
secret) and the two format checksums; see `core/src/rb_hash.c` for the configuration macros.
