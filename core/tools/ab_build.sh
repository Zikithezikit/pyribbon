#!/bin/sh
# Interleaved A/B timing of two builds of the core: tools/ab_build.sh OLD_BIN NEW_BIN [rounds] [bench_build args]
# OLD_BIN and NEW_BIN are bench_build binaries made from two source trees (make bench-build in each). Each round runs
# A, then B, one n and r at a time, pinned to one CPU, so slow phases of a shared machine hit both. Prints, for every
# (n, r), the median over rounds of each side's median ns/key, the spread of those per-round medians, and the ratio.
set -eu
A=$1; B=$2; shift 2
ROUNDS=${1:-5}
[ $# -gt 0 ] && shift
CPU=${BENCH_CPU:-2}
PIN=""
command -v taskset >/dev/null 2>&1 && PIN="taskset -c $CPU"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
r=1
while [ "$r" -le "$ROUNDS" ]; do
  $PIN "$A" "$@" > "$TMP/a.$r"
  $PIN "$B" "$@" > "$TMP/b.$r"
  r=$((r + 1))
done
python3 - "$TMP" "$ROUNDS" <<'PY'
import sys, statistics as st
d, rounds = sys.argv[1], int(sys.argv[2])
def load(side):
    out = {}
    for r in range(1, rounds + 1):
        for line in open(f"{d}/{side}.{r}").read().splitlines()[1:]:
            f = line.split()
            out.setdefault((int(f[0]), int(f[1])), []).append((float(f[2]), f[6]))
    return out
a, b = load("a"), load("b")
print(f"{'n':>10} {'r':>3} {'old':>7} {'old range':>13} {'new':>7} {'new range':>13} {'new/old':>8}  same bytes")
for k in sorted(a):
    ma, mb = [x[0] for x in a[k]], [x[0] for x in b[k]]
    same = {x[1] for x in a[k]} == {x[1] for x in b[k]} and len({x[1] for x in a[k]}) == 1
    print(f"{k[0]:>10} {k[1]:>3} {st.median(ma):7.1f} {min(ma):6.1f}-{max(ma):<6.1f} {st.median(mb):7.1f} {min(mb):6.1f}-{max(mb):<6.1f} {st.median(mb)/st.median(ma):8.3f}  {'yes' if same else 'NO'}")
PY
