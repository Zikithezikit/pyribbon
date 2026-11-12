"""Measure the false-positive rate for a few values of fp_bits.

The rate you get is about 2**-fp_bits, and every extra bit costs a little over one extra bit per key. Run it with:
python examples/03_choosing_fp_bits.py
"""

import array

from pyribbon import RibbonFilter

N = 100_000
PROBES = 4_000_000  # keys that are not in the set, so every "yes" is a false positive
members = array.array("q", range(N))
strangers = array.array("q", range(N, N + PROBES))

print(f"{N:,} keys, {PROBES:,} lookups of keys that are not in the set")
print(f"{'fp_bits':>7} {'designed':>10} {'measured':>10} {'bits/key':>9} {'Bloom bits/key':>15}")
for fp_bits in (4, 8, 12, 16):
    f = RibbonFilter(members, fp_bits=fp_bits)
    chunk = 1_000_000
    false_positives = sum(sum(f.contains_many(strangers[i : i + chunk])) for i in range(0, PROBES, chunk))
    designed = 2.0**-fp_bits
    print(
        f"{fp_bits:>7} {designed:>10.2e} {false_positives / PROBES:>10.2e} {f.bits_per_key:>9.2f} {1.44 * fp_bits:>15.2f}"
    )
