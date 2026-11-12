# Width study (w = 64 vs w = 128)

`sim_width.c` is a throwaway simulation of the banded GF(2) elimination from the Ribbon paper (Algorithm 1). For each
slot count `m` it inserts random equations until the first failure; `j` keys were added. A random key set of size `n`
builds iff `j >= n`, so the overhead for 95% per-attempt success is `m / q05(j) - 1`. It is not part of the library.

```
gcc -O2 -std=gnu11 -DNW=1 -o sim64  sim_width.c && ./sim64  7 22   # w = 64
gcc -O2 -std=gnu11 -DNW=2 -o sim128 sim_width.c && ./sim128 7 22   # w = 128
```

Outputs from the run used in DESIGN.md: `sim_width_w64.txt`, `sim_width_w128.txt` (Intel i7-7700, governor
`powersave`, gcc 15.2). The `ns/key` column times this naive generic code, not the library: treat it as a rough ratio.
