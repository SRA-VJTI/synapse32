"""Trap entry and return across privilege modes: ECALL from S to M and MRET back, and MPP on a trap."""

import cocotb

from support import INSTR_MEM_BASE, NOP, run_program, run_tests


@cocotb.test()
async def test_supervisor_ecall_machine_mret_returns_to_supervisor(dut):
    """Test S-mode ECALL handled in M-mode can return to S-mode with MRET.

    Also checks what the first MRET and the ECALL must skip: the instruction after each, and MPP = S on the trap."""
    print("Starting S-mode ECALL/M-mode MRET return test...")

    instr_mem = [NOP] * 56

    # M-mode setup.
    # 0x00: lui x1, 0x1                  # x1 = 0x1000 (MPP bit 12)
    instr_mem[0] = 0x000010B7
    # 0x04: csrrc x0, mstatus, x1        # clear MPP[1], leaving MPP=S (01)
    instr_mem[1] = 0x3000B073
    # 0x08: lui x2, 0x80000
    instr_mem[2] = 0x80000137
    # 0x0C: addi x2, x2, 0x60            # S payload address
    instr_mem[3] = 0x06010113
    # 0x10: csrrw x0, mepc, x2           # mepc = 0x60
    instr_mem[4] = 0x34111073
    # 0x14: lui x3, 0x80000
    instr_mem[5] = 0x800001B7
    # 0x18: addi x3, x3, 0xA0            # M-mode trap handler address
    instr_mem[6] = 0x0A018193
    # 0x1C: csrrw x0, mtvec, x3          # mtvec = 0xA0
    instr_mem[7] = 0x30519073
    # 0x20: mret                         # enter S-mode at mepc
    instr_mem[8] = 0x30200073
    # 0x24: addi x11, x0, 0x11           # must be skipped by mret redirect
    instr_mem[9] = 0x01100593

    # S-mode payload at 0x60 (word index 24).
    # 0x60: addi x5, x0, 0x5A            # S-mode pre-ecall sentinel
    instr_mem[24] = 0x05A00293
    # 0x64: ecall                        # SBI-shaped trap to M-mode
    instr_mem[25] = 0x00000073
    # 0x68: addi x6, x0, 0x66            # executes after MRET resumes
    instr_mem[26] = 0x06600313
    # 0x6C: jal x0, -4                   # hold PC here
    instr_mem[27] = 0xFFDFF06F

    # M-mode handler at 0xA0 (word index 40).
    # 0xA0: addi x7, x0, 0x77            # M-mode handler sentinel
    instr_mem[40] = 0x07700393
    # 0xA4: csrrs x9, mstatus, x0        # x9 = mstatus on trap entry (MPP = S)
    instr_mem[41] = 0x300024F3
    # 0xA8: addi x10, x6, 0              # x10 = x6 before MRET: the post-ecall addi must not have run yet
    instr_mem[42] = 0x00030513
    # 0xAC: csrrs x8, mepc, x0           # x8 = trapped ecall PC
    instr_mem[43] = 0x34102473
    # 0xB0: addi x8, x8, 4               # skip ecall on return
    instr_mem[44] = 0x00440413
    # 0xB4: csrrw x0, mepc, x8           # mepc = ecall PC + 4
    instr_mem[45] = 0x34141073
    # 0xB8: mret                         # return to S payload after ecall
    instr_mem[46] = 0x30200073

    await run_program(dut, instr_mem)

    x5 = int(dut.cpu_inst.rf_inst0.register_file[5].value)
    x6 = int(dut.cpu_inst.rf_inst0.register_file[6].value)
    x7 = int(dut.cpu_inst.rf_inst0.register_file[7].value)
    x8 = int(dut.cpu_inst.rf_inst0.register_file[8].value)
    x9 = int(dut.cpu_inst.rf_inst0.register_file[9].value)
    x10 = int(dut.cpu_inst.rf_inst0.register_file[10].value)
    x11 = int(dut.cpu_inst.rf_inst0.register_file[11].value)
    privilege_mode = int(dut.cpu_inst.csr_file_inst.privilege_mode.value)
    mcause = int(dut.cpu_inst.csr_file_inst.mcause.value)
    mepc = int(dut.cpu_inst.csr_file_inst.mepc.value)
    mstatus = int(dut.cpu_inst.csr_file_inst.mstatus.value)
    mpp = (mstatus >> 11) & 0x3

    print(f"x5 (S pre-ecall): {x5:#x}")
    print(f"x6 (S post-mret): {x6:#x}")
    print(f"x7 (M handler): {x7:#x}")
    print(f"x8 (handler-adjusted mepc): {x8:#x}")
    print(f"privilege_mode={privilege_mode:#x}, mcause={mcause:#x}, mepc={mepc:#x}, MPP={mpp:#x}")

    assert x5 == 0x5A, f"S-mode payload did not execute before ecall: x5={x5:#x}"
    assert x7 == 0x77, f"M-mode ecall handler did not execute: x7={x7:#x}"
    assert x8 == INSTR_MEM_BASE + 0x68, f"Handler did not observe/advance mepc correctly: x8={x8:#x}"
    assert x6 == 0x66, f"MRET did not resume S-mode after ecall: x6={x6:#x}"
    assert privilege_mode == 0x1, f"Expected S-mode after MRET, got {privilege_mode:#x}"
    assert mcause == 0x9, f"Expected S-mode ecall mcause=9, got {mcause:#x}"
    assert mepc == INSTR_MEM_BASE + 0x68, f"Unexpected final mepc {mepc:#x}"
    assert mpp == 0x0, f"MRET should clear MPP after return, got {mpp:#x}"
    assert x11 == 0x0, f"MRET did not redirect to mepc: the instruction after it ran (x11={x11:#x})"
    assert x10 == 0x0, f"Trap did not redirect away from the instruction after ecall (x10={x10:#x})"
    assert (x9 >> 11) & 0x3 == 0x1, f"Expected MPP=S on the S-mode ecall trap, mstatus={x9:#x}"

    print("S-mode ECALL/M-mode MRET return test passed!")


