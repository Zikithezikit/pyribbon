"""Query many keys at once, from a list or from a numeric array.

An integer array (array.array, numpy) is hashed in C, so it is the fastest way to feed a large batch. The answers are
exactly the ones you get from the same ints in a list. Run it with: python examples/05_batches_and_arrays.py
"""

import array

from pyribbon import RibbonFilter

ids = array.array("q", range(1_000_000))
f = RibbonFilter(ids, fp_bits=16)  # building from an array works too

wanted = [5, 999_999, 10**9, -1]
print(f.contains_many(wanted))  # [True, True, False, False]
print(f.contains_many(array.array("q", wanted)) == f.contains_many(wanted))  # True

try:
    import numpy as np
except ImportError:
    print("numpy is not installed; skipping the numpy part")
else:
    batch = np.arange(999_990, 1_000_010, dtype="int64")
    answers = f.contains_many(batch)
    print(sum(answers), "of", len(answers), "found")  # 10 of 20 found (the last ten are not in the set)
