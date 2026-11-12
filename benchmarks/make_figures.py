"""Small, README-sized figures drawn from the measured data (nothing is measured here).

Reads docs/benchmark.json (written by ``make bench``) and docs/measurements.json (written by ``make stats``) and writes:

* docs/img/overview.png: space per key, build time and query time against the number of keys, int keys, 8-bit class;
* docs/img/accuracy.png: measured false-positive rate divided by the designed rate 2**-r for every tested case.

Usage: ``python benchmarks/make_figures.py`` (or ``make figures``). Colors and marker shapes match docs/benchmark.png, and
the palette was checked with the dataviz skill's validator (colorblind separation passes; the pink Bloom series is just
under 3:1 contrast against white, so every series also has its own marker shape and a direct label).
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

INK, MUTED, GRID, SURFACE = "#1f2328", "#57606a", "#d8dce0", "#ffffff"
# series: (label, color, marker); the same entity keeps the same color and shape in every figure
SERIES = {
    "pyribbon": ("pyribbon", "#D55E00", "o"),
    "fuse8": ("Fuse8", "#009E73", "^"),
    "xor8": ("Xor8 (space panel only)", "#0072B2", "s"),
    "rbloom": ("rbloom", "#CC79A7", "D"),
}


# labels in the speed panels name what is measured: the Python packages as shipped
LABELS = {"pyribbon": "pyribbon", "fuse8": "Fuse8, pyfusefilter as shipped", "rbloom": "rbloom, built-in hash()"}
SHORT = {"pyribbon": "pyribbon", "fuse8": "Fuse8 as shipped", "rbloom": "rbloom"}


def style() -> None:
    """Quiet, readable defaults: recessive grid, no top/right spines, plain white surface."""
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "savefig.facecolor": SURFACE,
            "axes.edgecolor": "#8b949e",
            "axes.labelcolor": MUTED,
            "axes.titlecolor": INK,
            "axes.titlesize": 10.5,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "grid.color": GRID,
            "grid.linewidth": 0.6,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "text.color": INK,
            "font.size": 9,
            "legend.frameon": False,
        }
    )


def int_cells(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The int-key cells of the benchmark, sorted by n."""
    return sorted((c for c in data["results"] if c["regime"] == "int"), key=lambda c: c["n"])


def pow10_axis(ax: Any, log_y: bool) -> None:
    """Powers of ten on x; plain numbers (not 10^k) on a log y axis."""
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f"1e{round(math.log10(v))}"))
    if log_y:
        ax.set_yscale("log")
        ax.yaxis.set_major_locator(LogLocator(base=10, subs=(1.0, 2.0, 5.0)))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:g}"))
        ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xlabel("number of keys")


def draw(
    ax: Any,
    ns: list[int],
    ys: list[float],
    key: str,
    label: str | None = None,
    dotted: bool = False,
    short: str | None = None,
    dy: float = 0.0,
) -> None:
    """One series: thin line, 7 px marker, a direct label (``short``, shifted by ``dy`` points) at the last point."""
    name, color, marker = SERIES[key]
    ax.plot(
        ns,
        ys,
        color=color,
        marker=marker,
        markersize=6.5,
        linewidth=1.8,
        linestyle=":" if dotted else "-",
        markerfacecolor=SURFACE if dotted else color,
        markeredgecolor=color,
        markeredgewidth=1.4,
        label=label or name,
    )
    ax.annotate(
        short or (label or name).split(" (")[0],
        (ns[-1], ys[-1]),
        xytext=(7, dy),
        textcoords="offset points",
        va="center",
        fontsize=8,
        color=INK,
        annotation_clip=False,
    )