@cocotb.test()
async def test_csr_mret(dut):
    """Test trap entry via ecall and return via mret.

    Validates the trap spine RTOS ports depend on:
      - ecall sets mcause = 11 (env call from M-mode) and saves mepc
      - trap entry saves MIE -> MPIE, clears MIE, jumps to mtvec
      - mret restores MIE from MPIE (and jumps to mepc)
    """
    print("Starting mret test...")

    # Pad instruction memory so the handler at 0x40 (word index 16) lands in a valid slot.
    instr_mem = [NOP] * 32

    # 0x00: lui x1, 0x80000
    instr_mem[0] = 0x800000B7
    # 0x04: addi x1, x1, 0x40              # handler address
    instr_mem[1] = 0x04008093
    # 0x08: csrrw x0, mtvec, x1            # mtvec = 0x40
    instr_mem[2] = 0x30509073
    # 0x0C: csrrsi x0, mstatus, 8          # set MIE = 1
    instr_mem[3] = 0x30046073
    # 0x10: addi x5, x0, 0xAA              # pre-ecall sentinel
    instr_mem[4] = 0x0AA00293
    # 0x14: ecall                          # trap to mtvec
    instr_mem[5] = 0x00000073
    # 0x18: addi x6, x0, 0xBB              # executes only if mret returned here
    instr_mem[6] = 0x0BB00313
    # 0x1C: jal x0, 0                      # park here; without this the PC keeps
    #                                      # walking through the NOP padding into
    #                                      # the handler and re-executes it in
    #                                      # U-mode, trapping and clobbering mcause
    instr_mem[7] = 0x0000006F

    # Handler at 0x40 (word index 16):
    # 0x40: addi x7, x0, 0xCC              # handler sentinel
    instr_mem[16] = 0x0CC00393
    # 0x44: csrrs x8, mepc, x0             # x8 = trapped ecall PC
    instr_mem[17] = 0x34102473
    # 0x48: addi x8, x8, 4                 # return after ecall
    instr_mem[18] = 0x00440413
    # 0x4C: csrrw x0, mepc, x8             # mepc = ecall PC + 4
    instr_mem[19] = 0x34141073
    # 0x50: mret                           # return from trap
    instr_mem[20] = 0x30200073

    await run_program(dut, instr_mem)

    # Pre-ecall sentinel must have run.
    x5 = int(dut.cpu_inst.rf_inst0.register_file[5].value)
    print(f"x5 (pre-ecall sentinel): {x5:#x}")
    assert x5 == 0xAA, f"Pre-ecall path did not execute: x5={x5:#x}"

    # ecall must set mcause = 11 (env call from M-mode).
    mcause = int(dut.cpu_inst.csr_file_inst.mcause.value)
    mepc   = int(dut.cpu_inst.csr_file_inst.mepc.value)
    print(f"mcause: {mcause:#x}, mepc: {mepc:#x}")
    assert mcause == 0xB, f"ecall should set mcause=11, got {mcause:#x}"

    # Handler must have executed - proves mtvec redirect worked.
    x7 = int(dut.cpu_inst.rf_inst0.register_file[7].value)
    print(f"x7 (handler sentinel): {x7:#x}")
    assert x7 == 0xCC, f"Handler did not execute: x7={x7:#x}"

    # mret must restore MIE from MPIE. MIE was set before ecall, so trap
    # entry moves MIE(1) -> MPIE, clears MIE; mret must restore MIE = 1.
    mstatus = int(dut.cpu_inst.csr_file_inst.mstatus.value)
    mie_bit = (mstatus >> 3) & 1
    print(f"mstatus after mret: {mstatus:#x} (MIE={mie_bit})")
    assert mie_bit == 1, f"mret did not restore MIE from MPIE: mstatus={mstatus:#x}"

    print("mret test passed!")


