"""The PyPI release can only happen for a pushed version tag, and nothing else in the repository can publish."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

yaml = pytest.importorskip("yaml")

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"

pytestmark = pytest.mark.skipif(not WORKFLOWS.is_dir(), reason=".github/ is not shipped next to the installed tests")

PUBLISHING = ("PYPI_API_TOKEN", "uv publish", "twine upload", "pypi-publish", "gh release create", "id-token: write")


def load(name: str) -> dict[str, Any]:
    data = yaml.safe_load((WORKFLOWS / name).read_text())
    data["on"] = data.pop("on", data.pop(True, None))  # YAML 1.1 reads the key `on` as True
    return data


def test_release_workflow_triggers_only_on_version_tags_and_manual_runs() -> None:
    triggers = load("release.yml")["on"]
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"tags": ["v*"]}, "no branch pushes, no pull requests"


def test_only_the_publish_job_can_publish_and_it_is_guarded() -> None:
    jobs = load("release.yml")["jobs"]
    publishing = [name for name, job in jobs.items() if any(word in json.dumps(job) for word in PUBLISHING)]
    assert publishing == ["publish"]
    guard = jobs["publish"]["if"]
    for condition in ("github.event_name == 'push'", "github.ref_type == 'tag'", "startsWith(github.ref_name, 'v')"):
        assert condition in guard
    assert jobs["publish"]["needs"] == ["check"], "publishing waits for the checks"
    assert set(jobs["check"]["needs"]) == {"ci", "wheels", "sdist"}, "the checks wait for tests and builds"


def test_the_token_is_never_exposed_outside_the_publish_job() -> None:
    jobs = load("release.yml")["jobs"]
    for name, job in jobs.items():
        if name != "publish":
            assert "secrets." not in json.dumps(job), f"job {name} must not see any secret"
    steps = [json.dumps(s) for s in jobs["publish"]["steps"] if "PYPI_API_TOKEN" in json.dumps(s)]
    assert len(steps) == 1 and "uv publish" in steps[0], "the token is used by exactly one step: the upload"


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")) if WORKFLOWS.is_dir() else [])
def test_no_other_workflow_can_publish(name: str) -> None:
    if name == "release.yml":
        return
    text = (WORKFLOWS / name).read_text()
    for word in PUBLISHING:
        assert word not in text, f"{name} must not contain {word!r}; publishing belongs to release.yml"
