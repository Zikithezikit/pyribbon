"""Build a filter, ask it about some keys, and look at its size.

Run it with: python examples/01_quickstart.py
"""

from pyribbon import RibbonFilter

users = ["alice", "bob", "carol"]
f = RibbonFilter(users, fp_bits=12)  # a wrong "yes" happens about once in 2**12 lookups

print("alice" in f)  # True: a member is always found
print("mallory" in f)  # False: this non-member was rejected (a false positive has probability about 2**-12)
print(f.contains_many(["alice", "mallory"]))  # one answer per key

# Three keys are padded to the minimum size of 128 rows, which is why bits_per_key looks huge here.
print(len(f), f.size_in_bytes, round(f.bits_per_key))
