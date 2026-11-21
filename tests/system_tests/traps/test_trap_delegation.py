"""Exceptions and interrupts delegated to S-mode by medeleg and mideleg, and SRET back."""

import cocotb

from support import INSTR_MEM_BASE, NOP, run_program, run_tests


@cocotb.test()
async def test_delegated_user_ecall_sret(dut):
    """Test delegated U-mode ECALL traps to S-mode and resumes via SRET."""
    print("Starting delegated U-mode ECALL/SRET test...")

    instr_mem = [NOP] * 56

    # M-mode setup.
    instr_mem[0] = 0x80000137  # lui  x2, 0x80000
    instr_mem[1] = 0x06010113  # addi x2, x2, 0x60
    instr_mem[2] = 0x34111073  # csrrw x0, mepc, x2
    instr_mem[3] = 0x800001B7  # lui  x3, 0x80000
    instr_mem[4] = 0x0A018193  # addi x3, x3, 0xA0
    instr_mem[5] = 0x10519073  # csrrw x0, stvec, x3
    instr_mem[6] = 0x00100213  # addi x4, x0, 1
    instr_mem[7] = 0x00821213  # slli x4, x4, 8        -> medeleg[8]
    instr_mem[8] = 0x30221073  # csrrw x0, medeleg, x4
    instr_mem[9] = 0x34201073  # csrrw x0, mcause, x0
    instr_mem[10] = 0x000022B7 # lui  x5, 0x2
    instr_mem[11] = 0x80028293 # addi x5, x5, -2048    -> 0x1800
    instr_mem[12] = 0x3002B073 # csrrc x0, mstatus, x5 -> MPP=U
    instr_mem[13] = 0x30200073 # mret

    # U-mode payload at 0x60 (word index 24).
    instr_mem[24] = 0x05A00293  # addi x5, x0, 0x5A
    instr_mem[25] = 0x00000073  # ecall
    instr_mem[26] = 0x06600313  # addi x6, x0, 0x66
    instr_mem[27] = 0xFFDFF06F  # jal x0, -4

    # S-mode handler at 0xA0 (word index 40).
    instr_mem[40] = 0x07700393  # addi x7, x0, 0x77
    instr_mem[41] = 0x14102473  # csrrs x8, sepc, x0
    instr_mem[42] = 0x142024F3  # csrrs x9, scause, x0
    instr_mem[43] = 0x00440413  # addi x8, x8, 4
    instr_mem[44] = 0x14141073  # csrrw x0, sepc, x8
    instr_mem[45] = 0x10200073  # sret

    await run_program(dut, instr_mem)

    x5 = int(dut.cpu_inst.rf_inst0.register_file[5].value)
    x6 = int(dut.cpu_inst.rf_inst0.register_file[6].value)
    x7 = int(dut.cpu_inst.rf_inst0.register_file[7].value)
    x8 = int(dut.cpu_inst.rf_inst0.register_file[8].value)
    x9 = int(dut.cpu_inst.rf_inst0.register_file[9].value)
    privilege_mode = int(dut.cpu_inst.csr_file_inst.privilege_mode.value)
    scause = int(dut.cpu_inst.csr_file_inst.scause.value)
    sepc = int(dut.cpu_inst.csr_file_inst.sepc.value)
    mcause = int(dut.cpu_inst.csr_file_inst.mcause.value)
    mstatus = int(dut.cpu_inst.csr_file_inst.mstatus.value)
    spp = (mstatus >> 8) & 0x1

    print(f"x5 (U pre-ecall): {x5:#x}")
    print(f"x6 (U post-sret): {x6:#x}")
    print(f"x7 (S handler): {x7:#x}")
    print(f"x8 (handler-adjusted sepc): {x8:#x}")
    print(f"x9 (captured scause): {x9:#x}")
    print(f"privilege_mode={privilege_mode:#x}, scause={scause:#x}, sepc={sepc:#x}, mcause={mcause:#x}, SPP={spp:#x}")

    assert x5 == 0x5A, f"U-mode payload did not execute before ecall: x5={x5:#x}"
    assert x7 == 0x77, f"S-mode handler did not execute for delegated user ecall: x7={x7:#x}"
    assert x8 == INSTR_MEM_BASE + 0x68, f"Handler did not observe/advance sepc correctly: x8={x8:#x}"
    assert x9 == 0x8, f"Handler did not observe user ecall scause=8: x9={x9:#x}"
    assert x6 == 0x66, f"SRET did not resume user payload after ecall: x6={x6:#x}"
    assert privilege_mode == 0x0, f"Expected U-mode after sret, got {privilege_mode:#x}"
    assert scause == 0x8, f"Expected delegated user ecall scause=8, got {scause:#x}"
    assert sepc == INSTR_MEM_BASE + 0x68, f"Unexpected final sepc {sepc:#x}"
    assert mcause == 0x0, f"Delegated user ecall should not update mcause, got {mcause:#x}"
    assert spp == 0x0, f"Delegated U-mode trap should restore/clear SPP to 0, got {spp:#x}"

    print("Delegated U-mode ECALL/SRET test passed!")


