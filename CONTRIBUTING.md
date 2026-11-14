# Contributing

```bash
make venv          # create .venv
make install-dev   # editable install with dev tools (builds the C extension)
make check         # lint, docstyle, mypy + stubtest, C tests, Python tests
make example       # run every script in examples/ (a test also runs them)
```

The longer checks and the measurements:

```bash
make c-asan c-portable  # C tests under ASan/UBSan, and with the portable bit-op fallbacks
make c-fuzz             # fuzz the loader
make stats              # millions of probes: measured false-positive rates (docs/measurements.md)
make bench              # the benchmark (docs/benchmark.png, docs/benchmark.md), then run benchmarks/update_readme.py
make figures            # redraw docs/img/*.png from the saved results, without measuring again
```

To run the lint and format checks before every commit, install the hooks once with `pip install pre-commit && pre-commit install`.
They run `ruff check` and `ruff format` with the settings in `pyproject.toml`, and `.editorconfig` sets the indentation
(4 spaces in Python, 2 in C, YAML and TOML, tabs in Makefiles). Open a pull request from a branch; the template lists what to
check. Bugs and feature requests have issue templates. Vulnerabilities do not go in issues: see `SECURITY.md`. Dependabot
sends weekly updates for the GitHub Actions the workflows use.

New examples go in `examples/` with the next number (`08_...py`) and a docstring that says how to run it. `tests/test_examples.py`
runs each script, and `tests/test_readme.py` checks that `docs/usage.md` lists it. The README keeps one short quick start
and links the rest into `docs/`; `tests/test_docs.py` checks that every docs link works and that `docs/api.md` names every public
member, so a new method needs an entry there.

The C core (`core/`) builds and tests without Python, using `make c-test`, `make c-asan` and `make c-portable`.
C code must compile with `-std=c11 -Wall -Wextra -Wconversion -Werror`. A change to the algorithm needs a citation to
the Ribbon papers (see [docs/research.md](docs/research.md)). Do not copy code from RocksDB, fastfilter_cpp, BuRR or other implementations.

## Coverage

```bash
make coverage      # core and extension (a few minutes); needs gcc, installs gcovr into build/cov-venv
make c-coverage    # only the C core
make c-nomem       # the allocation-failure tests on their own (Linux, GNU ld)
```

`make c-coverage` builds the core unit tests twice with `gcc --coverage -O0` (default and `RB_PORTABLE=1`), builds
`core/tests/test_nomem.c`, runs all three and prints line and branch coverage per file with gcovr. The allocation-failure
tests link with `-Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc` and fail the 0th, 1st, 2nd ... allocation of each core call;
`make c-nomem` runs them under ASan and UBSan so a leak on an error path fails the run. No production source has a test hook.
`make ext-coverage` builds `src/pyribbon/_ribbon.c` with coverage flags in a scratch venv (`build/cov-venv`, your dev install is
not touched) and runs the Python tests against it. Its memory-failure tests run a child interpreter under `RLIMIT_AS` (Linux).

The Coverage workflow (`.github/workflows/coverage.yml`) runs this on pushes to `main` and on pull requests, prints the tables in the
job summary and fails when line coverage drops below `CORE_LINE_MIN` (the core) or `EXT_LINE_MIN` (the extension), both set in the
`env:` block of that file. `make coverage COV_MIN=N EXT_COV_MIN=N` applies a gate locally. Code that cannot run in a test is left
uncovered rather than hidden: the remaining branches are the 32-bit and big-endian code, the row-limit check when the table grows,
and failures of tiny CPython allocations.

## Releasing

1. Raise `version` in `pyproject.toml` and `__version__` in `src/pyribbon/__init__.py`, move the CHANGELOG entry from
   "Unreleased" to the new version, and commit to `main`.
2. Wait for CI to pass on `main`. To rehearse, run the Release workflow by hand (Actions, Release, Run workflow). It builds and
   checks everything and publishes nothing, even when started from a tag.
3. Tag that commit and push the tag: `git tag v0.1.0 && git push origin v0.1.0`.

The Release workflow then runs the full tests, builds the sdist and the wheels and checks that the tag equals the version in
`pyproject.toml` and points at a commit on `main`. Only if all of that passed does it publish to PyPI with the repository secret
`PYPI_API_TOKEN`, and only after the upload succeeded does a last, separate job create the GitHub release. A failure anywhere
stops everything after it. If only the GitHub release fails, re-run just that job from the Actions page. A tag with a suffix such as `v0.2.0rc1` becomes a GitHub pre-release. A failed run can be repeated, because
files already on PyPI are skipped. PyPI never accepts the same version twice, so a bad release needs a new version number.

## When the pipeline runs

Only three things start it: a push to `main`, a pull request into `main`, and a pushed `v*` tag (handled by `release.yml`, which calls
the CI and wheel workflows first). Pushing to any other branch runs nothing until you open the pull request. A new workflow file must
follow the same rule (`push: branches: [main]` and `pull_request: branches: [main]`); `tests/test_release_workflow.py` fails otherwise.

`cross-arch.yml` (C core and Python tests on s390x, 32-bit x86 and armv7) follows the same rule. Its s390x and armv7 jobs run under
QEMU and take a few minutes; it also has a manual `workflow_dispatch` trigger, which is how a branch whose pull request does not
target `main` can be tested: `gh workflow run cross-arch.yml --ref <branch>`.
