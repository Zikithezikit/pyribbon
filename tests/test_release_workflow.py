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


GUARD = ("success()", "github.event_name == 'push'", "github.ref_type == 'tag'", "startsWith(github.ref_name, 'v')")


def test_only_the_publish_and_release_jobs_can_publish_and_both_are_guarded() -> None:
    jobs = load("release.yml")["jobs"]
    publishing = sorted(name for name, job in jobs.items() if any(word in json.dumps(job) for word in PUBLISHING))
    assert publishing == ["github-release", "publish"]
    for name in publishing:
        for condition in GUARD:
            assert condition in jobs[name]["if"], f"{name} must require {condition}"


def test_nothing_is_released_unless_the_whole_pipeline_passed() -> None:
    jobs = load("release.yml")["jobs"]
    assert set(jobs["check"]["needs"]) == {"ci", "wheels", "sdist"}, "the checks wait for tests and builds"
    assert jobs["publish"]["needs"] == ["check"], "the upload waits for the checks"
    assert jobs["github-release"]["needs"] == ["publish"], "the GitHub release is last and needs a successful upload"


def test_the_token_and_the_permissions_stay_in_their_own_jobs() -> None:
    jobs = load("release.yml")["jobs"]
    for name, job in jobs.items():
        if name != "publish":
            assert "secrets." not in json.dumps(job), f"job {name} must not see any secret"
    steps = [json.dumps(s) for s in jobs["publish"]["steps"] if "PYPI_API_TOKEN" in json.dumps(s)]
    assert len(steps) == 1 and "uv publish" in steps[0], "the token is used by exactly one step: the upload"
    assert jobs["publish"]["permissions"] == {"id-token": "write", "attestations": "write"}
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    assert "gh release create" not in json.dumps(jobs["publish"]), "the release is not made in the upload job"


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")) if WORKFLOWS.is_dir() else [])
def test_no_other_workflow_can_publish(name: str) -> None:
    if name == "release.yml":
        return
    text = (WORKFLOWS / name).read_text()
    for word in PUBLISHING:
        assert word not in text, f"{name} must not contain {word!r}; publishing belongs to release.yml"


def test_macos_archs_are_not_pinned_while_two_runners_build_wheels() -> None:
    """The release check merges the wheel artifacts into one directory. Pinning both macOS archs while the matrix
    has two macOS runners makes each runner emit the same wheel filenames, and the merge corrupts them (this is
    how the v0.1.0 release failed: twine could not read a merged wheel)."""
    matrix = load("wheels.yml")["jobs"]["wheels"]["strategy"]["matrix"]["os"]
    macos_runners = [os for os in matrix if str(os).startswith("macos")]
    if len(macos_runners) > 1:
        pyproject = (WORKFLOWS.parent.parent / "pyproject.toml").read_text()
        wheels_yml = (WORKFLOWS / "wheels.yml").read_text()
        assert "[tool.cibuildwheel.macos]" not in pyproject, (
            "cibuildwheel's default (auto) builds each runner's native arch"
        )
        assert "CIBW_ARCHS_MACOS" not in wheels_yml, "cibuildwheel's default (auto) builds each runner's native arch"


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")) if WORKFLOWS.is_dir() else [])
def test_pipelines_run_only_for_main_tags_and_pull_requests_to_main(name: str) -> None:
    """Pushes to other branches do not start a pipeline; the pull request that targets main does. Tags are handled by
    release.yml alone (it calls ci.yml and wheels.yml), so no other workflow may trigger on tags."""
    triggers = load(name)["on"]
    assert isinstance(triggers, dict)
    assert "pull_request_target" not in triggers, "pull_request_target runs with secrets on untrusted code"
    # a bare `push:` or `pull_request:` key parses to None: treat it as "no filter", which is what it means
    if name == "release.yml":
        assert triggers.get("push") == {"tags": ["v*"]}
    elif "push" in triggers:
        assert (triggers["push"] or {}) == {"branches": ["main"]}, f"{name}: push must be limited to main (never tags)"
    if "pull_request" in triggers:
        assert (triggers["pull_request"] or {}).get("branches") == ["main"], f"{name}: PRs must be limited to main"
    if "schedule" in triggers:
        assert name == "stats.yml", "only the statistics workflow is scheduled"
