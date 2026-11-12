# Contributing

```bash
make venv          # create .venv
make install-dev   # editable install with dev tools (builds the C extension)
make check         # lint, docstyle, mypy + stubtest, C tests, Python tests
make example       # run every script in examples/ (a test also runs them)
```

New examples go in `examples/` with the next number (`08_...py`) and a docstring that says how to run it. `tests/test_examples.py`
runs each script, and `tests/test_readme.py` checks that the README lists it.

The C core (`core/`) builds and tests without Python, using `make c-test`, `make c-asan` and `make c-portable`.
C code must compile with `-std=c11 -Wall -Wextra -Wconversion -Werror`. A change to the algorithm needs a citation to
the Ribbon papers (see `RESEARCH.md`). Do not copy code from RocksDB, fastfilter_cpp, BuRR or other implementations.