@cocotb.test()
async def test_delegated_supervisor_ebreak_sret(dut):
    """Test delegated S-mode EBREAK traps to stvec and resumes with SRET."""
    print("Starting delegated S-mode EBREAK/SRET test...")

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
    # 0x18: addi x3, x3, 0xA0            # S trap handler address
    instr_mem[6] = 0x0A018193
    # 0x1C: csrrw x0, stvec, x3          # stvec = 0xA0
    instr_mem[7] = 0x10519073
    # 0x20: addi x4, x0, 0x8             # delegate exception cause 3
    instr_mem[8] = 0x00800213
    # 0x24: csrrw x0, medeleg, x4        # medeleg[3] = 1
    instr_mem[9] = 0x30221073
    # 0x28: csrrw x0, mcause, x0         # mcause = 0
    instr_mem[10] = 0x34201073
    # 0x2C: mret                         # enter S-mode at mepc
    instr_mem[11] = 0x30200073

    # S-mode payload at 0x60 (word index 24).
    # 0x60: addi x5, x0, 0x5A            # S-mode pre-ebreak sentinel
    instr_mem[24] = 0x05A00293
    # 0x64: ebreak                       # delegated to S-mode stvec
    instr_mem[25] = 0x00100073
    # 0x68: addi x6, x0, 0x66            # executes after SRET resumes
    instr_mem[26] = 0x06600313
    # 0x6C: jal x0, -4                   # hold PC here
    instr_mem[27] = 0xFFDFF06F

    # S-mode handler at 0xA0 (word index 40).
    # 0xA0: addi x7, x0, 0x77            # handler sentinel
    instr_mem[40] = 0x07700393
    # 0xA4: csrrs x8, sepc, x0           # x8 = trapped ebreak PC
    instr_mem[41] = 0x14102473
    # 0xA8: addi x8, x8, 4               # skip ecall on return
    instr_mem[42] = 0x00440413
    # 0xAC: csrrw x0, sepc, x8           # sepc = ecall PC + 4
    instr_mem[43] = 0x14141073
    # 0xB0: sret                         # return to S payload after ecall
    instr_mem[44] = 0x10200073

    await run_program(dut, instr_mem)

    x5 = int(dut.cpu_inst.rf_inst0.register_file[5].value)
    x6 = int(dut.cpu_inst.rf_inst0.register_file[6].value)
    x7 = int(dut.cpu_inst.rf_inst0.register_file[7].value)
    x8 = int(dut.cpu_inst.rf_inst0.register_file[8].value)
    privilege_mode = int(dut.cpu_inst.csr_file_inst.privilege_mode.value)
    scause = int(dut.cpu_inst.csr_file_inst.scause.value)
    sepc = int(dut.cpu_inst.csr_file_inst.sepc.value)
    mcause = int(dut.cpu_inst.csr_file_inst.mcause.value)
    mstatus = int(dut.cpu_inst.csr_file_inst.mstatus.value)
    spp = (mstatus >> 8) & 0x1

    print(f"x5 (S pre-ebreak): {x5:#x}")
    print(f"x6 (S post-sret): {x6:#x}")
    print(f"x7 (S handler): {x7:#x}")
    print(f"x8 (handler-adjusted sepc): {x8:#x}")
    print(f"privilege_mode={privilege_mode:#x}, scause={scause:#x}, sepc={sepc:#x}, mcause={mcause:#x}, SPP={spp:#x}")

    assert x5 == 0x5A, f"S-mode payload did not execute before ebreak: x5={x5:#x}"
    assert x7 == 0x77, f"S-mode trap handler did not execute: x7={x7:#x}"
    assert x8 == INSTR_MEM_BASE + 0x68, f"Handler did not observe/advance sepc correctly: x8={x8:#x}"
    assert x6 == 0x66, f"SRET did not resume after ebreak: x6={x6:#x}"
    assert privilege_mode == 0x1, f"Expected S-mode after sret, got {privilege_mode:#x}"
    assert scause == 0x3, f"Expected delegated S-mode ebreak scause=3, got {scause:#x}"
    assert sepc == INSTR_MEM_BASE + 0x68, f"Unexpected final sepc {sepc:#x}"
    assert mcause == 0x0, f"Delegated S-mode ebreak should not update mcause, got {mcause:#x}"
    assert spp == 0x0, f"SRET should clear SPP, got {spp:#x}"

    print("Delegated S-mode EBREAK/SRET test passed!")


