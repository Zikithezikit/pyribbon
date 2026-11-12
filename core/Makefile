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

.PHONY: test asan portable fuzz ovh-sweep fpr-report calibrate clean
.DEFAULT_GOAL := test

$(B):
	mkdir -p $(B)

$(B)/test_core: tests/test_core.c $(LIB) $(HDRS) tests/vectors.h | $(B)
	$(CC) $(CFLAGS) $(EXTRA) -o $@ tests/test_core.c $(LIB) $(LDLIBS)

test: $(B)/test_core  ## build and run the unit tests
	./$(B)/test_core

asan: EXTRA := -fsanitize=address,undefined -fno-sanitize-recover=undefined -fno-omit-frame-pointer
asan: OPT := -O1
asan: clean test

portable: EXTRA := -DRB_PORTABLE=1
portable: clean test

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
