"""A core built with another BOOT_ADDR starts there after reset."""

import cocotb

from cpu_program import INSTR_MEM_BASE, NOP, PARK, run_program, run_tests

BOOT_ADDR = INSTR_MEM_BASE + 0x100


@cocotb.test()
async def test_starts_at_boot_address(dut):
    """The code at the RAM base sets x5 = 1, the code at BOOT_ADDR sets x5 = 2."""
    boot_index = (BOOT_ADDR - INSTR_MEM_BASE) // 4
    instr_mem = [
        0x00100293,  # addi x5, x0, 1
        PARK,
    ]
    instr_mem += [NOP] * (boot_index - len(instr_mem))
    instr_mem += [
        0x00200293,  # addi x5, x0, 2
    ]
    await run_program(dut, instr_mem)
    x5 = int(dut.cpu_inst.rf_inst0.register_file[5].value)
    assert x5 == 2, f"x5 = {x5}: the core did not start at BOOT_ADDR {BOOT_ADDR:#x}"


def runCocotbTests():
    run_tests("test_boot_address", ["test_starts_at_boot_address"], parameters={"BOOT_ADDR": BOOT_ADDR})


if __name__ == "__main__":
    runCocotbTests()
