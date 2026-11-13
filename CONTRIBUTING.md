# Contributing

```bash
make venv          # create .venv
make install-dev   # editable install with dev tools (builds the C extension)
make check         # lint, docstyle, mypy + stubtest, C tests, Python tests
make example       # run every script in examples/ (a test also runs them)
```

To run the lint and format checks before every commit, install the hooks once with `pip install pre-commit && pre-commit install`.
They run `ruff check` and `ruff format` with the settings in `pyproject.toml`, and `.editorconfig` sets the indentation
(4 spaces in Python, 2 in C, YAML and TOML, tabs in Makefiles). Open a pull request from a branch; the template lists what to
check. Bugs and feature requests have issue templates. Vulnerabilities do not go in issues: see `SECURITY.md`. Dependabot
sends weekly updates for the GitHub Actions the workflows use.

New examples go in `examples/` with the next number (`08_...py`) and a docstring that says how to run it. `tests/test_examples.py`
runs each script, and `tests/test_readme.py` checks that the README lists it.

The C core (`core/`) builds and tests without Python, using `make c-test`, `make c-asan` and `make c-portable`.
C code must compile with `-std=c11 -Wall -Wextra -Wconversion -Werror`. A change to the algorithm needs a citation to
the Ribbon papers (see `RESEARCH.md`). Do not copy code from RocksDB, fastfilter_cpp, BuRR or other implementations.

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