@cocotb.test()
async def test_delegated_user_timer_interrupt_sret(dut):
    """Test delegated supervisor timer interrupt traps from U-mode to S-mode and resumes via SRET."""
    print("Starting delegated U-mode timer interrupt/SRET test...")

    instr_mem = [NOP] * 56

    # M-mode setup.
    instr_mem[0] = 0x80000137  # lui  x2, 0x80000
    instr_mem[1] = 0x06010113  # addi x2, x2, 0x60
    instr_mem[2] = 0x34111073  # csrrw x0, mepc, x2
    instr_mem[3] = 0x800001B7  # lui  x3, 0x80000
    instr_mem[4] = 0x0A018193  # addi x3, x3, 0xA0
    instr_mem[5] = 0x10519073  # csrrw x0, stvec, x3
    instr_mem[6] = 0x02000213  # addi x4, x0, 0x20     -> mideleg[5], sie.STIE, mip.STIP
    instr_mem[7] = 0x30321073  # csrrw x0, mideleg, x4
    instr_mem[8] = 0x10421073  # csrrw x0, sie, x4
    instr_mem[9] = 0x34421073  # csrrw x0, mip, x4     (M-mode software, as an SBI does)
    instr_mem[10] = 0x10016073 # csrrsi x0, sstatus, 2
    instr_mem[11] = 0x000022B7 # lui  x5, 0x2
    instr_mem[12] = 0x80028293 # addi x5, x5, -2048    -> 0x1800
    instr_mem[13] = 0x3002B073 # csrrc x0, mstatus, x5 -> MPP=U
    instr_mem[14] = 0x30200073 # mret

    # U-mode payload at 0x60 (word index 24).
    instr_mem[24] = 0x05A00293  # addi x5, x0, 0x5A
    instr_mem[25] = 0xFFDFF06F  # jal x0, -4

    # S-mode handler at 0xA0 (word index 40).
    instr_mem[40] = 0x07700393  # addi x7, x0, 0x77
    instr_mem[41] = 0x14102473  # csrrs x8, sepc, x0
    instr_mem[42] = 0x10423073  # csrrc x0, sie, x4    (sip.STIP is read-only to S-mode)
    instr_mem[43] = 0x10200073  # sret

    await run_program(dut, instr_mem)

    x5 = int(dut.cpu_inst.rf_inst0.register_file[5].value)
    x7 = int(dut.cpu_inst.rf_inst0.register_file[7].value)
    x8 = int(dut.cpu_inst.rf_inst0.register_file[8].value)
    privilege_mode = int(dut.cpu_inst.csr_file_inst.privilege_mode.value)
    scause = int(dut.cpu_inst.csr_file_inst.scause.value)
    sip = int(dut.cpu_inst.csr_file_inst.sip.value)
    mstatus = int(dut.cpu_inst.csr_file_inst.mstatus.value)
    spp = (mstatus >> 8) & 0x1

    print(f"x5 (U payload): {x5:#x}")
    print(f"x7 (S timer handler): {x7:#x}")
    print(f"x8 (captured sepc): {x8:#x}")
    print(f"privilege_mode={privilege_mode:#x}, scause={scause:#x}, sip={sip:#x}, SPP={spp:#x}")

    assert x7 == 0x77, f"S-mode timer handler did not execute from U-mode: x7={x7:#x}"
    assert x5 == 0x5A, f"SRET did not resume U-mode payload: x5={x5:#x}"
    assert x8 in (INSTR_MEM_BASE + 0x60, INSTR_MEM_BASE + 0x64), f"Unexpected interrupted U-mode PC in sepc: x8={x8:#x}"
    assert privilege_mode == 0x0, f"Expected U-mode after delegated timer sret, got {privilege_mode:#x}"
    assert scause == 0x80000005, f"Expected supervisor timer interrupt scause, got {scause:#x}"
    assert (sip & 0x20) != 0, f"sip.STIP is read-only to S-mode, yet the handler cleared it: sip={sip:#x}"
    assert spp == 0x0, f"Delegated U-mode interrupt should restore/clear SPP to 0, got {spp:#x}"

    print("Delegated U-mode timer interrupt/SRET test passed!")


def runCocotbTests():
    run_tests("test_trap_delegation", [
        "test_delegated_user_ecall_sret",
        "test_delegated_supervisor_ebreak_sret",
        "test_delegated_user_timer_interrupt_sret",
    ])


if __name__ == "__main__":
    runCocotbTests()
