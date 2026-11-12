"""Copy the "where pyribbon wins and loses" block of docs/benchmark.md into README.md, between the bench markers.

Usage: ``python benchmarks/update_readme.py`` (run by hand after ``make bench``; tests/test_readme.py checks the copy).
"""

from __future__ import annotations

from pathlib import Path

START, END = "<!-- bench:start -->", "<!-- bench:end -->"
HEADING = "## Where pyribbon wins and loses"


def benchmark_block(markdown: str) -> str:
    """Return the body of the "wins and loses" section of a benchmark report (heading excluded)."""
    lines = markdown.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(HEADING))
    heading = lines[start]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    body = "\n".join(lines[start + 1 : end]).strip("\n")
    return f"*{heading.removeprefix('## ')}:*\n\n{body}"


def readme_block(readme: str) -> str:
    """Return the text between the bench markers of a README."""
    return readme.split(START, 1)[1].split(END, 1)[0].strip("\n")


def main() -> None:
    """Rewrite the bench block of README.md from docs/benchmark.md."""
    root = Path(__file__).resolve().parent.parent
    readme = (root / "README.md").read_text()
    block = benchmark_block((root / "docs" / "benchmark.md").read_text())
    head, rest = readme.split(START, 1)
    tail = rest.split(END, 1)[1]
    (root / "README.md").write_text(f"{head}{START}\n{block}\n{END}{tail}")
    print("README.md updated from docs/benchmark.md")


if __name__ == "__main__":
    main()
