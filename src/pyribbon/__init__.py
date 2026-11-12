"""Ribbon filters for Python.

A ribbon filter is a static approximate-membership structure: ``key in filter`` never gives a false negative and
gives a false positive with probability about ``2**-fp_bits``. The core is written in C; see ``DESIGN.md``.

Example:
    >>> from pyribbon import RibbonFilter
    >>> f = RibbonFilter(["alice", "bob"], fp_bits=12)
    >>> "alice" in f
    True
"""

from __future__ import annotations

from pyribbon._ribbon import ConstructionError, FormatError, RibbonError, RibbonFilter

__version__ = "0.1.0"

#: Types accepted as keys: bytes-like and ``str`` keys are hashed by content, ``int`` by value.
Key = bytes | bytearray | memoryview | str | int

__all__ = ["ConstructionError", "FormatError", "Key", "RibbonError", "RibbonFilter", "__version__"]
