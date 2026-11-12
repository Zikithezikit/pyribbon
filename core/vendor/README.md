# Vendored code

`xxhash.h` is xxHash v0.8.4 (https://github.com/Cyan4973/xxHash, tag `v0.8.4`, commit `c87183a77d`), copied unmodified.
Its SHA-256 is `3dc8d161e867a62d3417f7885b55fdaded8b7b497e2f165d05c94f4fe24f2ca4`. The library is BSD 2-Clause licensed;
see `LICENSES/xxhash-BSD-2-Clause.txt` (shipped in the sdist and wheels). pyribbon uses it only for `XXH3_64bits` (seed 0,
default secret) and the two format checksums. The configuration macros are in `core/src/rb_hash.c`.
