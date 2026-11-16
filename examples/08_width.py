"""Build the same keys at both ribbon widths and compare the size and the build time.

Width 128 needs less spare room in its table, so the filter is smaller, and it takes longer to build. Queries cost about the
same. The width is saved with the filter. Run it with: python examples/08_width.py
"""

import array
import time

from pyribbon import RibbonFilter, Width

print(f"{'keys':>9} {'width':>5} {'bits/key':>9} {'build s':>8}")
for n in (10_000, 100_000, 1_000_000):
    keys = array.array("q", range(n))
    for width in Width:
        start = time.perf_counter()
        f = RibbonFilter(keys, width=width)
        elapsed = time.perf_counter() - start
        print(f"{n:>9,} {width.value:>5} {f.bits_per_key:>9.2f} {elapsed:>8.3f}")

print(RibbonFilter.from_buffer(f.to_bytes()).width.name)  # the last filter is width 128, and loading keeps it