@cocotb.test()
async def test_mpp_set_on_m_mode_illegal_instruction(dut):
    """Illegal instruction trap in M-mode must save MPP=3 in mstatus.

    This is the gap that lets rv32mi-p-illegal pass even when MPP is wrong:
    that test never does an mret that relies on MPP for a privilege switch.
    OpenSBI's CSR probe pattern does, so we test it explicitly here.
    """
    print("Starting M-mode illegal instruction MPP test...")

    instr_mem = [NOP] * 32

    # 0x00: lui x1, 0x80000
    instr_mem[0] = 0x800000B7
    # 0x04: addi x1, x1, 0x40          # handler address
    instr_mem[1] = 0x04008093
    # 0x08: csrrw x0, mtvec, x1        # install handler
    instr_mem[2] = 0x30509073
    # 0x0C: 0xFFFFFFFF                  # illegal instruction → trap
    instr_mem[3] = 0xFFFFFFFF
    # 0x10: addi x3, x0, 0x33          # post-mret M-mode sentinel
    instr_mem[4] = 0x03300193
    # 0x14: jal x0, 0                   # hang
    instr_mem[5] = 0x0000006F

    # Handler at 0x40 (word 16):
    # 0x40: csrrs x2, mstatus, x0       # x2 = mstatus at trap time (check MPP in bits 12-11)
    instr_mem[16] = 0x30002173
    # 0x44: csrrs x4, mepc, x0          # x4 = mepc (must be address of illegal instr)
    instr_mem[17] = 0x34102273
    # 0x48: addi x8, x4, 4              # x8 = return address
    instr_mem[18] = 0x00420413
    # 0x4C: csrrw x0, mepc, x8          # advance past illegal instr
    instr_mem[19] = 0x34141073
    # 0x50: mret
    instr_mem[20] = 0x30200073

    await run_program(dut, instr_mem)

    x2 = int(dut.cpu_inst.rf_inst0.register_file[2].value)
    x3 = int(dut.cpu_inst.rf_inst0.register_file[3].value)
    x4 = int(dut.cpu_inst.rf_inst0.register_file[4].value)
    mcause = int(dut.cpu_inst.csr_file_inst.mcause.value)
    privilege_mode = int(dut.cpu_inst.csr_file_inst.privilege_mode.value)
    mpp = (x2 >> 11) & 0x3

    print(f"x2 (mstatus at trap): {x2:#x}, MPP={mpp:#x}")
    print(f"x3 (post-mret sentinel): {x3:#x}")
    print(f"x4 (mepc at trap): {x4:#x}")
    print(f"mcause={mcause:#x}, privilege_mode={privilege_mode:#x}")

    assert mcause == 0x2, f"Expected illegal instruction mcause=2, got {mcause:#x}"
    assert mpp == 0x3, f"mstatus.MPP must be 3 (M-mode) when trapping in M-mode, got {mpp:#x}"
    assert x4 == INSTR_MEM_BASE + 0x0C, f"mepc must point to faulting instruction, got {x4:#x}"
    assert x3 == 0x33, f"mret did not return to M-mode: post-mret sentinel missing (x3={x3:#x})"
    assert privilege_mode == 0x3, f"Expected M-mode after mret with MPP=3, got {privilege_mode:#x}"

    print("M-mode illegal instruction MPP test passed!")


def runCocotbTests():
    run_tests("test_trap_return", [
        "test_supervisor_ecall_machine_mret_returns_to_supervisor",
        "test_csr_mret",
        "test_mpp_set_on_m_mode_illegal_instruction",
    ])


if __name__ == "__main__":
    runCocotbTests()
