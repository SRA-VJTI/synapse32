"""An access to a CSR that does not exist traps as an illegal instruction."""

import cocotb

from support import INSTR_MEM_BASE, NOP, run_program, run_tests


@cocotb.test()
async def test_csr_invalid_access(dut):
    """Test access to invalid CSR addresses"""
    print("Starting invalid CSR access test...")
    
    # Program to test invalid CSR access:
    instr_mem = [
        # Try to access an invalid CSR (address 0x123)
        0x12302173,  # csrrs x2, 0x123, x0    # Illegal instruction: x2 is not written
        
        # Never reached: the access above traps
        0x34002273,  # csrrs x4, mscratch, x0
    ]

    # The access to 0x123 traps (mcause 2) and ends the program.
    await run_program(dut, instr_mem, done=lambda dut: int(dut.cpu_inst.csr_file_inst.mcause.value) == 2)
    
    # The trapping CSR access must not write x2
    invalid_csr_value = int(dut.cpu_inst.rf_inst0.register_file[2].value)
    print(f"Invalid CSR read: {invalid_csr_value:#x}")
    
    assert invalid_csr_value == 0, "Illegal CSR access wrote x2"

    print("Invalid CSR access test passed!")


@cocotb.test()
async def test_m_mode_illegal_csr_probe_pattern(dut):
    """OpenSBI-style CSR probe: swap mtvec, probe unknown CSR, restore mtvec.

    OpenSBI probes optional CSRs (e.g. the AIA CSRs) by installing a temporary
    mtvec, attempting the access, and relying on the trap handler to advance
    mepc+4 and mret back. The probed CSR must be one this core does not
    implement: mtopi/0xFB0 reads as 0 here (see csr_valid in csr_file.v), so
    this probes mtopei/0x35C, which is absent from csr_valid and therefore
    raises an illegal-instruction trap. Verifies the full round-trip: trap → probe handler →
    mret → M-mode execution resumes at the instruction after the probe.
    """
    print("Starting M-mode illegal CSR probe pattern test...")

    instr_mem = [NOP] * 32

    # 0x00: lui x1, 0x80000
    instr_mem[0] = 0x800000B7
    # 0x04: addi x1, x1, 0x50          # probe handler address
    instr_mem[1] = 0x05008093
    # 0x08: csrrw x2, mtvec, x1        # save old mtvec in x2, install probe handler
    instr_mem[2] = 0x30509173
    # 0x0C: csrr x0, 0x35C             # probe mtopei (AIA ext, unimplemented → illegal instr)
    instr_mem[3] = 0x35C02073
    # 0x10: csrw mtvec, x2             # restore mtvec (reached after probe mret)
    instr_mem[4] = 0x30511073
    # 0x14: addi x5, x0, 0xAA         # sentinel: probe handled, execution continued
    instr_mem[5] = 0x0AA00293
    # 0x18: jal x0, 0                  # hang
    instr_mem[6] = 0x0000006F

    # Probe handler at 0x50 (word 20):
    # 0x50: csrrs x3, mepc, x0         # x3 = faulting PC
    instr_mem[20] = 0x341021F3
    # 0x54: addi x3, x3, 4             # advance past probe instruction
    instr_mem[21] = 0x00418193
    # 0x58: csrrw x0, mepc, x3         # mepc = probe PC + 4
    instr_mem[22] = 0x34119073
    # 0x5C: mret
    instr_mem[23] = 0x30200073

    await run_program(dut, instr_mem)

    x3 = int(dut.cpu_inst.rf_inst0.register_file[3].value)
    x5 = int(dut.cpu_inst.rf_inst0.register_file[5].value)
    mcause = int(dut.cpu_inst.csr_file_inst.mcause.value)
    privilege_mode = int(dut.cpu_inst.csr_file_inst.privilege_mode.value)

    print(f"x3 (probe handler observed mepc + 4): {x3:#x}")
    print(f"x5 (post-probe sentinel): {x5:#x}")
    print(f"mcause={mcause:#x}, privilege_mode={privilege_mode:#x}")

    assert mcause == 0x2, f"Expected illegal instruction mcause=2 from CSR probe, got {mcause:#x}"
    assert x3 == INSTR_MEM_BASE + 0x10, \
        f"Probe handler must observe mepc + 4, got {x3:#x}"
    assert x5 == 0xAA, \
        f"Execution must continue after probe mret: sentinel missing (x5={x5:#x})"
    assert privilege_mode == 0x3, \
        f"Must remain in M-mode after probe mret, got {privilege_mode:#x}"

    print("M-mode illegal CSR probe pattern test passed!")


def runCocotbTests():
    run_tests("test_invalid_csr", [
        "test_csr_invalid_access",
        "test_m_mode_illegal_csr_probe_pattern",
    ])


if __name__ == "__main__":
    runCocotbTests()
