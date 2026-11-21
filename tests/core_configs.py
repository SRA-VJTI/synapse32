"""Core configurations the riscv-tests and riscv-arch-test also run under, each setting some of top's parameters.

`compare_with_spike.py --config NAME` builds one; the ISA workflow runs each."""

MATRIX = {
    "no_caches": {"ICACHE_ENABLE": 0, "DCACHE_ENABLE": 0},
    "one_way": {"ICACHE_WAYS": 1, "DCACHE_WAYS": 1},
    "long_lines": {"ICACHE_WORD_OFFSET_BITS": 3, "DCACHE_WORD_OFFSET_BITS": 3},
    "one_mshr": {"NUM_MSHR": 1},
    "small_buffers": {"STORE_BUFFER_DEPTH": 1, "TLB_ENTRIES": 1},
}
