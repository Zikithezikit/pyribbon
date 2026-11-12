"""Turn `make calibrate` output into the default-overhead table (C array, Python mirror, documentation table).

Usage: python overhead_table.py CALIBRATE_OUTPUT [QUANTILE_COLUMN]

Input rows are `k m trials f50 f05 f03 f01 ...` for slot counts m = 2**k, where fQQ is the fill j/m reached by the
QQ-th percentile of random trials (a random key set of n keys builds in one attempt iff n <= j). The default target is
the 3rd percentile column (f03): about 97% of attempts succeed, so the expected number of attempts is about 1.03.
For each n = 2**k the table gives eps(n) = m / n - 1 with m solving m * f(m) = n (f interpolated in log2 m).
"""

from __future__ import annotations

import math
import sys


def load(path: str, column: str) -> dict[int, float]:
    col = {"f50": 3, "f05": 4, "f03": 5, "f01": 6}[column]
    fills: dict[int, float] = {}
    for line in open(path):
        parts = line.split()
        if len(parts) >= 7 and parts[0].isdigit():
            fills[int(parts[0])] = float(parts[col])
    return fills


def fill_at(fills: dict[int, float], log2m: float) -> float:
    ks = sorted(fills)
    if log2m <= ks[0]:
        return fills[ks[0]]
    if log2m >= ks[-1]:
        return fills[ks[-1]]
    lo = math.floor(log2m)
    frac = log2m - lo
    return fills[lo] + frac * (fills[lo + 1] - fills[lo])


def main() -> None:
    path = sys.argv[1]
    column = sys.argv[2] if len(sys.argv) > 2 else "f03"
    fills = load(path, column)
    ks = sorted(fills)
    table: dict[int, float] = {}
    for k in range(ks[0], ks[-1] + 1):
        n = 2.0**k
        m = n / fills[k]
        for _ in range(30):  # fixed point of m = n / f(m)
            m = n / fill_at(fills, math.log2(m))
        table[k] = m / n - 1.0
    # enforce monotone non-decreasing from k = 10 (small-k noise is real but a rising table is what the code assumes)
    for k in range(11, ks[-1] + 1):
        table[k] = max(table[k], table[k - 1])
    slope = (table[ks[-1]] - table[ks[-1] - 3]) / 3.0
    print(f"# column {column}; k = {ks[0]}..{ks[-1]}; slope over the last 3 octaves {100 * slope:.2f} pp/doubling")
    values = [round(table[k] + 0.0005, 3) for k in range(ks[0], ks[-1] + 1)]  # round up to 0.1 pp
    print("C:      " + ", ".join(f"{v:.3f}" for v in values))
    print("Python: [" + ", ".join(f"{v:.3f}" for v in values) + "]")
    print(f"RB_OVERHEAD_SLOPE (rounded up): {math.ceil(slope * 1000) / 1000:.3f}")
    print("\n| n = 2^k | " + " | ".join(str(k) for k in range(ks[0], ks[-1] + 1)) + " |")
    print("|---|" + "---|" * (ks[-1] - ks[0] + 1))
    print("| overhead | " + " | ".join(f"{100 * v:.1f}%" for v in values) + " |")


if __name__ == "__main__":
    main()
