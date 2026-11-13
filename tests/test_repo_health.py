"""The community files under .github/ parse and keep the keys GitHub needs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

ROOT = Path(__file__).resolve().parent.parent
GITHUB = ROOT / ".github"

pytestmark = pytest.mark.skipif(not GITHUB.is_dir(), reason=".github/ is not shipped next to the installed tests")


def load(path: Path) -> Any:
    return yaml.safe_load(path.read_text())


def test_issue_forms_have_the_required_keys() -> None:
    forms = sorted((GITHUB / "ISSUE_TEMPLATE").glob("*.yml"))
    names = {f.name for f in forms}
    assert {"bug_report.yml", "feature_request.yml", "config.yml"} <= names
    for form in forms:
        if form.name == "config.yml":
            continue
        data = load(form)
        assert {"name", "description", "body"} <= set(data), form.name
        ids = [item["id"] for item in data["body"] if item["type"] != "markdown"]
        assert len(ids) == len(set(ids)), f"{form.name}: duplicate ids"
        assert any(item.get("validations", {}).get("required") for item in data["body"]), form.name


def test_bug_report_asks_for_what_a_report_needs() -> None:
    ids = {item.get("id") for item in load(GITHUB / "ISSUE_TEMPLATE" / "bug_report.yml")["body"]}
    assert {"pyribbon-version", "python-version", "reproduction", "exception"} <= ids


def test_issue_config_allows_blank_issues_and_links_to_the_security_policy() -> None:
    config = load(GITHUB / "ISSUE_TEMPLATE" / "config.yml")
    assert config["blank_issues_enabled"] is True
    assert any(link["url"].endswith("/SECURITY.md") for link in config["contact_links"])


def test_dependabot_covers_github_actions_weekly() -> None:
    config = load(GITHUB / "dependabot.yml")
    assert config["version"] == 2
    update = next(u for u in config["updates"] if u["package-ecosystem"] == "github-actions")
    assert update["schedule"]["interval"] == "weekly"


def test_pre_commit_ruff_rev_is_pinned_to_a_tag() -> None:
    repo = load(ROOT / ".pre-commit-config.yaml")["repos"][0]
    assert repo["repo"].endswith("/ruff-pre-commit")
    assert repo["rev"].startswith("v")
    assert {hook["id"] for hook in repo["hooks"]} == {"ruff-check", "ruff-format"}
