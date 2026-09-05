"""
same as the cache_tb_v.v in the tb/ folder only with cocotb format

Run:
    pytest system_tests/test_cache.py -s -v
    WAVES=1 pytest system_tests/test_cache.py -s -v
"""

import cocotb
from cocotb.triggers import RisingEdge, ClockCycles
from cocotb.clock import Clock
from cocotb_test.simulator import run
import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Parameters — must match runCocotbTests()
# ---------------------------------------------------------------------------
MEM_SIZE        = 1048576
CACHE_SIZE      = 1024
SETS            = 256
ADDRESS_WIDTH   = 32
DATA_WIDTH      = 32
TAG_WIDTH       = 18
SET_WIDTH       = 8
OFFSET_WIDTH    = 4
WAY             = 4
BYTE_OFFSET     = 2
WORDS_PER_BLOCK = 16
BYTES_PER_WORD  = 4
CLK_PERIOD      = 10   


@cocotb.test()
async def test_cache_fsm(dut):
    """
    Full port of cache_fsm_tb.sv.
    Tests: full-word write/read, byte-enable, sign-extension,
           way filling, LRU eviction, writeback, re-read from main memory.
    """

    # Start clock
    clock = Clock(dut.clk, CLK_PERIOD, units="ns")
    cocotb.start_soon(clock.start())

    # -------------------------------------------------------------------
    # Reset — mirrors: reset=1; repeat(2)@posedge; reset=0
    # -------------------------------------------------------------------
    dut.reset.value              = 1
    dut.write_en.value           = 0
    dut.read_en.value            = 0
    dut.data_in.value            = 0
    dut.mem_add.value            = 0
    dut.write_bytes_enable.value = 0
    dut.load_type.value          = 0
    await ClockCycles(dut.clk, 2)
    dut.reset.value = 0

    # ===================================================================
    # TEST 1 – full-word write + read back
    # ===================================================================
    print("\n##########################################")
    print("  TEST 1: full-word write + read back")
    print("  addr=0x0000_00F0  data=0xFBFC_FDFE  be=1111")
    print("##########################################")

    dut.write_bytes_enable.value = 0b1111
    dut.mem_add.value            = 0x000000F0
    dut.data_in.value            = 0xFBFCFDFE
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    await RisingEdge(dut.clk)
    dut.write_en.value = 0
    await ClockCycles(dut.clk, 8)

    dut.load_type.value = 0b010   # LW
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 3)
    dut.read_en.value = 0


    # ===================================================================
    # TEST 2 – byte-enable write (be=0001) + unsigned byte read (LBU)
    # ===================================================================
    print("\n##########################################")
    print("  TEST 2: byte write (be=0001) + unsigned byte read")
    print("  addr=0x0000_00F3  data[7:0]=0xFF  load_type=100 (LBU)")
    print("##########################################")

    dut.write_bytes_enable.value = 0b0001
    dut.mem_add.value            = 0b00000000000000000000000011110011
    dut.data_in.value            = 0x000000FF
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    await RisingEdge(dut.clk)
    dut.write_en.value = 0
    await ClockCycles(dut.clk, 8)

    dut.load_type.value = 0b100   # LBU
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 2)
    dut.read_en.value = 0

    # ===================================================================
    # TEST 3 – signed byte read (same address, load_type=000 LB)
    # ===================================================================
    print("\n##########################################")
    print("  TEST 3: signed byte read (same addr)")
    print("  load_type=000 (LB)  expect sign-extended 0xFF -> 0xFFFFFFFF")
    print("##########################################")

    dut.load_type.value = 0b000   # LB
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 3)
    dut.read_en.value = 0

    try:
        data_out = int(dut.data_out.value)
    except Exception:
        data_out = 0
    print(f"  data_out after LB = 0x{data_out:08x}  (expect 0xFFFFFFFF)")

    # ===================================================================
    # TEST 4 – fill all 4 ways
    # ===================================================================
    print("\n##########################################")
    print("  TEST 4: fill all ways (3 more writes to same set)")
    print("##########################################")

    # --- 4a ---
    dut.write_bytes_enable.value = 0b1111
    dut.mem_add.value            = 0x0F0000F0
    dut.data_in.value            = 0xABABFDFE
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    await RisingEdge(dut.clk)
    dut.write_en.value = 0
    await ClockCycles(dut.clk, 8)

    dut.load_type.value = 0b010
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 3)
    dut.read_en.value = 0

    print("  [4a] after write 0x0F00_00F0:")

    # --- 4b ---
    dut.write_bytes_enable.value = 0b1111
    dut.mem_add.value            = 0x0D0000F0
    dut.data_in.value            = 0xFBFCABAB
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    await RisingEdge(dut.clk)
    dut.write_en.value = 0
    await ClockCycles(dut.clk, 8)

    dut.load_type.value = 0b010
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 3)
    dut.read_en.value = 0

    print("  [4b] after write 0x0D00_00F0:")

    # --- 4c (halfword enable be=0011) ---
    dut.write_bytes_enable.value = 0b0011
    dut.mem_add.value            = 0x0B0000F0
    dut.data_in.value            = 0xFBABABFE
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    await RisingEdge(dut.clk)
    dut.write_en.value = 0
    await ClockCycles(dut.clk, 8)

    dut.load_type.value = 0b010
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 3)
    dut.read_en.value = 0

    print("  [4c] after write 0x0B00_00F0 (all 4 ways now full):")

    # ===================================================================
    # TEST 5 – force LRU eviction + writeback + re-read from main memory
    # ===================================================================
    print("\n##########################################")
    print("  TEST 5: eviction + writeback + re-read from main memory")
    print("  new write  addr=0x0900_00F0  data=0xDEAD_BEAD")
    print("  expect LRU victim written back to main memory")
    print("  then re-read 0x0D00_00F0 -> expect 0xFBFC_ABAB")
    print("##########################################")

    dut.write_bytes_enable.value = 0b1111
    dut.mem_add.value            = 0x090000F0
    dut.data_in.value            = 0xDEADBEAD
    await RisingEdge(dut.clk)
    dut.write_en.value = 1
    await RisingEdge(dut.clk)
    dut.write_en.value = 0
    await ClockCycles(dut.clk, 8)

    dut.load_type.value = 0b010
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 3)
    dut.read_en.value = 0


    # Re-read evicted address — mirrors: mem_add=0x0D00_00F0; read_en=1; repeat(10)
    dut.mem_add.value   = 0x0D0000F0
    dut.load_type.value = 0b010
    dut.read_en.value   = 1
    await ClockCycles(dut.clk, 10)

    try:
        data_out = int(dut.data_out.value)
    except Exception:
        data_out = 0
    print(f"  [5b] re-read 0x0D00_00F0 (from main mem after eviction):")
    print(f"       data_out = 0x{data_out:08x}  (expect 0xFBFC_ABAB)")

    assert data_out == 0xFBFCABAB, \
        f"TEST5 re-read: expected 0xFBFCABAB, got 0x{data_out:08x}"

    print("\nAll tests completed successfully.")


