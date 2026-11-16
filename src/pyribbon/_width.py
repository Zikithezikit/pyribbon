"""The ribbon widths a filter can be built with."""

from __future__ import annotations

from enum import IntEnum


class Width(IntEnum):
    """Ribbon width in rows, the ``width`` argument of ``RibbonFilter``.

    A wider ribbon needs less spare room in its table, so the filter is smaller, and it builds slower. The members are
    ints (``Width.W128 == 128``), and these two are the only values the filter accepts.
    """

    W64 = 64
    W128 = 128
