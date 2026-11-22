"""The cycle counter, and user-mode reads of it enabled by mcounteren and scounteren."""

import cocotb

from support import run_program, run_tests


@cocotb.test()
async def test_csr_cycle_counter(dut):
    """Test cycle counter CSRs"""
    print("Starting cycle counter CSR test...")
    
    # Program to test cycle counter:
    instr_mem = [
        # Read cycle counter at different times
        0xc0002073,  # csrrs x0, cycle, x0     # Read cycle (no change)
        0xc0002173,  # csrrs x2, cycle, x0     # x2 = cycle low
        0xc8002273,  # csrrs x4, cycleh, x0    # x4 = cycle high
        
        # Add some NOPs to advance cycle counter
        0x00000013,  # nop
        0x00000013,  # nop
        0x00000013,  # nop
        
        # Read cycle counter again
        0xc0002373,  # csrrs x6, cycle, x0     # x6 = cycle low (later)
        0xc8002473,  # csrrs x8, cycleh, x0    # x8 = cycle high (later)
    ]

    await run_program(dut, instr_mem)
    
    # Verify that cycle counter is advancing
    cycle_low_1 = int(dut.cpu_inst.rf_inst0.register_file[2].value)
    cycle_high_1 = int(dut.cpu_inst.rf_inst0.register_file[4].value)
    cycle_low_2 = int(dut.cpu_inst.rf_inst0.register_file[6].value)
    cycle_high_2 = int(dut.cpu_inst.rf_inst0.register_file[8].value)
    
    print(f"First cycle read: low={cycle_low_1:#x}, high={cycle_high_1:#x}")
    print(f"Second cycle read: low={cycle_low_2:#x}, high={cycle_high_2:#x}")
    
    # Cycle counter should have advanced
    assert cycle_low_2 > cycle_low_1, "Cycle counter should have advanced"
    
    print("Cycle counter CSR test passed!")


@cocotb.test()
async def test_counteren_allows_user_cycle_read(dut):
    """Machine mode can enable user-mode cycle reads via mcounteren/scounteren."""
    print("Starting counteren user-cycle access test...")

    instr_mem = [
        0x00100093,  # addi  x1, x0, 1
        0x30609073,  # csrrw x0, mcounteren, x1
        0x10609073,  # csrrw x0, scounteren, x1
        0x30602173,  # csrrs x2, mcounteren, x0
        0x106021F3,  # csrrs x3, scounteren, x0
        0x80000237,  # lui   x4, 0x80000
        0x03020213,  # addi  x4, x4, 0x30       -> the cycle read below
        0x34121073,  # csrrw x0, mepc, x4
        0x000022B7,  # lui   x5, 0x2
        0x80028293,  # addi  x5, x5, -2048      -> 0x1800
        0x3002B073,  # csrrc x0, mstatus, x5    -> MPP=U
        0x30200073,  # mret
        0xC0002373,  # csrrs x6, cycle, x0      -> user-mode cycle read
        0x07700393,  # addi  x7, x0, 0x77
        0x0000006F,  # jal   x0, 0
    ]

    await run_program(dut, instr_mem)

    x2 = int(dut.cpu_inst.rf_inst0.register_file[2].value)
    x3 = int(dut.cpu_inst.rf_inst0.register_file[3].value)
    x6 = int(dut.cpu_inst.rf_inst0.register_file[6].value)
    x7 = int(dut.cpu_inst.rf_inst0.register_file[7].value)
    privilege_mode = int(dut.cpu_inst.csr_file_inst.privilege_mode.value)
    mcounteren = int(dut.cpu_inst.csr_file_inst.mcounteren.value)
    scounteren = int(dut.cpu_inst.csr_file_inst.scounteren.value)

    print(
        f"x2={x2:#x}, x3={x3:#x}, x6={x6:#x}, x7={x7:#x}, "
        f"priv={privilege_mode:#x}, mcounteren={mcounteren:#x}, scounteren={scounteren:#x}"
    )

    assert x2 == 0x1, f"Expected mcounteren readback 0x1, got {x2:#x}"
    assert x3 == 0x1, f"Expected scounteren readback 0x1, got {x3:#x}"
    assert x6 != 0x0, "Expected user-mode cycle read to succeed with a non-zero value"
    assert x7 == 0x77, f"Expected user payload to continue after cycle read, got {x7:#x}"
    assert privilege_mode == 0x0, f"Expected U-mode after mret, got {privilege_mode:#x}"
    assert mcounteren == 0x1, f"Expected mcounteren=0x1, got {mcounteren:#x}"
    assert scounteren == 0x1, f"Expected scounteren=0x1, got {scounteren:#x}"

    print("Counteren user-cycle access test passed!")


def runCocotbTests():
    run_tests("test_counters", [
        "test_csr_cycle_counter",
        "test_counteren_allows_user_cycle_read",
    ])


if __name__ == "__main__":
    runCocotbTests()
