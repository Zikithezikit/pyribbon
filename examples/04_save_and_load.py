"""Save a filter to a file and query it again without copying it into memory.

Run it with: python examples/04_save_and_load.py
"""

import mmap
import os
import tempfile

from pyribbon import FormatError, RibbonFilter

f = RibbonFilter(range(100_000), fp_bits=10)

with tempfile.TemporaryDirectory() as folder:
    path = os.path.join(folder, "ids.ribbon")
    with open(path, "wb") as fh:
        fh.write(f.to_bytes())
    print(f"wrote {os.path.getsize(path):,} bytes")

    # Loading checks the header and the checksum once; after that the file's pages are queried where they are.
    with open(path, "rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
        g = RibbonFilter.from_buffer(mm)
        print(12_345 in g, len(g), g.fp_bits)  # True 100000 10
        del g  # release the buffer before the map is closed

        # verify=False skips the payload checksum, which would read the whole file. The header is still checked.
        h = RibbonFilter.from_buffer(mm, verify=False)
        print(99_999 in h)  # True
        del h

    # A damaged file is refused, never half-read.
    with open(path, "rb") as fh:
        data = bytearray(fh.read())
    data[-1] ^= 0x01
    try:
        RibbonFilter.from_buffer(bytes(data))
    except FormatError as error:
        print(error)  # invalid pyribbon data: checksum mismatch
