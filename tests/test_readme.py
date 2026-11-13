"""The README is executable documentation: every Python example runs, printed output matches its comment, and the
benchmark table is an exact copy of the one in docs/benchmark.md."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

pytestmark = pytest.mark.skipif(not README.exists(), reason="README.md is not shipped next to the installed tests")


def test_readme_links_every_example_and_only_real_ones() -> None:
    """The examples live in examples/, not in the README: each script is listed there, with an absolute link (so it also
    works on the PyPI page), and each link points at a file."""
    text = README.read_text()
    prefix = "https://github.com/Zikithezikit/pyribbon/blob/main/"
    linked = set(re.findall(r"\]\(" + re.escape(prefix) + r"(examples/[\w./-]+\.py)\)", text))
    on_disk = {f"examples/{p.name}" for p in (ROOT / "examples").glob("*.py")}
    assert on_disk, "examples/ has no scripts"
    assert linked == on_disk, f"README and examples/ disagree: {sorted(linked ^ on_disk)}"
    assert "```python" not in text, "put code in examples/ and link to it"
    relative = re.findall(r"\]\((?!https?://|#)([^)]+)\)", text)
    assert not relative, f"relative links break on the PyPI page; use absolute URLs: {relative}"


def _update_readme():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(ROOT / "benchmarks"))
    try:
        import update_readme
    finally:
        sys.path.pop(0)
    return update_readme


def test_readme_benchmark_blocks_match_the_generated_results() -> None:
    mod = _update_readme()
    readme = README.read_text()
    md, js = ROOT / "docs" / "benchmark.md", ROOT / "docs" / "benchmark.json"
    assert md.exists() and js.exists(), "run `make bench` first"
    stale = "README benchmark block is stale: run `python benchmarks/update_readme.py` after `make bench`"
    assert mod.read_block(readme, "bench") == mod.benchmark_block(md.read_text()), stale
    assert mod.read_block(readme, "bench-by-size") == mod.by_size_block(json.loads(js.read_text())), stale


def test_readme_fp_bits_table_matches_real_filters() -> None:
    import array

    from pyribbon import RibbonFilter

    rows = re.findall(r"^\| (\d+) \| ([\d.]+)% \| ([\d.]+) \|$", README.read_text(), flags=re.MULTILINE)
    assert [int(r) for r, _, _ in rows] == [4, 8, 12, 16, 20]
    keys = array.array("q", range(1_000_000))
    for r, rate, bits in rows:
        assert float(rate) == pytest.approx(
            100 * 2.0 ** -int(r), rel=0.05
        )  # the README rounds to two significant digits
        assert float(bits) == pytest.approx(RibbonFilter(keys, fp_bits=int(r)).bits_per_key, abs=0.005)


def test_readme_images_exist() -> None:
    """Every image in the README is an absolute raw-GitHub URL (so it renders on PyPI too) of a file in this repository."""
    urls = [u for u in re.findall(r"!\[[^\]]*\]\((\S+?)\)", README.read_text()) if not u.endswith("/badge.svg")]
    prefix = "https://raw.githubusercontent.com/Zikithezikit/pyribbon/main/"
    assert len(urls) >= 2
    for url in urls:
        assert url.startswith(prefix), f"use an absolute raw URL for {url}"
        assert (ROOT / url.removeprefix(prefix)).is_file(), f"missing image file for {url}"
