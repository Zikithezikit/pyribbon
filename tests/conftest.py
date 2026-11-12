"""Shared pytest configuration: Hypothesis profiles for the pyribbon test suite.

Select a profile with ``HYPOTHESIS_PROFILE=pyribbon-thorough`` (about 20x more examples per property). Builds take a
variable amount of time, so the per-example deadline is disabled.
"""

from __future__ import annotations

import os

from hypothesis import HealthCheck, settings

_COMMON = {
    "deadline": None,
    "suppress_health_check": [HealthCheck.too_slow, HealthCheck.data_too_large],
    "print_blob": True,
}
settings.register_profile("pyribbon", max_examples=100, **_COMMON)
settings.register_profile("pyribbon-thorough", max_examples=2000, **_COMMON)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "pyribbon"))
