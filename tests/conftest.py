"""Shared pytest configuration: Hypothesis profiles for the pyribbon test suite.

Select a profile with ``HYPOTHESIS_PROFILE=pyribbon-thorough`` (about 20x more examples per property). Builds take a
variable amount of time, so the per-example deadline is disabled.
"""

from __future__ import annotations

import os

import pytest
from hypothesis import HealthCheck, settings

_COMMON = {
    "deadline": None,
    "suppress_health_check": [HealthCheck.too_slow, HealthCheck.data_too_large],
    "print_blob": True,
}
settings.register_profile("pyribbon", max_examples=100, **_COMMON)
settings.register_profile("pyribbon-thorough", max_examples=2000, **_COMMON)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "pyribbon"))


def pytest_configure(config: pytest.Config) -> None:
    """Register the ``slow`` marker here too, so it exists when the tests run without pyproject.toml (wheel tests)."""
    config.addinivalue_line(
        "markers", "slow: statistical tests with many millions of probes (deselect with -m 'not slow')"
    )
