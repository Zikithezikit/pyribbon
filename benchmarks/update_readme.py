"""Copy benchmark results into README.md between marker comments, generated from docs/benchmark.md and benchmark.json.

Usage: ``python benchmarks/update_readme.py`` (run by hand after ``make bench``; tests/test_readme.py checks the result).
Blocks: ``bench`` (the wins-and-loses table, copied verbatim from the markdown report) and ``bench-by-size`` (space, build
and query tables built from the JSON). No benchmark number in the README is typed by hand.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HEADING = "## Where pyribbon wins and loses"
ROOT = Path(__file__).resolve().parent.parent


def markers(name: str) -> tuple[str, str]:
    """Return the start and end marker comments of a README block."""
    return f"<!-- {name}:start -->", f"<!-- {name}:end -->"


def benchmark_block(markdown: str) -> str:
    """Return the "wins and loses" section of a benchmark report as a README block (heading as an italic caption)."""
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(HEADING))
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = "\n".join(lines[start + 1 : end]).strip("\n")
    return f"*{lines[start].removeprefix('## ')}:*\n\n{body}"


def _table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---:"] * len(headers)) + "|"]
    return "\n".join(out + ["| " + " | ".join(r) + " |" for r in rows])


def by_size_block(data: dict[str, Any]) -> str:
    """Build the by-size tables (int keys, 8-bit class) from ``benchmark.json``."""
    cells = [c for c in data["results"] if c["regime"] == "int"]
    space, build, query = [], [], []
    for c in cells:
        n, f = c["n"], c["filters"]
        pyr, xor, fuse, bloom = f["pyribbon8"], f["xor8"], f["fuse8"], f["rbloom8"]
        core = c["diag"]["pyfusefilter"]["core_build"]["fuse8"]["median"]
        space.append(
            [f"{n:,}"] + [f"{x['bits_per_key']:.2f}" for x in (pyr, xor, fuse, bloom)]
            + [f"{100 * (pyr['bits_per_key'] / fuse['bits_per_key'] - 1):+.1f}%"]
        )  # fmt: skip
        build.append(
            [f"{n:,}", f"{pyr['build_ns']['median'] / n:.0f}", f"{fuse['build_ns']['median'] / n:.0f}", f"{core:.0f}"]
        )
        batch_array = pyr.get("batch_array_kps", pyr["batch_kps"])["mixed"]["median"] / 1e6
        query.append(
            [
                f"{n:,}",
                f"{pyr['lat_member_ns']['median']:.0f} / {pyr['lat_non_member_ns']['median']:.0f}",
                f"{fuse['lat_member_ns']['median']:.0f} / {fuse['lat_non_member_ns']['median']:.0f}",
                f"{pyr['batch_kps']['mixed']['median'] / 1e6:.1f}",
                f"{batch_array:.1f}",
            ]
        )
    return "\n\n".join(
        [
            "*Space, 8-bit class (bits per key including the 64-byte header; last column: pyribbon relative to Fuse8):*",
            _table(["n", "pyribbon", "Xor8", "Fuse8", "rbloom 2^-8", "pyribbon vs Fuse8"], space),
            "*Build time (ns per key). `pyfusefilter` as shipped hashes every key in Python; the last column is its bare C "
            "core on pre-hashed keys, which is what a C-to-C comparison would use:*",
            _table(["n", "pyribbon (Python keys)", "Fuse8 as shipped", "Fuse8 C core only"], build),
            "*Query: `key in f` in ns (member / non-member) and `contains_many` throughput (million keys per second, 50/50 mix, "
            "from a list and from an `array('q')`):*",
            _table(["n", "pyribbon `in`", "Fuse8 `in`", "pyribbon batch (list)", "pyribbon batch (array)"], query),
        ]
    )


def replace_block(readme: str, name: str, text: str) -> str:
    """Return ``readme`` with the text between the ``name`` markers replaced."""
    start, end = markers(name)
    head, rest = readme.split(start, 1)
    return f"{head}{start}\n{text}\n{end}{rest.split(end, 1)[1]}"


def read_block(readme: str, name: str) -> str:
    """Return the text between the ``name`` markers of a README."""
    start, end = markers(name)
    return readme.split(start, 1)[1].split(end, 1)[0].strip("\n")


def main() -> None:
    """Rewrite the generated blocks of README.md from docs/."""
    readme = (ROOT / "README.md").read_text()
    readme = replace_block(readme, "bench", benchmark_block((ROOT / "docs" / "benchmark.md").read_text()))
    readme = replace_block(
        readme, "bench-by-size", by_size_block(json.loads((ROOT / "docs" / "benchmark.json").read_text()))
    )
    (ROOT / "README.md").write_text(readme)
    print("README.md updated from docs/benchmark.md and docs/benchmark.json")


if __name__ == "__main__":
    main()
