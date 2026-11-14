# Width study (w = 64 vs w = 128)

`sim_width.c` is a throwaway simulation of the banded GF(2) elimination from the Ribbon paper (Algorithm 1). For each
slot count `m` it inserts random equations until the first one fails, and `j` is the number of keys added by then. A
random key set of size `n` builds if and only if `j >= n`, so the overhead for 95% per-attempt success is
`m / q05(j) - 1`. The simulation is not part of the library.

```
gcc -O2 -std=gnu11 -DNW=1 -o sim64  sim_width.c && ./sim64  7 22   # w = 64
gcc -O2 -std=gnu11 -DNW=2 -o sim128 sim_width.c && ./sim128 7 22   # w = 128
```

`sim_width_w64.txt` and `sim_width_w128.txt` hold the output of the run used in docs/internals.md (Intel i7-7700, governor
`powersave`, gcc 15.2). The `ns/key` column times this naive generic code, not the library, so treat it as a rough ratio.
