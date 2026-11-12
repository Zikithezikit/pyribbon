VENV ?= .venv
BIN  := $(VENV)/bin
PY   := $(BIN)/python

.DEFAULT_GOAL := help
.PHONY: help venv install-dev test pytest example c-test c-asan c-portable c-fuzz ovh-sweep fpr-report stats figures calibrate lint format docstyle typecheck check bench build clean

help:  ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

venv:  ## Create .venv
	python3 -m venv $(VENV)
	$(BIN)/pip install --upgrade pip

install-dev:  ## Install in editable mode with dev tools (builds the C extension)
	$(BIN)/pip install -e '.[dev]'

test: c-test pytest  ## C unit tests, then the Python tests

pytest:  ## Run the Python test suite (add ARGS="-m 'not slow'" to skip the statistical tests)
	$(BIN)/pytest $(ARGS)

example:  ## Run every script in examples/
	@for f in examples/*.py; do echo "== $$f"; $(PY) $$f || exit 1; done

c-test:  ## Build and run the C core unit tests (no Python needed)
	$(MAKE) -C core test

c-asan:  ## C core tests under AddressSanitizer and UBSan
	$(MAKE) -C core asan

c-portable:  ## C core tests with the portable bit-op fallbacks forced
	$(MAKE) -C core portable

c-fuzz:  ## Fuzz the buffer loader (libFuzzer with clang, otherwise the built-in mutator)
	$(MAKE) -C core fuzz

ovh-sweep:  ## Measure construction failure rate vs overhead with the real core
	$(MAKE) -C core ovh-sweep

fpr-report:  ## Measure the false-positive rate against 2^-r with millions of probes
	$(MAKE) -C core fpr-report

stats:  ## Run the statistical tests (slow) and write docs/measurements.{json,md}
	PYRIBBON_STATS_OUT=docs/measurements.json $(BIN)/pytest -m slow -s tests/test_statistics.py
	$(PY) benchmarks/render_measurements.py docs/measurements.json docs/measurements.md
	$(MAKE) figures

figures:  ## Redraw the README figures (docs/img) from the saved benchmark and measurement results
	$(BIN)/pip install -q -e '.[bench]'
	$(PY) benchmarks/make_figures.py

calibrate:  ## Regenerate the default-overhead table from the real core (slow)
	$(MAKE) -C core calibrate

lint:  ## Lint and check formatting
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format:  ## Auto-fix lint issues and format code
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

docstyle:  ## Check Google-style docstrings
	$(BIN)/ruff check --select D src examples

typecheck:  ## Run mypy (strict) and stubtest against the compiled module
	$(BIN)/mypy
	$(PY) -m mypy.stubtest pyribbon --allowlist stubtest-allowlist.txt

check: lint docstyle typecheck test  ## Everything CI runs

bench:  ## Run the benchmarks (use an idle machine); writes docs/benchmark.png, .md and .json
	$(BIN)/pip install -q -e '.[bench]'
	$(PY) benchmarks/bench.py --plot docs/benchmark.png --table docs/benchmark.md --json docs/benchmark.json
	$(MAKE) figures

build:  ## Build sdist + wheel and validate them
	rm -rf dist
	$(PY) -m build
	$(BIN)/twine check dist/*

clean:  ## Remove build and cache files
	$(MAKE) -C core clean
	rm -rf dist build *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache .hypothesis .coverage wheelhouse
	rm -f src/pyribbon/*.so src/pyribbon/*.pyd
	find . -name __pycache__ -not -path './.venv/*' -prune -exec rm -rf {} +
