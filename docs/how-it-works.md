# How it works


Each key becomes one linear equation over GF(2) with a window of 64 consecutive unknowns. The unknowns are `r`-bit rows,
chosen so that every key's equation holds. A query XORs the rows its equation selects and compares the result with the
key's `r`-bit fingerprint. Building is banded Gaussian elimination. If a random key set happens to be unsolvable (a few
percent of attempts at the default size), the build retries with a new seed.

The design is the standard Ribbon filter of Dillinger and Walzer, "Ribbon filter: practically smaller than Bloom and Xor"
(arXiv:2103.02515), with width 64 and the interleaved column layout. [RESEARCH.md](../RESEARCH.md) has the literature survey and
[DESIGN.md](../DESIGN.md) the decisions, formats and measurements behind this implementation. The C core builds and tests without
Python (`make -C core test`).
