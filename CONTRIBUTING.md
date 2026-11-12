# Contributing

```bash
make venv          # create .venv
make install-dev   # editable install with dev tools (builds the C extension)
make check         # lint, docstyle, mypy + stubtest, C tests, Python tests
```

The C core (`core/`) builds and tests without Python: `make c-test`, `make c-asan`, `make c-portable`.
C code must compile with `-std=c11 -Wall -Wextra -Wconversion -Werror`. Algorithmic changes need a citation to the
Ribbon papers (see `RESEARCH.md`); do not copy code from RocksDB, fastfilter_cpp, BuRR or other implementations.
