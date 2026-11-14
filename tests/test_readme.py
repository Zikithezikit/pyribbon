"""The README and the docs are checked documentation: the quick start runs, every example script is listed, the benchmark
tables are exact copies of the ones in docs/benchmark.md, and every link points at something that exists."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

pytestmark = pytest.mark.skipif(not README.exists(), reason="README.md is not shipped next to the installed tests")


def test_usage_page_lists_every_example_and_only_real_ones() -> None:
    """The examples live in examples/. docs/usage.md lists each script with a link, and each link points at a file."""
    text = (ROOT / "docs" / "usage.md").read_text()
    linked = set(re.findall(r"\]\(\.\./(examples/[\w./-]+\.py)\)", text))
    on_disk = {f"examples/{p.name}" for p in (ROOT / "examples").glob("*.py")}
    assert on_disk, "examples/ has no scripts"
    assert linked == on_disk, f"docs/usage.md and examples/ disagree: {sorted(linked ^ on_disk)}"


def test_readme_quick_start_runs() -> None:
    """The README's one Python block runs as written; its asserts are the check."""
    blocks = re.findall(r"```python\n(.*?)```", README.read_text(), flags=re.DOTALL)
    assert len(blocks) == 1, "the README has exactly one quick start block; longer code belongs in examples/"
    exec(compile(blocks[0], "README.md", "exec"), {})  # noqa: S102


def test_readme_links_are_absolute() -> None:
    """Relative links break on the PyPI page, so the README uses absolute URLs."""
    relative = re.findall(r"\]\((?!https?://|#)([^)]+)\)", README.read_text())
    assert not relative, f"use absolute URLs: {relative}"


def _update_readme():  # type: ignore[no-untyped-def]
    sys.path.insert(0, str(ROOT / "benchmarks"))
    try:
        import update_readme
    finally:
        sys.path.pop(0)
    return update_readme


def test_benchmark_blocks_match_the_generated_results() -> None:
    mod = _update_readme()
    md, js = ROOT / "docs" / "benchmark.md", ROOT / "docs" / "benchmark.json"
    assert md.exists() and js.exists(), "run `make bench` first"
    stale = "benchmark block is stale: run `python benchmarks/update_readme.py` after `make bench`"
    summary = mod.benchmark_block(md.read_text())
    by_size = mod.by_size_block(json.loads(js.read_text()))
    page = (ROOT / "docs" / "performance.md").read_text()
    assert mod.read_block(README.read_text(), "bench") == summary, f"README {stale}"
    assert mod.read_block(page, "bench") == summary, f"docs/performance.md {stale}"
    assert mod.read_block(page, "bench-by-size") == by_size, f"docs/performance.md {stale}"


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
    """Every figure in the README is an absolute raw-GitHub URL (so it renders on PyPI too) of a file in this repository.

    Status badges (the CI badge and shields.io) are the only images that come from elsewhere.
    """
    images = re.findall(r"!\[[^\]]*\]\((\S+?)\)", README.read_text())
    urls = [u for u in images if not u.endswith("/badge.svg") and not u.startswith("https://img.shields.io/")]
    prefix = "https://raw.githubusercontent.com/Zikithezikit/pyribbon/main/"
    assert len(urls) >= 1
    for url in urls:
        assert url.startswith(prefix), f"use an absolute raw URL for {url}"
        assert (ROOT / url.removeprefix(prefix)).is_file(), f"missing image file for {url}"
