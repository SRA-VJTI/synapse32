"""WFI sleeps until an enabled interrupt is pending, whether or not MIE is set, and resumes."""

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

from support import program_hex, run_hex_programs


def run_wfi_interrupt_test():
    """Create program that executes WFI and resumes after a SW interrupt."""
    main_program = [
        0x800000b7,  # lui x1, 0x80000      # mtvec base = 0x80000000
        0x10008093,  # addi x1, x1, 0x100   # mtvec = 0x80000100
        0x30509073,  # csrw mtvec, x1
        0x00800093,  # addi x1, x0, 8       # MSIE
        0x30409073,  # csrw mie, x1
        0x00800093,  # addi x1, x0, 8       # MIE global
        0x30009073,  # csrw mstatus, x1
        0x03000137,  # lui x2, 0x3000       # data base: 0x03000000
        0x01100213,  # addi x4, x0, 0x11    # pre-WFI marker
        0x00412023,  # sw x4, 0(x2)
        0x10500073,  # wfi
        0x02200293,  # addi x5, x0, 0x22    # post-WFI marker
        0x00512223,  # sw x5, 4(x2)
        0x00100313,  # addi x6, x0, 1       # done
        0x00612423,  # sw x6, 8(x2)
        0x0000006F,  # jal x0, 0            # stop here
    ]

    while len(main_program) < 64:
        main_program.append(0x00000013)  # nop

    handler = [
        0x03300393,  # addi x7, x0, 0x33    # handler marker
        0x00712623,  # sw x7, 12(x2)
        0x30200073,  # mret
        0x00000013,  # nop
    ]

    instr_mem = main_program + handler
    test_name = "wfi_interrupt"
    hex_file = program_hex("wfi", test_name, instr_mem, 512)
    return test_name, hex_file

def run_wfi_interrupt_with_global_mie_clear_test():
    """Create a WFI program with MSIE set but global MIE deliberately clear."""
    main_program = [
        0x800000b7,  # lui x1, 0x80000          # mtvec base = 0x80000000
        0x10008093,  # addi x1, x1, 0x100       # mtvec = 0x80000100
        0x30509073,  # csrw mtvec, x1
        0x00800093,  # addi x1, x0, 8           # MSIE only
        0x30409073,  # csrw mie, x1
        0x03000137,  # lui x2, 0x3000           # data base: 0x03000000
        0x01100213,  # addi x4, x0, 0x11        # pre-WFI marker
        0x00412023,  # sw x4, 0(x2)
        0x10500073,  # wfi
        0x02200293,  # addi x5, x0, 0x22        # post-WFI marker
        0x00512223,  # sw x5, 4(x2)
        0x00100313,  # addi x6, x0, 1
        0x00612423,  # sw x6, 8(x2)
        0x0000006F,  # jal x0, 0
    ]

    while len(main_program) < 64:
        main_program.append(0x00000013)

    instr_mem = main_program + [0x00000013] * 4
    test_name = "wfi_interrupt_with_global_mie_clear"
    hex_file = program_hex("wfi", test_name, instr_mem, 512)
    return test_name, hex_file

def run_wfi_pending_no_global_test():
    """Create program that proves WFI resumes on a pending enabled interrupt
    even when the global MIE bit is clear.
    """
    main_program = [
        0x03000137,  # lui x2, 0x3000       # data base: 0x03000000
        0x02000093,  # addi x1, x0, 0x20    # STIP bit
        0x30409073,  # csrw mie, x1         # enable STIP source in MIE
        0x34409073,  # csrw mip, x1         # pend STIP via supervisor-visible MIP
        0x30001073,  # csrw mstatus, x0     # keep global MIE cleared
        0x01100213,  # addi x4, x0, 0x11    # pre-WFI marker
        0x00412023,  # sw x4, 0(x2)
        0x10500073,  # wfi
        0x02200293,  # addi x5, x0, 0x22    # post-WFI marker
        0x00512223,  # sw x5, 4(x2)
        0x00100313,  # addi x6, x0, 1       # done
        0x00612423,  # sw x6, 8(x2)
        0x0000006F,  # jal x0, 0
    ]

    test_name = "wfi_pending_no_global"
    hex_file = program_hex("wfi", test_name, main_program, 512)
    return test_name, hex_file


