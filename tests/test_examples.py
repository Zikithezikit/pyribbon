"""Every script in examples/ runs from a clean process, exits cleanly and prints what it is meant to show."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"

pytestmark = pytest.mark.skipif(not EXAMPLES.is_dir(), reason="examples/ is not shipped next to the installed tests")

SCRIPTS = sorted(p.name for p in EXAMPLES.glob("*.py")) if EXAMPLES.is_dir() else []


def run(name: str) -> list[str]:
    done = subprocess.run(
        [sys.executable, str(EXAMPLES / name)], capture_output=True, text=True, timeout=180, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stderr == ""
    return done.stdout.splitlines()


@pytest.mark.parametrize("name", SCRIPTS)
def test_example_runs(name: str) -> None:
    assert run(name), "an example should print something"


def test_quickstart_output() -> None:
    assert run("01_quickstart.py") == ["True", "False", "[True, False]", "3 256 683"]


def test_key_types_output() -> None:
    lines = run("02_key_types.py")
    assert lines[:4] == ["True", "True", "True True True", "False False"]
    assert sum("unsupported key type" in line for line in lines) == 3
    assert any("not a single str" in line for line in lines)


def test_choosing_fp_bits_measures_close_to_the_design() -> None:
    rows = [line.split() for line in run("03_choosing_fp_bits.py")[2:]]
    assert [int(r[0]) for r in rows] == [4, 8, 12, 16]
    for fp_bits, designed, measured, bits, bloom in rows:
        assert float(measured) == pytest.approx(float(designed), rel=0.5 if fp_bits == "16" else 0.1)
        assert float(bits) < float(bloom)  # smaller than a Bloom filter at every width shown


def test_save_and_load_output() -> None:
    lines = run("04_save_and_load.py")
    assert re.fullmatch(r"wrote [\d,]+ bytes", lines[0])
    assert lines[1:] == ["True 100000 10", "True", "invalid pyribbon data: checksum mismatch"]


def test_batches_and_arrays_output() -> None:
    lines = run("05_batches_and_arrays.py")
    assert lines[:2] == ["[True, True, False, False]", "True"]


def test_errors_output() -> None:
    lines = run("06_errors.py")
    assert lines[0].startswith("ConstructionError: could not build a filter for 100000 keys")
    assert "FormatError (garbage): invalid pyribbon data: bad magic number: not a pyribbon filter" in lines
    assert "FormatError (truncated): invalid pyribbon data: buffer too short" in lines
    assert any(line.startswith("ValueError: fp_bits must be") for line in lines)
    assert any(line.startswith("TypeError: unsupported key type") for line in lines)


def test_threads_output() -> None:
    first, second, same = run("07_threads.py")[0].split()
    assert first == second and same == "True"
