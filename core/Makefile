# Standalone build of the C core: no Python needed.  `make test` is the default.
CC     ?= cc
OPT    ?= -O2
STD    := -std=c11
WARN   := -Wall -Wextra -Wconversion -Wshadow -Wcast-align -Wstrict-prototypes -Wmissing-prototypes -Werror
CFLAGS += $(STD) $(WARN) $(OPT) -g -Iinclude -Isrc -isystem vendor
LIB    := src/ribbon.c src/rb_hash.c
LDLIBS := -lm
HDRS   := include/ribbon.h src/rb_internal.h
B      := build

.PHONY: test example asan portable nomem coverage fuzz ovh-sweep fpr-report calibrate clean
.DEFAULT_GOAL := test

$(B):
	mkdir -p $(B)

$(B)/test_core: tests/test_core.c $(LIB) $(HDRS) tests/vectors.h | $(B)
	$(CC) $(CFLAGS) $(EXTRA) -o $@ tests/test_core.c $(LIB) $(LDLIBS)

test: $(B)/test_core  ## build and run the unit tests
	./$(B)/test_core

$(B)/basic: examples/basic.c $(LIB) $(HDRS) | $(B)
	$(CC) $(CFLAGS) $(EXTRA) -o $@ examples/basic.c $(LIB) $(LDLIBS)

example: $(B)/basic  ## build and run examples/basic.c
	./$(B)/basic

asan: EXTRA := -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer
asan: OPT := -O1
asan: clean test example

portable: EXTRA := -DRB_PORTABLE=1
portable: clean test

# Allocation-failure tests: tests/test_nomem.c fails the Nth malloc/calloc/realloc by linking with GNU ld's --wrap (Linux).
# Under ASan/UBSan, so a leak or an invalid free on any error path fails the run.
NOMEM_LD := -Wl,--wrap=malloc,--wrap=calloc,--wrap=realloc
$(B)/test_nomem: tests/test_nomem.c $(LIB) $(HDRS) | $(B)
	$(CC) $(CFLAGS) -O1 -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer $(NOMEM_LD) -o $@ tests/test_nomem.c $(LIB) $(LDLIBS)

nomem: $(B)/test_nomem  ## build and run the allocation-failure tests (Linux, GNU ld)
	./$(B)/test_nomem

# Line and branch coverage of src/ with gcov, reported by gcovr (pip install gcovr). Three builds at -O0 with --coverage:
# the unit tests, the same with the portable bit-op fallbacks, and the allocation-failure tests; gcovr merges them.
# COV_MIN=N makes the target fail when total line coverage is below N percent.
GCOVR   ?= gcovr
COV_MIN ?= 0
CB      := $(B)/cov
COVFLAGS = $(CFLAGS) -O0 --coverage
coverage:
	rm -rf $(CB) && mkdir -p $(CB)/default $(CB)/portable $(CB)/nomem
	$(CC) $(COVFLAGS) -o $(CB)/default/test_core tests/test_core.c $(LIB) $(LDLIBS)
	$(CC) $(COVFLAGS) -DRB_PORTABLE=1 -o $(CB)/portable/test_core tests/test_core.c $(LIB) $(LDLIBS)
	$(CC) $(COVFLAGS) $(NOMEM_LD) -o $(CB)/nomem/test_nomem tests/test_nomem.c $(LIB) $(LDLIBS)
	./$(CB)/default/test_core && ./$(CB)/portable/test_core && ./$(CB)/nomem/test_nomem
	$(GCOVR) --root . --filter 'src/' --txt-metric branch --txt --print-summary $(CB)
	$(GCOVR) --root . --filter 'src/' --txt-metric line --txt --print-summary --fail-under-line $(COV_MIN) $(CB)

# Loader fuzzing. With clang this builds a libFuzzer binary; otherwise the built-in mutation driver
# (same harness, deterministic PRNG, under ASan/UBSan) runs for a fixed number of iterations.
FUZZ_ITERS ?= 2000000
fuzz: | $(B)
	@if command -v clang >/dev/null 2>&1 && echo 'int LLVMFuzzerTestOneInput(const unsigned char *d, unsigned long n){(void)d;(void)n;return 0;}' | clang -x c -fsanitize=fuzzer - -o /dev/null 2>/dev/null; then \
	  clang $(STD) -O1 -g -Iinclude -Isrc -isystem vendor -fsanitize=fuzzer,address,undefined fuzz/fuzz_load.c $(LIB) -o $(B)/fuzz_load && \
	  rm -rf $(B)/corpus && mkdir -p $(B)/corpus && cp fuzz/corpus/* $(B)/corpus/ && \
	  ./$(B)/fuzz_load -max_total_time=60 -max_len=4096 $(B)/corpus; \
	else \
	  echo "clang/libFuzzer not found: running the built-in mutation driver"; \
	  $(CC) $(STD) -O1 -g -Iinclude -Isrc -isystem vendor -fsanitize=address,undefined -fno-sanitize-recover=undefined -DFUZZ_DRIVER fuzz/fuzz_load.c $(LIB) -o $(B)/fuzz_driver && \
	  ./$(B)/fuzz_driver $(FUZZ_ITERS); \
	fi

$(B)/sweep: tools/sweep.c $(LIB) $(HDRS) | $(B)
	$(CC) $(CFLAGS) -o $@ tools/sweep.c $(LIB) $(LDLIBS)

ovh-sweep: $(B)/sweep
	./$(B)/sweep

$(B)/fpr: tools/fpr.c $(LIB) $(HDRS) | $(B)
	$(CC) $(CFLAGS) -o $@ tools/fpr.c $(LIB) $(LDLIBS)

fpr-report: $(B)/fpr
	./$(B)/fpr

$(B)/calibrate: tools/calibrate.c src/ribbon.c $(HDRS) | $(B)
	$(CC) $(CFLAGS) -o $@ tools/calibrate.c src/rb_hash.c $(LDLIBS)

calibrate: $(B)/calibrate  ## regenerate the default-overhead table (slow: minutes)
	./$(B)/calibrate 7 24

clean:
	rm -rf $(B)
