"""Query one filter from several threads at once.

A filter never changes after it is built, so sharing it between threads needs no lock. Large batches also release the
GIL, so the threads really do run in parallel. Run it with: python examples/07_threads.py
"""

import array
from concurrent.futures import ThreadPoolExecutor

from pyribbon import RibbonFilter

f = RibbonFilter(range(200_000), fp_bits=16)
probes = array.array("q", range(100_000, 500_000))  # half are members, half are not


def count_hits(start: int) -> int:
    """Count the "yes" answers for one slice of the probes."""
    return sum(f.contains_many(probes[start : start + 50_000]))


starts = range(0, len(probes), 50_000)
with ThreadPoolExecutor(max_workers=8) as pool:
    from_threads = sum(pool.map(count_hits, starts))
alone = sum(count_hits(start) for start in starts)
print(from_threads, alone, from_threads == alone)  # the two counts are identical
