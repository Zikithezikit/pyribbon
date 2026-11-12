"""The README is executable documentation: every Python example runs, printed output matches its comment, and the
benchmark table is an exact copy of the one in docs/benchmark.md."""

from __future__ import annotations

import contextlib
import io
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"

pytestmark = pytest.mark.skipif(not README.exists(), reason="README.md is not shipped next to the installed tests")


def python_blocks() -> list[str]:
    return re.findall(r"```python\n(.*?)```", README.read_text(), flags=re.DOTALL)


@pytest.mark.parametrize("index", range(len(python_blocks()) if README.exists() else 0))
def test_readme_example_runs_and_prints_what_it_says(index: int) -> None:
    code = python_blocks()[index]
    expected = [
        re.sub(r"\s+\(.*\)$", "", m.group(1))  # a trailing "(note)" is commentary, not output
        for m in re.finditer(r"print\(.*\)\s+# (.*)$", code, flags=re.MULTILINE)
    ]
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(code, f"README.md block {index}", "exec"), {"__name__": "__readme__"})
    assert out.getvalue().splitlines() == expected


def test_readme_benchmark_block_matches_docs_benchmark_md() -> None:
    sys.path.insert(0, str(ROOT / "benchmarks"))
    try:
        from update_readme import benchmark_block, readme_block
    finally:
        sys.path.pop(0)
    report = ROOT / "docs" / "benchmark.md"
    assert report.exists(), "run `make bench` first"
    assert readme_block(README.read_text()) == benchmark_block(report.read_text()), (
        "README benchmark block is stale: run `python benchmarks/update_readme.py` after `make bench`"
    )
