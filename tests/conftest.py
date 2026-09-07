import ctypes.util
import os
import sys
import sysconfig
from pathlib import Path

import cocotb_test.simulator as cocotb_simulator
import find_libpython

_ORIG_FIND_LIBPYTHON = find_libpython.find_libpython


def _candidate_libpython_paths():
    libdir = sysconfig.get_config_var("LIBDIR")
    for key in ("LDLIBRARY", "INSTSONAME", "LIBRARY"):
        libname = sysconfig.get_config_var(key)
        if libdir and libname:
            yield Path(libdir) / libname

    major = sys.version_info.major
    minor = sys.version_info.minor
    for soname in (f"python{major}.{minor}", f"python{major}{minor}", "python3"):
        lib = ctypes.util.find_library(soname)
        if not lib:
            continue

        found = Path(lib)
        if found.is_absolute():
            yield found
            continue

        search_dirs = []
        if libdir:
            search_dirs.append(Path(libdir))
        search_dirs.extend(
            Path(path)
            for path in (
                "/usr/lib/x86_64-linux-gnu",
                "/usr/lib/aarch64-linux-gnu",
                "/usr/lib64",
                "/usr/lib",
                "/lib/x86_64-linux-gnu",
                "/lib/aarch64-linux-gnu",
                "/lib64",
                "/lib",
            )
        )

        for directory in search_dirs:
            yield directory / lib


def _safe_find_libpython():
    try:
        libpython = _ORIG_FIND_LIBPYTHON()
    except Exception:
        libpython = None
    if libpython:
        return libpython

    for candidate in _candidate_libpython_paths():
        if candidate.is_file():
            return str(candidate.resolve())

    # cocotb-test pushes this value into subprocess env; avoid NoneType crashes.
    return ""


find_libpython.find_libpython = _safe_find_libpython
cocotb_simulator.find_libpython.find_libpython = _safe_find_libpython


def pytest_configure(config):
    """Keep simulator subprocesses on the same Python as pytest."""
    python_dir = str(Path(sys.executable).resolve().parent)
    path = os.environ.get("PATH")
    entries = path.split(os.pathsep) if path else []
    if python_dir not in entries:
        os.environ["PATH"] = os.pathsep.join([python_dir, *entries])
    os.environ.setdefault("PYTHON3", sys.executable)