def overview(data: dict[str, Any], path: Path) -> None:
    """Space, build time and query time against n (int keys, 8-bit fingerprint class)."""
    cells = int_cells(data)
    ns = [c["n"] for c in cells]

    def f(c: dict[str, Any], key: str) -> dict[str, Any]:
        return c["filters"][key]

    fig, axes = plt.subplots(1, 3, figsize=(12.6, 3.7), gridspec_kw={"wspace": 0.42})
    ax = axes[0]
    nudge = {"pyribbon": 6.0, "fuse8": -6.0}  # the last points of pyribbon and Fuse8 nearly coincide
    for key, fk in (("pyribbon", "pyribbon8"), ("fuse8", "fuse8"), ("xor8", "xor8"), ("rbloom", "rbloom8")):
        draw(ax, ns, [f(c, fk)["bits_per_key"] for c in cells], key, dy=nudge.get(key, 0.0))
    ax.axhline(8, color="#6e7781", linewidth=0.9, linestyle="--")
    ax.text(ns[0], 8.08, "minimum for a 2^-8 false-positive rate: 8 bits", fontsize=7.5, color=MUTED, va="bottom")
    ax.set_ylim(7.5, 12.2)
    ax.set_ylabel("bits per key")
    ax.set_title("Space per key (lower is better)")
    pow10_axis(ax, log_y=False)

    ax = axes[1]
    for key, fk in (("pyribbon", "pyribbon8"), ("fuse8", "fuse8"), ("rbloom", "rbloom8b")):
        draw(ax, ns, [f(c, fk)["build_ns"]["median"] / c["n"] for c in cells], key, LABELS[key], short=SHORT[key])
    core = [c["diag"]["pyfusefilter"]["core_build"]["fuse8"]["median"] for c in cells]
    draw(ax, ns, core, "fuse8", "Fuse8, C core only", dotted=True, short="Fuse8 C core only")
    ax.set_ylabel("ns per key")
    ax.set_title("Build time (lower is better)")
    pow10_axis(ax, log_y=True)

    ax = axes[2]
    for key, fk in (("pyribbon", "pyribbon8"), ("fuse8", "fuse8"), ("rbloom", "rbloom8b")):
        draw(ax, ns, [f(c, fk)["lat_non_member_ns"]["median"] for c in cells], key, LABELS[key], short=SHORT[key])
    ax.set_ylabel("ns per lookup")
    ax.set_title("Lookup time, key not in set (lower is better)")
    pow10_axis(ax, log_y=True)

    handles, labels = axes[1].get_legend_handles_labels()
    extra = [h for h, lab in zip(*axes[0].get_legend_handles_labels(), strict=True) if lab == SERIES["xor8"][0]]
    fig.legend(
        handles + extra,
        labels + [SERIES["xor8"][0]] * len(extra),
        loc="upper center",
        ncol=5,
        fontsize=8.5,
        bbox_to_anchor=(0.5, -0.02),
    )
    meta = data["meta"]
    cpu = meta.get("machine", {}).get("CPU", "")
    fig.suptitle(
        f"pyribbon vs pyfusefilter and rbloom, int keys, 8-bit fingerprint class{f' ({cpu})' if cpu else ''}",
        x=0.01,
        ha="left",
        fontsize=10,
        color=MUTED,
        y=1.02,
    )
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def accuracy(rows: list[dict[str, Any]], path: Path) -> None:
    """Measured false-positive rate over the designed rate 2**-r, one dot per tested case, with 95% intervals."""
    fig, ax = plt.subplots(figsize=(7.2, 3.6))
    families = {"int": ("o", "#D55E00"), "str": ("s", "#0072B2"), "bytes": ("^", "#009E73")}
    names = {"int": "int keys", "str": "str keys", "bytes": "bytes keys"}
    offsets = {"int": -0.18, "str": 0.0, "bytes": 0.18}
    for fam, (marker, color) in families.items():
        sel = [r for r in rows if r["family"] == fam]
        xs = [r["r"] + offsets[fam] for r in sel]
        ys = [r["rate"] / r["p"] for r in sel]
        err = [1.96 * math.sqrt((1 - r["p"]) / (r["probes"] * r["p"])) for r in sel]
        ax.errorbar(
            xs, ys, yerr=err, fmt=marker, color=color, markersize=5.5, elinewidth=1.0, capsize=0, label=names[fam],
            markerfacecolor=color, markeredgecolor=SURFACE, markeredgewidth=0.8,
        )  # fmt: skip
    ax.axhline(1.0, color="#6e7781", linewidth=1.0, linestyle="--")
    ax.set_ylim(0.88, 1.12)
    ax.set_xlabel("fp_bits r (designed false-positive rate 2^-r)")
    ax.set_ylabel("measured rate / designed rate")
    ax.set_title("False-positive rate: measured over designed (1.0 = exactly as designed)")
    ax.xaxis.set_major_locator(plt.MultipleLocator(2))
    ax.legend(loc="upper right", ncol=3, fontsize=8.5)
    total = sum(r["probes"] for r in rows)
    ax.text(
        0.0, -0.22, f"{len(rows)} cases, {total / 1e9:.1f} billion negative probes in total; bars are 95% intervals "
        "(wider for rare events: fewer false positives to count).",
        transform=ax.transAxes, fontsize=7.5, color=MUTED,
    )  # fmt: skip
    fig.savefig(path, dpi=170, bbox_inches="tight")
    plt.close(fig)


def main() -> None:
    """Write the figures into docs/img/."""
    style()
    out = DOCS / "img"
    out.mkdir(parents=True, exist_ok=True)
    bench = DOCS / "benchmark.json"
    if bench.exists():
        overview(json.loads(bench.read_text()), out / "overview.png")
        print(f"wrote {out / 'overview.png'}")
    else:
        print("docs/benchmark.json not found: run `make bench` first")
    stats = DOCS / "measurements.json"
    if stats.exists():
        accuracy(json.loads(stats.read_text())["fpr"], out / "accuracy.png")
        print(f"wrote {out / 'accuracy.png'}")
    else:
        print("docs/measurements.json not found: run `make stats` first")


if __name__ == "__main__":
    main()
