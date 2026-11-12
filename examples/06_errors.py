"""The errors you can get, and what each one means.

Run it with: python examples/06_errors.py
"""

from pyribbon import ConstructionError, FormatError, RibbonError, RibbonFilter

# A build can fail when the table is too small for the keys. The default size makes that rare, and a failed attempt is
# retried with a new seed. Asking for no extra room and a single attempt makes the failure certain here.
try:
    RibbonFilter(range(100_000), overhead=0.0, max_attempts=1)
except ConstructionError as error:
    print("ConstructionError:", error)

# Serialized data that is too short, damaged or not a filter at all raises FormatError (also a ValueError).
good = RibbonFilter(range(1_000)).to_bytes()
for name, data in (("truncated", good[:-1]), ("garbage", b"definitely not a filter " * 4), ("empty", b"")):
    try:
        RibbonFilter.from_buffer(data)
    except FormatError as error:
        print(f"FormatError ({name}):", error)

# Both errors share a base class, so one except clause can catch either.
try:
    RibbonFilter.from_buffer(b"x" * 100)
except RibbonError as error:
    print(type(error).__name__)

# Wrong arguments are ordinary ValueError and TypeError.
for make in (lambda: RibbonFilter([1], fp_bits=0), lambda: RibbonFilter([1.5])):
    try:
        make()
    except (ValueError, TypeError) as error:
        print(type(error).__name__ + ":", error)