@cocotb.test()
async def test_wfi_interrupt(dut):
    """Test WFI sleep and wakeup by software interrupt, then mret resume."""
    print("Starting WFI interrupt wake test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = {}
    first_write_cycle = {}
    max_cycles = 400

    irq_armed = False
    irq_pulse = 0

    for cycle in range(max_cycles):
        if int(dut.cpu_inst.module_mem_wr_en.value):
            addr = int(dut.cpu_inst.module_write_addr.value)
            data = int(dut.cpu_inst.module_wr_data_out.value)
            mem_writes[addr] = data
            if addr not in first_write_cycle:
                first_write_cycle[addr] = cycle
            print(f"Cycle {cycle}: Memory write addr=0x{addr:08x} data=0x{data:08x}")

        # Arm SW interrupt once we know setup reached the pre-WFI marker.
        if not irq_armed and mem_writes.get(0x03000000) == 0x11:
            irq_armed = True
            irq_pulse = 4
            dut.software_interrupt.value = 1
            print(f"Cycle {cycle}: Asserting software_interrupt for {irq_pulse} cycles")

        if irq_pulse > 0:
            irq_pulse -= 1
            if irq_pulse == 0:
                dut.software_interrupt.value = 0
                print(f"Cycle {cycle}: Deasserting software_interrupt")

        if mem_writes.get(0x03000008) == 1:
            print(f"Cycle {cycle}: Completion flag observed")
            break

        await RisingEdge(dut.clk)

    assert mem_writes.get(0x03000000) == 0x11, "Pre-WFI marker missing"
    assert mem_writes.get(0x0300000C) == 0x33, "WFI handler marker missing"
    assert mem_writes.get(0x03000004) == 0x22, "Post-WFI resume marker missing"
    assert mem_writes.get(0x03000008) == 1, "Completion flag missing"

    assert first_write_cycle[0x0300000C] < first_write_cycle[0x03000004], (
        "Post-WFI marker appeared before handler marker; WFI wake/return order is wrong"
    )

    print("WFI interrupt wake test passed!")


@cocotb.test()
async def test_wfi_interrupt_with_global_mie_clear(dut):
    """WFI must resume on an enabled pending interrupt with MIE clear."""
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = {}
    irq_armed = False
    irq_pulse = 0

    for _ in range(400):
        if int(dut.cpu_inst.module_mem_wr_en.value):
            addr = int(dut.cpu_inst.module_write_addr.value)
            mem_writes[addr] = int(dut.cpu_inst.module_wr_data_out.value)

        # Pulse once WFI sleeps: a pulse that ends before WFI executes leaves nothing pending.
        if not irq_armed and mem_writes.get(0x03000000) == 0x11 and int(dut.cpu_inst.wfi_active.value):
            irq_armed = True
            irq_pulse = 4
            dut.software_interrupt.value = 1

        if irq_pulse > 0:
            irq_pulse -= 1
            if irq_pulse == 0:
                dut.software_interrupt.value = 0

        if mem_writes.get(0x03000008) == 1:
            break
        await RisingEdge(dut.clk)

    assert mem_writes.get(0x03000000) == 0x11, "Pre-WFI marker missing"
    assert irq_armed, "WFI never slept"
    assert mem_writes.get(0x03000004) == 0x22, (
        "WFI did not resume while global MIE was clear"
    )
    assert mem_writes.get(0x03000008) == 1, "Completion flag missing"
    assert 0x0300000C not in mem_writes, "Interrupt was delivered despite MIE=0"


@cocotb.test()
async def test_wfi_pending_no_global(dut):
    """Test WFI resumes on an enabled pending interrupt even with MIE=0."""
    print("Starting WFI pending-with-global-disabled test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0

    mem_writes = {}
    max_cycles = 120

    for cycle in range(max_cycles):
        if int(dut.cpu_inst.module_mem_wr_en.value):
            addr = int(dut.cpu_inst.module_write_addr.value)
            data = int(dut.cpu_inst.module_wr_data_out.value)
            mem_writes[addr] = data
            print(f"Cycle {cycle}: Memory write addr=0x{addr:08x} data=0x{data:08x}")

        if mem_writes.get(0x03000008) == 1:
            print(f"Cycle {cycle}: Completion flag observed")
            break

        await RisingEdge(dut.clk)

    assert mem_writes.get(0x03000000) == 0x11, "Pre-WFI marker missing"
    assert mem_writes.get(0x03000004) == 0x22, (
        "Post-WFI marker missing; WFI did not resume with pending enabled interrupt"
    )
    assert mem_writes.get(0x03000008) == 1, "Completion flag missing"
    assert int(dut.cpu_inst.csr_file_inst.mcause.value) == 0, (
        "Interrupt should not have trapped while global MIE was disabled"
    )

    print("WFI pending-with-global-disabled test passed!")


def runCocotbTests():
    run_hex_programs("test_wfi", [
        ("wfi_interrupt", run_wfi_interrupt_test),
        ("wfi_interrupt_with_global_mie_clear", run_wfi_interrupt_with_global_mie_clear_test),
        ("wfi_pending_no_global", run_wfi_pending_no_global_test),
    ])


if __name__ == "__main__":
    runCocotbTests()