# ---------------------------------------------------------------------------
# pytest entry point
# ---------------------------------------------------------------------------
def runCocotbTests():
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        parent = os.path.dirname(root_dir)
        if parent == root_dir:
            raise FileNotFoundError("rtl directory not found")
        root_dir = parent

    rtl_dir  = Path(root_dir) / "rtl"
    incl_dir = rtl_dir / "include"
    sources  = [str(rtl_dir / "cache_fsm.v")]

    enable_waves = os.getenv("WAVES", "0") == "1"
    wave_dir = Path(os.getcwd()) / "waveforms"
    plus_args = []
    if enable_waves:
        wave_dir.mkdir(exist_ok=True)
        plus_args = [f"+dumpfile={wave_dir / 'cache_fsm_test.vcd'}"]

    print("\n" + "="*60)
    print("  Running: test_cache_fsm")
    print("="*60)

    run(
        verilog_sources=sources,
        toplevel="cache_fsm",
        module="test_cache",
        testcase="test_cache_fsm",
        includes=[str(incl_dir)],
        simulator="verilator",
        timescale="1ns/1ps",
        plus_args=plus_args,
        extra_env={"COCOTB_LOG_LEVEL": "INFO"},
        compile_args=["-Wno-WIDTHTRUNC", "-Wno-WIDTHEXPAND", "-Wno-fatal"],
        parameters={
            "MEM_SIZE":        MEM_SIZE,
            "CACHE_SIZE":      CACHE_SIZE,
            "SETS":            SETS,
            "ADDRESS_WIDTH":   ADDRESS_WIDTH,
            "DATA_WIDTH":      DATA_WIDTH,
            "TAG_WIDTH":       TAG_WIDTH,
            "SET_WIDTH":       SET_WIDTH,
            "OFFSET_WIDTH":    OFFSET_WIDTH,
            "WAY":             WAY,
            "BYTE_OFFSET":     BYTE_OFFSET,
            "WORDS_PER_BLOCK": WORDS_PER_BLOCK,
            "BYTES_PER_WORD":  BYTES_PER_WORD,
        },
    )


if __name__ == "__main__":
    runCocotbTests()