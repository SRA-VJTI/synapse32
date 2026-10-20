"""Memory as the program's loads would see it. The data cache is write-back, so RAM alone can be stale: a read
takes a valid cache line, else a dirty line being written back, else RAM with pending MSHR bytes on top."""

INSTR_MEM_BASE = 0x8000_0000
INSTR_MEM_WORDS = 0x0400_0000 // 4
DATA_MEM_BASE = 0x1000_0000

# dcache.v engine states
E_EVICT_READ = 3
E_EVICT_WRITE = 4


def _phys_addr(index: int) -> int:
    if index < INSTR_MEM_WORDS:
        return INSTR_MEM_BASE + 4 * index
    return DATA_MEM_BASE + 4 * (index - INSTR_MEM_WORDS)


def _locate(cache, index: int):
    """The word's data-array row, set, tag, line address and word in line, and the way holding it or None."""
    sets = len(cache.tag_mem)
    way_words = len(cache.data_mem)
    words = way_words // sets
    ways = len(cache.data_rd_q) // 32
    tag_bits = 30 - (way_words.bit_length() - 1)
    addr = _phys_addr(index)
    row = (addr >> 2) % way_words
    set_index = row // words
    tag = addr >> (32 - tag_bits)
    line = addr >> (2 + (words.bit_length() - 1))
    valid = int(cache.valid_q.value)
    tags = int(cache.tag_mem[set_index].value)
    way = None
    for w in range(ways):
        if (valid >> (w * sets + set_index)) & 1 and ((tags >> (tag_bits * w)) & ((1 << tag_bits) - 1)) == tag:
            way = w
    return row, set_index, tag, line, row % words, way


def _lane(row: int, way: int) -> int:
    return (row >> (32 * way)) & 0xFFFF_FFFF


def read_word(dut, index: int) -> int:
    """The word at backing-memory word index `index` (the RAM array's index)."""
    word = int(dut.unified_mem_inst.instr_ram[index].value) & 0xFFFF_FFFF
    try:
        cache = dut.dcache_inst
    except AttributeError:
        return word
    row, set_index, tag, line, word_in_line, way = _locate(cache, index)
    if way is not None:
        return _lane(int(cache.data_mem[row].value), way)
    if (int(cache.eng_state.value) in (E_EVICT_READ, E_EVICT_WRITE) and not int(cache.eng_clean.value) and
            int(cache.eng_set.value) == set_index and int(cache.eng_tag.value) == tag):
        return _lane(int(cache.data_mem[row].value), int(cache.eng_way.value))
    for i in range(int(cache.mshr_count.value)):
        if int(cache.mshr_line_q[i].value) != line:
            continue
        be = int(cache.mshr_be_q[i].value) >> (4 * word_in_line)
        data = int(cache.mshr_data_q[i].value) >> (32 * word_in_line)
        for byte in range(4):
            if (be >> byte) & 1:
                mask = 0xFF << (8 * byte)
                word = (word & ~mask) | (data & mask)
    return word & 0xFFFF_FFFF

