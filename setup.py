"""Build script for the C extension (all project metadata lives in pyproject.toml)."""

import sys
import sysconfig

from setuptools import Extension, setup

# The extension uses the limited API (one abi3 wheel for CPython 3.11+) where it can:
#  - Py_buffer joined the stable ABI in 3.11, so 3.10 builds against the full API from the same source;
#  - free-threaded CPython has no abi3 before 3.15, so those builds are full-API too.
limited = (
    sys.implementation.name == "cpython"
    and sys.version_info >= (3, 11)
    and not sysconfig.get_config_var("Py_GIL_DISABLED")
)

extension = Extension(
    "pyribbon._ribbon",
    sources=["src/pyribbon/_ribbon.c", "core/src/ribbon.c", "core/src/rb_hash.c"],
    include_dirs=["core/include", "core/src", "core/vendor"],
    define_macros=[("Py_LIMITED_API", "0x030b0000")] if limited else [],
    extra_compile_args=["/std:c11"] if sys.platform == "win32" else [],
    py_limited_api=limited,
)

setup(
    ext_modules=[extension],
    options={"bdist_wheel": {"py_limited_api": "cp311"}} if limited else {},
)
