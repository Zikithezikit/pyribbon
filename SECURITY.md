# Security policy

## Supported versions

Only the latest 0.1.x release gets security fixes. Older and unreleased versions do not.

## Reporting a vulnerability

Please do not open a public issue for a vulnerability. Use GitHub's private vulnerability reporting instead: on the
repository page, open the Security tab and choose "Report a vulnerability". Include the pyribbon version, the Python
version and platform, and a minimal reproduction (for a loader bug, the bytes that trigger it).

pyribbon has one maintainer, who does this in spare time. Expect an acknowledgement within about a week and a first
assessment within about two weeks. There is no fixed fix date. A confirmed issue gets a fix in a new release and a
published advisory, and the reporter is credited unless they prefer not to be.

## What is in scope

* Loading untrusted bytes. `RibbonFilter.from_buffer` and unpickling parse a serialized filter. A crash, an
  out-of-bounds read, an unbounded allocation or an accepted-but-inconsistent filter from a crafted buffer is a
  vulnerability.
* The C extension handling arbitrary Python objects. Keys, key iterables and buffers come from the caller, who can pass
  anything. A crash, a memory error or a leak triggered by an odd object (a buffer that changes during a call, an
  iterable that raises, a huge integer) is a vulnerability.
* The vendored hash code and the build and release workflows.

## What is not in scope

* Wrong query answers from a corrupted payload loaded with `verify=False`. The loader skips the payload checksum in that
  mode and the docs say so.
* Tampering. The checksums catch accidents, they are not a MAC. Authenticate files you do not trust.
* Unpickling data you do not trust. Like any pickle, it can run arbitrary code regardless of this library. Load untrusted
  files with `from_buffer`.
* A memory-mapped file that another process truncates while it is mapped. The operating system faults on access (SIGBUS)
  and no library can prevent that.
* False positives at the chosen rate, and hash-flooding by an attacker who knows the seed. A ribbon filter is not a
  security boundary.

## Existing hardening

The loader checks a fixed sequence of rules in a fixed order, and the unverified path still runs every O(1) rule, so it
cannot read out of bounds. It copies the 64 header bytes before parsing them. The sequence is in
[docs/internals.md](docs/internals.md) section 5. Section 7 of the same file lists the tests and the CI jobs: a
differential fuzz of the loader against an independent Python reference, hand-crafted hostile headers, libFuzzer on the
loader under ASan and UBSan, ASan and UBSan runs of the C tests and the extension, and a `-Werror` build with `-Wconversion`.
