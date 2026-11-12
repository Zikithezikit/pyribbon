"""Which keys a filter accepts, and how they are told apart.

Run it with: python examples/02_key_types.py
"""

from pyribbon import RibbonFilter

# bytes, bytearray and memoryview are hashed by content, str as UTF-8, int by value (any size, negatives too).
f = RibbonFilter([b"abc", "abc", 97, -5, 2**100, "héllo"], fp_bits=32)

print(bytearray(b"abc") in f)  # True: same bytes as b"abc"
print(memoryview(b"abc") in f)  # True
print(97 in f, -5 in f, 2**100 in f)  # True True True

# b"a", "a" and 97 are three different keys. With fp_bits=32 a false positive is vanishingly unlikely,
# so these checks are reliable.
g = RibbonFilter(["a"], fp_bits=32)
print(b"a" in g, 97 in g)  # False False

# Anything else is refused instead of being guessed at: there is no implicit str() or repr().
for bad_key in (1.5, None, (1, 2)):
    try:
        print(bad_key in f)
    except TypeError as error:
        print(error)

# A lone str or bytes is a mistake: iterating it would build a filter of single characters or numbers.
try:
    RibbonFilter("alice")
except TypeError as error:
    print(error)
