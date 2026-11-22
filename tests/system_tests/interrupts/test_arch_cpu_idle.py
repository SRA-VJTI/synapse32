"""Linux's arch_cpu_idle (fence; wfi; lw; ret) in S-mode through Sv32 resumes on an interrupt."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from support import INSTR_MEM_BASE, program_hex, run_hex_programs, word_index


def run_arch_cpu_idle_resume_mmu_test():
    """Same idle helper, but return target stores into a mapped scratch page.

    Layout matches run_arch_cpu_idle_resume_test: the return block sits at
    +0x20 behind two spins, so it is reachable only through the loaded ra.
    """
    instr_mem = [
        0x0FF0000F,  # fence
        0x10500073,  # wfi
        0x00C12083,  # lw ra, 12(sp)
        0x00812403,  # lw s0, 8(sp)
        0x01010113,  # addi sp, sp, 0x10
        0x00008067,  # ret                  -> code_va + 0x20 via the loaded ra
        0x0000006F,  # jal x0, 0            # trap the fall-through path
        0x0000006F,  # jal x0, 0
        0x800023B7,  # lui x7, 0x80002      -> 0x80002000
        0x0013A023,  # sw ra, 0(x7)
        0x07700293,  # addi x5, x0, 0x77
        0x0053A223,  # sw x5, 4(x7)
        0x00100313,  # addi x6, x0, 1
        0x0063A423,  # sw x6, 8(x7)
        0x0000006F,  # jal x0, 0
    ]

    test_name = "arch_cpu_idle_resume_mmu"
    hex_file = program_hex("arch_cpu_idle", test_name, instr_mem, 512)
    return test_name, hex_file


@cocotb.test()
async def test_arch_cpu_idle_resume_mmu(dut):
    """Run the idle helper through Sv32 mappings without full Linux boot."""
    print("Starting arch_cpu_idle MMU reproducer...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.uart_rx.value = 1
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)

    code_va = 0x80000000
    stack_va = 0x80001000
    scratch_va = 0x80002000
    stack_pa = 0x10000000
    scratch_pa = 0x10001000
    root_pt_pa = 0x10002000
    l0_pt_pa = 0x10003000
    return_pc = code_va + 0x20
    saved_s0 = 0x12345678

    def pte_leaf(ppn, flags):
        return ((ppn & 0xFFFFF) << 10) | flags

    def pte_ptr(ppn):
        return ((ppn & 0xFFFFF) << 10) | 0x001

    # Seed stack frame.
    dut.unified_mem_inst.instr_ram[word_index(stack_pa + 8)].value = saved_s0
    dut.unified_mem_inst.instr_ram[word_index(stack_pa + 12)].value = return_pc

    # Root entry for vpn1=0x200, then leaf entries for vpn0=0/1/2.
    dut.unified_mem_inst.instr_ram[word_index(root_pt_pa + 0x800)].value = pte_ptr(l0_pt_pa >> 12)
    dut.unified_mem_inst.instr_ram[word_index(l0_pt_pa + 0x000)].value = pte_leaf(INSTR_MEM_BASE >> 12, 0x04B)
    dut.unified_mem_inst.instr_ram[word_index(l0_pt_pa + 0x004)].value = pte_leaf(stack_pa >> 12, 0x0C7)
    dut.unified_mem_inst.instr_ram[word_index(l0_pt_pa + 0x008)].value = pte_leaf(scratch_pa >> 12, 0x0C7)

    # Seed S-mode + satp-on state while reset is asserted.
    dut.cpu_inst.rf_inst0.register_file[2].value = stack_va
    dut.cpu_inst.rf_inst0.register_file[8].value = 0xCAFEBABE
    dut.cpu_inst.rf_inst0.register_file[1].value = 0x11111111
    csr = dut.cpu_inst.csr_file_inst
    csr.privilege_mode.value = 0x1
    csr.mstatus.value = 0x00000000
    csr.mie.value = 0x00000020
    csr.mideleg.value = 0x00000020
    csr.stip_software_pending.value = 1
    csr.satp.value = 0x80000000 | (root_pt_pa >> 12)

    dut.rst.value = 0

    observed = []
    mem_writes = {}
    reached_return = False

    for cycle in range(300):
        await RisingEdge(dut.clk)

        sample = {
            "cycle": cycle,
            "pc": int(dut.pc_debug.value) & 0xFFFFFFFF,
            "instr": int(dut.instr_debug.value) & 0xFFFFFFFF,
            "ipaddr": int(dut.cpu_inst.phys_instr_addr.value) & 0xFFFFFFFF,
            "dpaddr": int(dut.cpu_inst.phys_data_addr.value) & 0xFFFFFFFF,
            "ifault": int(dut.cpu_inst.module_instr_page_fault_in.value),
            "lfault": int(dut.cpu_inst.module_load_page_fault_in.value),
            "sfault": int(dut.cpu_inst.module_store_page_fault_in.value),
            "wfi_active": int(dut.cpu_inst.wfi_active.value),
            "wfi_stall": int(dut.cpu_inst.wfi_stall.value),
            "wake": int(dut.cpu_inst.wfi_resume_pending.value),
            "ipend": int(dut.cpu_inst.interrupt_pending.value),
            "mip": int(csr.mip.value) & 0xFFFFFFFF,
            "mie": int(csr.mie.value) & 0xFFFFFFFF,
            "satp": int(csr.satp.value) & 0xFFFFFFFF,
        }
        observed.append(sample)
        print(
            "Cycle {cycle}: pc=0x{pc:08x} instr=0x{instr:08x} ipaddr=0x{ipaddr:08x} "
            "dpaddr=0x{dpaddr:08x} ifault={ifault} lfault={lfault} sfault={sfault} "
            "wfi_active={wfi_active} wfi_stall={wfi_stall} wake={wake} ipend={ipend} "
            "mip=0x{mip:08x} mie=0x{mie:08x} satp=0x{satp:08x}".format(**sample)
        )

        if sample["pc"] == return_pc:
            reached_return = True

        # module_write_addr is the pre-translation address, so these keys are
        # the scratch page's virtual addresses.
        if int(dut.cpu_inst.module_mem_wr_en.value):
            addr = int(dut.cpu_inst.module_write_addr.value) & 0xFFFFFFFF
            data = int(dut.cpu_inst.module_wr_data_out.value) & 0xFFFFFFFF
            mem_writes[addr] = data
            print(f"Cycle {cycle}: Memory write addr=0x{addr:08x} data=0x{data:08x}")

        if mem_writes.get(scratch_va + 8) == 1:
            break

    pc_tail = " ".join(f"{s['cycle']}:0x{s['pc']:08x}" for s in observed[-12:])
    assert mem_writes.get(scratch_va + 8) == 1, (
        "Return block never ran: the core did not return through the loaded ra "
        f"(reached_return={reached_return}, last PCs: {pc_tail})"
    )
    assert mem_writes.get(scratch_va) == return_pc, (
        f"ret used the wrong return address: stored ra="
        f"0x{mem_writes.get(scratch_va, 0):08x}, expected 0x{return_pc:08x}"
    )
    assert mem_writes.get(scratch_va + 4) == 0x77, "Marker store missing"
    assert int(dut.cpu_inst.rf_inst0.register_file[8].value) == saved_s0, (
        "Post-WFI load of s0 did not retire: s0="
        f"0x{int(dut.cpu_inst.rf_inst0.register_file[8].value):08x}, "
        f"expected 0x{saved_s0:08x}"
    )
    assert not any(s["ifault"] or s["lfault"] or s["sfault"] for s in observed), (
        "Unexpected MMU fault during idle reproducer"
    )

    print("arch_cpu_idle MMU reproducer passed!")


def runCocotbTests():
    run_hex_programs("test_arch_cpu_idle", [
        ("arch_cpu_idle_resume_mmu", run_arch_cpu_idle_resume_mmu_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
