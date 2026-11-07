"""Core configurations the regression runs besides the default: each one sets some of top's parameters."""

import os

MATRIX = {
    "no_caches": {"ICACHE_ENABLE": 0, "DCACHE_ENABLE": 0},
    "one_way": {"ICACHE_WAYS": 1, "DCACHE_WAYS": 1},
    "long_lines": {"ICACHE_WORD_OFFSET_BITS": 3, "DCACHE_WORD_OFFSET_BITS": 3},
    "one_mshr": {"NUM_MSHR": 1},
    "small_buffers": {"STORE_BUFFER_DEPTH": 1, "TLB_ENTRIES": 1},
}

# Every parameter the matrix changes, at top's default (keep equal to rtl/top.v).
DEFAULT_CORE = {
    "ICACHE_ENABLE": 1, "ICACHE_WAYS": 4, "ICACHE_SET_INDEX_BITS": 6, "ICACHE_WORD_OFFSET_BITS": 2,
    "DCACHE_ENABLE": 1, "DCACHE_WAYS": 4, "DCACHE_SET_INDEX_BITS": 6, "DCACHE_WORD_OFFSET_BITS": 2,
    "NUM_MSHR": 8, "STORE_BUFFER_DEPTH": 4, "TLB_ENTRIES": 8,
}


def default_caches() -> bool:
    """Both caches are enabled at their default ways, sets and line size (the MSHR count, store buffer depth and TLB
    size may differ). Cycle counts that depend on line fills and fetch alignment are checked only then; functional
    checks run in every build."""
    core = current()
    return all(core[name] == value for name, value in DEFAULT_CORE.items() if name.startswith(("ICACHE_", "DCACHE_")))


def _built() -> dict:
    """The matrix parameters this simulation was built with (conftest passes them in CORE_PARAMETERS)."""
    parameters = decode(os.environ.get("CORE_PARAMETERS", ""))
    return {name: parameters.get(name, value) for name, value in DEFAULT_CORE.items()}


def configured(parameters: dict) -> dict:
    """On the pytest side: the matrix parameters a build of top with these parameters of its own gets."""
    config = os.environ.get("CORE_CONFIG")
    applied = {**(MATRIX[config] if config else {}), **parameters}
    return {name: applied.get(name, value) for name, value in DEFAULT_CORE.items()}


def current() -> dict:
    """The matrix parameters of this run: the build's inside a simulation, the configured ones on the pytest side."""
    return _built() if "CORE_PARAMETERS" in os.environ else configured({})


def encode(parameters: dict) -> str:
    return ",".join(f"{name}={value}" for name, value in parameters.items())


def decode(text: str) -> dict:
    return {name: int(value, 0) for name, value in (item.split("=", 1) for item in text.split(",") if item)}
