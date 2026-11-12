"""Render the JSON written by ``PYRIBBON_STATS_OUT=... pytest -m slow tests/test_statistics.py`` as markdown.

Usage: ``python benchmarks/render_measurements.py docs/measurements.json docs/measurements.md``
"""

from __future__ import annotations

import datetime
import json
import platform
import sys
from pathlib import Path
from typing import Any

import pyribbon


def cpu_model() -> str:
    """CPU model string (Linux), falling back to ``platform.processor()``."""
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    return platform.processor() or "unknown"


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """GitHub-flavoured markdown table lines."""
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return out


def render(data: dict[str, list[dict[str, Any]]]) -> str:
    """Return the markdown report for the statistics rows in ``data``."""
    fpr = data.get("fpr", [])
    worst = max(fpr, key=lambda r: abs(r["z"])) if fpr else None
    out = [
        "# pyribbon measurements",
        "",
        f"Generated {datetime.date.today().isoformat()} by `make stats` (`tests/test_statistics.py`, marked `slow`) on "
        f"{cpu_model()}, CPython {platform.python_version()}, pyribbon {pyribbon.__version__}. "
        "Every row is a measurement; tolerances are 5 sigma of the exact binomial.",
        "",
        "## False-positive rate vs 2^-fp_bits",
        "",
        "Members are ints `[0, n)`; negatives are disjoint ints, `str` keys and `bytes` keys (one row per family). "
        "`z = (FP - expected) / sigma`.",
        "",
    ]
    if worst:
        out += [
            f"{len(fpr)} cases, worst |z| = {abs(worst['z']):.2f} (r={worst['r']}, n={worst['n']:,}, {worst['family']}).",
            "",
        ]
    out += table(
        ["fp_bits r", "n", "negatives", "probes", "false positives", "measured rate", "2^-r", "z"],
        [
            [
                str(r["r"]),
                f"{r['n']:,}",
                r["family"],
                f"{r['probes']:,}",
                f"{r['fp']:,}",
                f"{r['rate']:.4g}",
                f"{r['p']:.4g}",
                f"{r['z']:+.2f}",
            ]
            for r in fpr
        ],
    )
    out += [
        "",
        "## Construction failure per attempt at the default overhead",
        "",
        "`max_attempts=1`, an independent key range per trial. Target: at most 7% (the design aims at about 3%).",
        "",
    ]
    out += table(
        ["n", "overhead", "rows", "trials", "failures", "rate", "95% CI"],
        [
            [
                f"{r['n']:,}",
                f"{100 * r['overhead']:.1f}%",
                f"{r['rows']:,}",
                f"{r['trials']:,}",
                str(r["failures"]),
                f"{100 * r['rate']:.2f}%",
                f"{100 * r['ci95'][0]:.2f}% to {100 * r['ci95'][1]:.2f}%",
            ]
            for r in data.get("construction", [])
        ],
    )
    out += ["", "## Failure rate vs overhead (around the default)", ""]
    out += table(
        ["n", "overhead", "rows", "trials", "failure rate"],
        [
            [
                f"{r['n']:,}",
                f"{100 * r['overhead']:.2f}%",
                f"{r['rows']:,}",
                f"{r['trials']:,}",
                f"{100 * r['rate']:.2f}%",
            ]
            for r in data.get("sweep", [])
        ],
    )
    out += ["", "## Size at the default parameters", ""]
    out += table(
        ["n", "fp_bits", "rows", "measured bits/key (with 64-byte header)", "expected from the sizing table"],
        [
            [
                f"{r['n']:,}",
                str(r["r"]),
                f"{r['rows']:,}" if "rows" in r else "",
                f"{r['measured_bits_per_key']:.3f}",
                f"{r['expected_bits_per_key']:.3f}",
            ]
            for r in data.get("size", [])
        ],
    )
    return "\n".join(out) + "\n"


def main() -> None:
    """Command line entry point."""
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.write_text(render(json.loads(src.read_text())))
    print(f"wrote {dst}")


if __name__ == "__main__":
    main()
