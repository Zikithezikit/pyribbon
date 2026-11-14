"""The docs folder is checked too: every relative link and image points at a file, and the API reference names everything
that pyribbon exports."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

import pyribbon

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

pytestmark = pytest.mark.skipif(not DOCS.exists(), reason="docs/ is not shipped next to the installed tests")


def _pages() -> list[Path]:
    return sorted(DOCS.glob("*.md"))


@pytest.mark.parametrize("page", _pages(), ids=lambda p: p.name)
def test_relative_links_and_images_point_at_files(page: Path) -> None:
    for target in re.findall(r"\]\((?!https?://|#|mailto:)([^)\s]+)\)", page.read_text()):
        path = target.split("#", 1)[0]
        assert (page.parent / path).exists(), f"{page.name} links to {target}, which does not exist"


def test_index_links_every_page() -> None:
    index = (DOCS / "index.md").read_text()
    for page in _pages():
        if page.name not in ("index.md", "benchmark.md", "measurements.md"):
            assert f"]({page.name})" in index, f"docs/index.md does not link {page.name}"
    assert "](benchmark.md)" in index and "](measurements.md)" in index


def test_api_reference_names_every_public_member() -> None:
    api = (DOCS / "api.md").read_text()
    for name in pyribbon.__all__:
        assert f"`{name}`" in api or f"`{name}(" in api, f"docs/api.md does not mention {name}"
    members = [n for n in vars(pyribbon.RibbonFilter) if not n.startswith("_") or n in ("__contains__", "__len__")]
    for member in members:
        shown = {"__contains__": "key in f", "__len__": "len(f)"}.get(member, member)
        assert shown in api, f"docs/api.md does not mention RibbonFilter.{member}"
