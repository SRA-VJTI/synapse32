import cocotb
from cocotb.triggers import FallingEdge, ReadOnly, RisingEdge, Timer
from cocotb.clock import Clock
import pytest
import os

RESET_PC_BASE = 0x80000000
NOP = 0x00000013


async def run_csr_test_program(dut, instr_mem):
    """Helper function to run a CSR test program"""
    # Dictionary to track register values
    reg_values = {i: 0 for i in range(32)}
    trace_pipeline = os.getenv("TRACE_PIPELINE", "0") == "1"
    
    # Simulate instruction memory fetch
    def get_instr(pc):
        if pc >= RESET_PC_BASE:
            idx = (pc - RESET_PC_BASE) // 4
        else:
            idx = pc // 4
        if 0 <= idx < len(instr_mem):
            return instr_mem[idx]
        return NOP

    async def drive_instruction_memory():
        while True:
            pc = int(dut.module_pc_out.value)
            dut.module_instr_in.value = get_instr(pc)
            await FallingEdge(dut.clk)

    cocotb.start_soon(drive_instruction_memory())
    
    # Feed instructions and track CSR operations
    for cycle in range(len(instr_mem) + 10):  # Run for enough cycles
        await RisingEdge(dut.clk)
        await ReadOnly()
        
        # Track register writes
        try:
            wb_reg = int(dut.rf_inst0_rd_in.value)
            wb_val = int(dut.rf_inst0_rd_value_in.value)
            wb_en = int(dut.rf_inst0_wr_en.value)
            
            if wb_en and wb_reg != 0:
                reg_values[wb_reg] = wb_val
                print(f"Cycle {cycle}: Register x{wb_reg} = {wb_val:#x}")
        except Exception as e:
            print(f"Error tracking registers: {e}")
        
        # Track CSR operations
        try:
            csr_addr = int(dut.csr_addr.value)
            csr_read_en = int(dut.csr_read_enable.value)
            csr_write_en = int(dut.csr_write_enable.value)
            csr_read_data = int(dut.csr_read_data.value)
            csr_write_data = int(dut.csr_write_data.value)
            
            if csr_read_en or csr_write_en:
                operation = ""
                if csr_read_en and csr_write_en:
                    operation = f"CSR RW: CSR[{csr_addr:#x}] read={csr_read_data:#x}, write={csr_write_data:#x}"
                elif csr_read_en:
                    operation = f"CSR R: CSR[{csr_addr:#x}] read={csr_read_data:#x}"
                elif csr_write_en:
                    operation = f"CSR W: CSR[{csr_addr:#x}] write={csr_write_data:#x}"
                print(f"Cycle {cycle}: {operation}")
        except Exception as e:
            # CSR signals might not be ready yet
            pass

        if trace_pipeline:
            try:
                print(
                    "Cycle {}: fetch_pc={} if_id_pc={} if_id_instr={} if_id_valid={} "
                    "module_instr={} id_ex_pc={} id_ex_id={} id_ex_valid={} jump={} jump_addr={} "
                    "flush={} mepc={} priv={}".format(
                        cycle,
                        int(dut.module_pc_out.value),
                        int(dut.if_id_pc_out.value),
                        int(dut.if_id_instr_out.value),
                        int(dut.if_id_instr_valid_out.value),
                        int(dut.module_instr_in.value),
                        int(dut.id_ex_inst0_pc_out.value),
                        int(dut.id_ex_inst0_instr_id_out.value),
                        int(dut.id_ex_inst0_instr_valid_out.value),
                        int(dut.ex_inst0_jump_signal_out.value),
                        int(dut.ex_inst0_jump_addr_out.value),
                        int(dut.execution_flush.value),
                        int(dut.csr_file_inst.mepc.value),
                        int(dut.csr_file_inst.privilege_mode.value),
                    )
                )
            except Exception:
                pass
            
    # Print final register values
    print("\nFinal register values:")
    for reg, value in reg_values.items():
        if value != 0:  # Only print non-zero registers
            print(f"x{reg} = {value:#x}")
    
    return reg_values

@cocotb.test()
async def test_csr_basic_operations(dut):
    """Test basic CSR read/write operations"""
    print("Starting CSR basic operations test...")
    
    # Attach a clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Program to test CSR operations:
    instr_mem = [
        # Test CSRRW (Read/Write)
        0x00a00093,  # addi x1, x0, 10     # x1 = 10
        0x34009173,  # csrrw x2, mscratch, x1  # x2 = old mscratch (0), mscratch = 10
        0x34001273,  # csrrw x4, mscratch, x0  # x4 = mscratch (10), mscratch = 0
        
        # Test CSRRS (Read/Set)
        0x00500093,  # addi x1, x0, 5      # x1 = 5
        0x3400a373,  # csrrs x6, mscratch, x1  # x6 = mscratch (0), mscratch |= 5
        0x00300113,  # addi x2, x0, 3      # x2 = 3
        0x34012473,  # csrrs x8, mscratch, x2  # x8 = mscratch (5), mscratch |= 3 = 7
        
        # Test CSRRC (Read/Clear)
        0x00100193,  # addi x3, x0, 1      # x3 = 1
        0x3401b573,  # csrrc x10, mscratch, x3 # x10 = mscratch (7), mscratch &= ~1 = 6
        
        # Test immediate versions
        0x3402d673,  # csrrwi x12, mscratch, 5  # x12 = mscratch (6), mscratch = 5
        0x34016773,  # csrrsi x14, mscratch, 2  # x14 = mscratch (5), mscratch |= 2 = 7
        0x3400f873,  # csrrci x16, mscratch, 1  # x16 = mscratch (7), mscratch &= ~1 = 6
    ]

    # Run the program
    reg_values = await run_csr_test_program(dut, instr_mem)
    
    # Expected register values after execution
    expected_values = {
        1: 5,    # x1 = 10
        2: 3,     # x2 = old mscratch (initial value 0)
        4: 10,    # x4 = mscratch value (10)
        6: 0,     # x6 = mscratch before set (0)
        8: 5,     # x8 = mscratch before set (5)
        10: 7,    # x10 = mscratch before clear (7)
        12: 6,    # x12 = mscratch before write (6)
        14: 5,    # x14 = mscratch before set (5)
        16: 7,    # x16 = mscratch before clear (7)
    }
    
    # Verify register values
    print("\nVerifying register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    # Check final CSR value
    final_mscratch = int(dut.csr_file_inst.mscratch.value)
    expected_mscratch = 6  # Final value after all operations
    print(f"mscratch: expected={expected_mscratch:#x}, actual={final_mscratch:#x}")
    assert final_mscratch == expected_mscratch, f"mscratch value mismatch: expected {expected_mscratch:#x}, got {final_mscratch:#x}"
    
    print("All CSR basic operations test passed!")

@cocotb.test()
async def test_csr_mstatus_operations(dut):
    """Test operations on MSTATUS CSR"""
    print("Starting MSTATUS CSR test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Program to test MSTATUS operations:
    instr_mem = [
        # Read initial MSTATUS value
        0x30002073,  # csrrs x0, mstatus, x0   # Read mstatus (no change)
        0x30002173,  # csrrs x2, mstatus, x0   # x2 = mstatus
        
        # Set some bits in MSTATUS
        0x00800093,  # addi x1, x0, 8         # x1 = 8 (MIE bit)
        0x3000a273,  # csrrs x4, mstatus, x1   # Set MIE bit, x4 = old mstatus
        
        # Clear some bits in MSTATUS
        0x00800193,  # addi x3, x0, 8         # x3 = 8 (MIE bit)
        0x3001b373,  # csrrc x6, mstatus, x3   # Clear MIE bit, x6 = old mstatus
        
        # Test immediate operations on MSTATUS
        0x30006473,  # csrrsi x8, mstatus, 0   # Read mstatus (no change)
        0x30015573,  # csrrsi x10, mstatus, 2  # Set bit 1, x10 = old mstatus
    ]

    await run_csr_test_program(dut, instr_mem)
    
    # Verify that MSTATUS operations worked correctly
    # Note: Initial MSTATUS = 0x1800 (MPP = 11)
    expected_values = {
        2: 0x1800,  # x2 = initial mstatus
        3: 0x8,  # x3 = MIE bit set (0x1808)
        4: 0x1800,  # x4 = mstatus before setting MIE
        6: 0x1808,  # x6 = mstatus with MIE set
        8: 0x1800,  # x8 = mstatus after clearing MIE
        10: 0x1800, # x10 = mstatus before setting bit 1
    }
    
    print("\nVerifying MSTATUS register values:")
    for reg, expected in expected_values.items():
        actual = int(dut.rf_inst0.register_file[reg].value)
        print(f"x{reg}: expected={expected:#x}, actual={actual:#x}")
        assert actual == expected, f"Register x{reg} value mismatch: expected {expected:#x}, got {actual:#x}"
    
    print("MSTATUS CSR test passed!")

@cocotb.test()
async def test_csr_cycle_counter(dut):
    """Test cycle counter CSRs"""
    print("Starting cycle counter CSR test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

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

    await run_csr_test_program(dut, instr_mem)
    
    # Verify that cycle counter is advancing
    cycle_low_1 = int(dut.rf_inst0.register_file[2].value)
    cycle_high_1 = int(dut.rf_inst0.register_file[4].value)
    cycle_low_2 = int(dut.rf_inst0.register_file[6].value)
    cycle_high_2 = int(dut.rf_inst0.register_file[8].value)
    
    print(f"First cycle read: low={cycle_low_1:#x}, high={cycle_high_1:#x}")
    print(f"Second cycle read: low={cycle_low_2:#x}, high={cycle_high_2:#x}")
    
    # Cycle counter should have advanced
    assert cycle_low_2 > cycle_low_1, "Cycle counter should have advanced"
    
    print("Cycle counter CSR test passed!")

@cocotb.test()
async def test_mret_enters_supervisor_mode(dut):
    """Test that MRET can drop from M-mode into S-mode."""
    print("Starting MRET-to-S-mode test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    NOP = 0x00000013
    instr_mem = [NOP] * 16

    # 0x00: lui x1, 0x1                  # x1 = 0x1000 (MPP bit 12)
    instr_mem[0] = 0x000010B7
    # 0x04: csrrc x0, mstatus, x1        # clear MPP[1], leaving MPP=S (01)
    instr_mem[1] = 0x3000B073
    # 0x08: addi x2, x0, 0x20            # S payload address
    instr_mem[2] = 0x02000113
    # 0x0C: csrrw x0, mepc, x2           # mepc = 0x20
    instr_mem[3] = 0x34111073
    # 0x10: mret                         # enter S-mode at mepc
    instr_mem[4] = 0x30200073
    # 0x14: addi x6, x0, 0x66            # must be skipped by mret redirect
    instr_mem[5] = 0x06600313

    # S-mode payload at 0x20 (word index 8).
    # 0x20: addi x5, x0, 0x5A            # S-mode sentinel
    instr_mem[8] = 0x05A00293
    # 0x24: jal x0, 0                    # hold PC here
    instr_mem[9] = 0x0000006F

    await run_csr_test_program(dut, instr_mem)

    x5 = int(dut.rf_inst0.register_file[5].value)
    x6 = int(dut.rf_inst0.register_file[6].value)
    privilege_mode = int(dut.csr_file_inst.privilege_mode.value)
    mstatus = int(dut.csr_file_inst.mstatus.value)
    mpp = (mstatus >> 11) & 0x3

    print(f"x5 (S-mode sentinel): {x5:#x}")
    print(f"x6 (skipped M-mode sentinel): {x6:#x}")
    print(f"privilege_mode={privilege_mode:#x}, mstatus={mstatus:#x}, MPP={mpp:#x}")

    assert x5 == 0x5A, f"S-mode payload did not execute: x5={x5:#x}"
    assert x6 == 0x0, f"MRET did not redirect to mepc: x6={x6:#x}"
    assert privilege_mode == 0x1, f"Expected S-mode after mret, got {privilege_mode:#x}"
    assert mpp == 0x0, f"MRET should clear MPP after return, got {mpp:#x}"

    print("MRET-to-S-mode test passed!")

@cocotb.test()
async def test_supervisor_ecall_traps_to_machine_mode(dut):
    """Test that an ECALL from S-mode traps to M-mode with cause 9."""
    print("Starting S-mode ECALL-to-M-mode test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    NOP = 0x00000013
    instr_mem = [NOP] * 40

    # 0x00: lui x1, 0x1                  # x1 = 0x1000 (MPP bit 12)
    instr_mem[0] = 0x000010B7
    # 0x04: csrrc x0, mstatus, x1        # clear MPP[1], leaving MPP=S (01)
    instr_mem[1] = 0x3000B073
    # 0x08: addi x2, x0, 0x60            # S payload address
    instr_mem[2] = 0x06000113
    # 0x0C: csrrw x0, mepc, x2           # mepc = 0x60
    instr_mem[3] = 0x34111073
    # 0x10: addi x3, x0, 0x80            # M-mode trap handler address
    instr_mem[4] = 0x08000193
    # 0x14: csrrw x0, mtvec, x3          # mtvec = 0x80
    instr_mem[5] = 0x30519073
    # 0x18: mret                         # enter S-mode at mepc
    instr_mem[6] = 0x30200073

    # S-mode payload at 0x60 (word index 24).
    # 0x60: addi x5, x0, 0x5A            # S-mode sentinel before ecall
    instr_mem[24] = 0x05A00293
    # 0x64: ecall                        # trap to M-mode mtvec
    instr_mem[25] = 0x00000073
    # 0x68: addi x6, x0, 0x66            # skipped by trap redirect
    instr_mem[26] = 0x06600313

    # M-mode handler at 0x80 (word index 32).
    # 0x80: addi x7, x0, 0x77            # handler sentinel
    instr_mem[32] = 0x07700393
    # 0x84: jal x0, 0                    # hold PC here
    instr_mem[33] = 0x0000006F

    await run_csr_test_program(dut, instr_mem)

    x5 = int(dut.rf_inst0.register_file[5].value)
    x6 = int(dut.rf_inst0.register_file[6].value)
    x7 = int(dut.rf_inst0.register_file[7].value)
    privilege_mode = int(dut.csr_file_inst.privilege_mode.value)
    mcause = int(dut.csr_file_inst.mcause.value)
    mstatus = int(dut.csr_file_inst.mstatus.value)
    mpp = (mstatus >> 11) & 0x3

    print(f"x5 (S-mode pre-ecall sentinel): {x5:#x}")
    print(f"x6 (skipped S-mode post-ecall sentinel): {x6:#x}")
    print(f"x7 (M-mode handler sentinel): {x7:#x}")
    print(f"privilege_mode={privilege_mode:#x}, mcause={mcause:#x}, mstatus={mstatus:#x}, MPP={mpp:#x}")

    assert x5 == 0x5A, f"S-mode payload did not execute before ecall: x5={x5:#x}"
    assert x6 == 0x0, f"Trap did not redirect away from S-mode fallthrough: x6={x6:#x}"
    assert x7 == 0x77, f"M-mode trap handler did not execute: x7={x7:#x}"
    assert privilege_mode == 0x3, f"Expected M-mode after S-mode ecall, got {privilege_mode:#x}"
    assert mcause == 0x9, f"Expected S-mode ecall mcause=9, got {mcause:#x}"
    assert mpp == 0x1, f"Expected MPP=S after S-mode ecall trap, got {mpp:#x}"

    print("S-mode ECALL-to-M-mode test passed!")

@cocotb.test()
async def test_supervisor_ecall_machine_mret_returns_to_supervisor(dut):
    """Test S-mode ECALL handled in M-mode can return to S-mode with MRET."""
    print("Starting S-mode ECALL/M-mode MRET return test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    NOP = 0x00000013
    instr_mem = [NOP] * 56

    # M-mode setup.
    # 0x00: lui x1, 0x1                  # x1 = 0x1000 (MPP bit 12)
    instr_mem[0] = 0x000010B7
    # 0x04: csrrc x0, mstatus, x1        # clear MPP[1], leaving MPP=S (01)
    instr_mem[1] = 0x3000B073
    # 0x08: addi x2, x0, 0x60            # S payload address
    instr_mem[2] = 0x06000113
    # 0x0C: csrrw x0, mepc, x2           # mepc = 0x60
    instr_mem[3] = 0x34111073
    # 0x10: addi x3, x0, 0xA0            # M-mode trap handler address
    instr_mem[4] = 0x0A000193
    # 0x14: csrrw x0, mtvec, x3          # mtvec = 0xA0
    instr_mem[5] = 0x30519073
    # 0x18: mret                         # enter S-mode at mepc
    instr_mem[6] = 0x30200073

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
    # 0xA4: csrrs x8, mepc, x0           # x8 = trapped ecall PC
    instr_mem[41] = 0x34102473
    # 0xA8: addi x8, x8, 4               # skip ecall on return
    instr_mem[42] = 0x00440413
    # 0xAC: csrrw x0, mepc, x8           # mepc = ecall PC + 4
    instr_mem[43] = 0x34141073
    # 0xB0: mret                         # return to S payload after ecall
    instr_mem[44] = 0x30200073

    await run_csr_test_program(dut, instr_mem)

    x5 = int(dut.rf_inst0.register_file[5].value)
    x6 = int(dut.rf_inst0.register_file[6].value)
    x7 = int(dut.rf_inst0.register_file[7].value)
    x8 = int(dut.rf_inst0.register_file[8].value)
    privilege_mode = int(dut.csr_file_inst.privilege_mode.value)
    mcause = int(dut.csr_file_inst.mcause.value)
    mepc = int(dut.csr_file_inst.mepc.value)
    mstatus = int(dut.csr_file_inst.mstatus.value)
    mpp = (mstatus >> 11) & 0x3

    print(f"x5 (S pre-ecall): {x5:#x}")
    print(f"x6 (S post-mret): {x6:#x}")
    print(f"x7 (M handler): {x7:#x}")
    print(f"x8 (handler-adjusted mepc): {x8:#x}")
    print(f"privilege_mode={privilege_mode:#x}, mcause={mcause:#x}, mepc={mepc:#x}, MPP={mpp:#x}")

    assert x5 == 0x5A, f"S-mode payload did not execute before ecall: x5={x5:#x}"
    assert x7 == 0x77, f"M-mode ecall handler did not execute: x7={x7:#x}"
    assert x8 == 0x68, f"Handler did not observe/advance mepc correctly: x8={x8:#x}"
    assert x6 == 0x66, f"MRET did not resume S-mode after ecall: x6={x6:#x}"
    assert privilege_mode == 0x1, f"Expected S-mode after MRET, got {privilege_mode:#x}"
    assert mcause == 0x9, f"Expected S-mode ecall mcause=9, got {mcause:#x}"
    assert mepc == 0x68, f"Expected final mepc=0x68, got {mepc:#x}"
    assert mpp == 0x0, f"MRET should clear MPP after return, got {mpp:#x}"

    print("S-mode ECALL/M-mode MRET return test passed!")

@cocotb.test()
async def test_delegated_supervisor_timer_interrupt_sret(dut):
    """Test delegated supervisor timer interrupt traps to stvec and resumes."""
    print("Starting delegated S-mode timer interrupt/SRET test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    NOP = 0x00000013
    instr_mem = [NOP] * 56

    # M-mode setup.
    # 0x00: lui x1, 0x1                  # x1 = 0x1000 (MPP bit 12)
    instr_mem[0] = 0x000010B7
    # 0x04: csrrc x0, mstatus, x1        # clear MPP[1], leaving MPP=S (01)
    instr_mem[1] = 0x3000B073
    # 0x08: addi x2, x0, 0x60            # S payload address
    instr_mem[2] = 0x06000113
    # 0x0C: csrrw x0, mepc, x2           # mepc = 0x60
    instr_mem[3] = 0x34111073
    # 0x10: addi x3, x0, 0xA0            # S trap handler address
    instr_mem[4] = 0x0A000193
    # 0x14: csrrw x0, stvec, x3          # stvec = 0xA0
    instr_mem[5] = 0x10519073
    # 0x18: addi x4, x0, 0x20            # supervisor timer bit
    instr_mem[6] = 0x02000213
    # 0x1C: csrrw x0, mideleg, x4        # mideleg[5] = 1
    instr_mem[7] = 0x30321073
    # 0x20: csrrw x0, sie, x4            # sie.STIE = 1
    instr_mem[8] = 0x10421073
    # 0x24: csrrw x0, sip, x4            # sip.STIP = 1
    instr_mem[9] = 0x14421073
    # 0x28: csrrsi x0, sstatus, 2        # sstatus.SIE = 1
    instr_mem[10] = 0x10016073
    # 0x2C: mret                         # enter S-mode at mepc
    instr_mem[11] = 0x30200073

    # S-mode payload at 0x60 (word index 24).
    # 0x60: addi x5, x0, 0x5A            # runs after interrupt handler returns
    instr_mem[24] = 0x05A00293
    # 0x64: jal x0, -4                   # hold PC here
    instr_mem[25] = 0xFFDFF06F

    # S-mode interrupt handler at 0xA0 (word index 40).
    # 0xA0: addi x7, x0, 0x77            # handler sentinel
    instr_mem[40] = 0x07700393
    # 0xA4: csrrs x8, sepc, x0           # capture interrupted PC
    instr_mem[41] = 0x14102473
    # 0xA8: csrrc x0, sip, x4            # clear STIP
    instr_mem[42] = 0x14423073
    # 0xAC: sret                         # return to interrupted S-mode code
    instr_mem[43] = 0x10200073

    await run_csr_test_program(dut, instr_mem)

    x5 = int(dut.rf_inst0.register_file[5].value)
    x7 = int(dut.rf_inst0.register_file[7].value)
    x8 = int(dut.rf_inst0.register_file[8].value)
    privilege_mode = int(dut.csr_file_inst.privilege_mode.value)
    scause = int(dut.csr_file_inst.scause.value)
    sip = int(dut.csr_file_inst.sip.value)
    mstatus = int(dut.csr_file_inst.mstatus.value)
    spp = (mstatus >> 8) & 0x1

    print(f"x5 (S payload): {x5:#x}")
    print(f"x7 (S timer handler): {x7:#x}")
    print(f"x8 (captured sepc): {x8:#x}")
    print(f"privilege_mode={privilege_mode:#x}, scause={scause:#x}, sip={sip:#x}, SPP={spp:#x}")

    assert x7 == 0x77, f"S-mode timer handler did not execute: x7={x7:#x}"
    assert x5 == 0x5A, f"SRET did not resume S-mode payload: x5={x5:#x}"
    assert x8 in (0x60, 0x64), f"Unexpected interrupted S-mode PC in sepc: x8={x8:#x}"
    assert privilege_mode == 0x1, f"Expected S-mode after timer sret, got {privilege_mode:#x}"
    assert scause == 0x80000005, f"Expected supervisor timer interrupt scause, got {scause:#x}"
    assert (sip & 0x20) == 0, f"Handler should clear STIP, sip={sip:#x}"
    assert spp == 0x0, f"SRET should clear SPP, got {spp:#x}"

    print("Delegated S-mode timer interrupt/SRET test passed!")

@cocotb.test()
async def test_delegated_supervisor_ebreak_sret(dut):
    """Test delegated S-mode EBREAK traps to stvec and resumes with SRET."""
    print("Starting delegated S-mode EBREAK/SRET test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    NOP = 0x00000013
    instr_mem = [NOP] * 56

    # M-mode setup.
    # 0x00: lui x1, 0x1                  # x1 = 0x1000 (MPP bit 12)
    instr_mem[0] = 0x000010B7
    # 0x04: csrrc x0, mstatus, x1        # clear MPP[1], leaving MPP=S (01)
    instr_mem[1] = 0x3000B073
    # 0x08: addi x2, x0, 0x60            # S payload address
    instr_mem[2] = 0x06000113
    # 0x0C: csrrw x0, mepc, x2           # mepc = 0x60
    instr_mem[3] = 0x34111073
    # 0x10: addi x3, x0, 0xA0            # S trap handler address
    instr_mem[4] = 0x0A000193
    # 0x14: csrrw x0, stvec, x3          # stvec = 0xA0
    instr_mem[5] = 0x10519073
    # 0x18: addi x4, x0, 0x8             # delegate exception cause 3
    instr_mem[6] = 0x00800213
    # 0x1C: csrrw x0, medeleg, x4        # medeleg[3] = 1
    instr_mem[7] = 0x30221073
    # 0x20: csrrw x0, mcause, x0         # clear stale harness/reset artifact
    instr_mem[8] = 0x34201073
    # 0x24: mret                         # enter S-mode at mepc
    instr_mem[9] = 0x30200073

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

    await run_csr_test_program(dut, instr_mem)

    x5 = int(dut.rf_inst0.register_file[5].value)
    x6 = int(dut.rf_inst0.register_file[6].value)
    x7 = int(dut.rf_inst0.register_file[7].value)
    x8 = int(dut.rf_inst0.register_file[8].value)
    privilege_mode = int(dut.csr_file_inst.privilege_mode.value)
    scause = int(dut.csr_file_inst.scause.value)
    sepc = int(dut.csr_file_inst.sepc.value)
    mcause = int(dut.csr_file_inst.mcause.value)
    mstatus = int(dut.csr_file_inst.mstatus.value)
    spp = (mstatus >> 8) & 0x1

    print(f"x5 (S pre-ebreak): {x5:#x}")
    print(f"x6 (S post-sret): {x6:#x}")
    print(f"x7 (S handler): {x7:#x}")
    print(f"x8 (handler-adjusted sepc): {x8:#x}")
    print(f"privilege_mode={privilege_mode:#x}, scause={scause:#x}, sepc={sepc:#x}, mcause={mcause:#x}, SPP={spp:#x}")

    assert x5 == 0x5A, f"S-mode payload did not execute before ebreak: x5={x5:#x}"
    assert x7 == 0x77, f"S-mode trap handler did not execute: x7={x7:#x}"
    assert x8 == 0x68, f"Handler did not observe/advance sepc correctly: x8={x8:#x}"
    assert x6 == 0x66, f"SRET did not resume after ebreak: x6={x6:#x}"
    assert privilege_mode == 0x1, f"Expected S-mode after sret, got {privilege_mode:#x}"
    assert scause == 0x3, f"Expected delegated S-mode ebreak scause=3, got {scause:#x}"
    assert sepc == 0x68, f"Expected final sepc=0x68, got {sepc:#x}"
    assert mcause == 0x0, f"Delegated S-mode ebreak should not update mcause, got {mcause:#x}"
    assert spp == 0x0, f"SRET should clear SPP, got {spp:#x}"

    print("Delegated S-mode EBREAK/SRET test passed!")

@cocotb.test()
async def test_csr_invalid_access(dut):
    """Test access to invalid CSR addresses"""
    print("Starting invalid CSR access test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Program to test invalid CSR access:
    instr_mem = [
        # Try to access an invalid CSR (address 0x123)
        0x12302173,  # csrrs x2, 0x123, x0    # Should read 0 from invalid CSR
        
        # Valid CSR for comparison
        0x34002273,  # csrrs x4, mscratch, x0  # Should read valid CSR
    ]

    await run_csr_test_program(dut, instr_mem)
    
    # Verify invalid CSR returns 0
    invalid_csr_value = int(dut.rf_inst0.register_file[2].value)
    valid_csr_value = int(dut.rf_inst0.register_file[4].value)
    
    print(f"Invalid CSR read: {invalid_csr_value:#x}")
    print(f"Valid CSR read: {valid_csr_value:#x}")
    
    assert invalid_csr_value == 0, "Invalid CSR should return 0"

    print("Invalid CSR access test passed!")

@cocotb.test()
async def test_csr_mret(dut):
    """Test trap entry via ecall and return via mret.

    Validates the trap spine RTOS ports depend on:
      - ecall sets mcause = 11 (env call from M-mode) and saves mepc
      - trap entry saves MIE -> MPIE, clears MIE, jumps to mtvec
      - mret restores MIE from MPIE (and jumps to mepc)
    """
    print("Starting mret test...")

    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.module_instr_in.value = 0
    dut.module_read_data_in.value = 0
    dut.rst.value = 1
    await Timer(20, units="ns")
    dut.rst.value = 0
    await RisingEdge(dut.clk)

    # Pad instruction memory so the handler at PC=0x40 (word index 16)
    # lands in a valid slot. run_csr_test_program fetches via pc//4.
    NOP = 0x00000013
    instr_mem = [NOP] * 32

    # 0x00: addi x1, x0, 0x40              # handler address
    instr_mem[0] = 0x04000093
    # 0x04: csrrw x0, mtvec, x1            # mtvec = 0x40
    instr_mem[1] = 0x30509073
    # 0x08: csrrsi x0, mstatus, 8          # set MIE = 1
    instr_mem[2] = 0x30046073
    # 0x0C: addi x5, x0, 0xAA              # pre-ecall sentinel
    instr_mem[3] = 0x0AA00293
    # 0x10: ecall                          # trap to mtvec
    instr_mem[4] = 0x00000073
    # 0x14: addi x6, x0, 0xBB              # executes only if mret returned here
    instr_mem[5] = 0x0BB00313

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

    await run_csr_test_program(dut, instr_mem)

    # Pre-ecall sentinel must have run.
    x5 = int(dut.rf_inst0.register_file[5].value)
    print(f"x5 (pre-ecall sentinel): {x5:#x}")
    assert x5 == 0xAA, f"Pre-ecall path did not execute: x5={x5:#x}"

    # ecall must set mcause = 11 (env call from M-mode).
    mcause = int(dut.csr_file_inst.mcause.value)
    mepc   = int(dut.csr_file_inst.mepc.value)
    print(f"mcause: {mcause:#x}, mepc: {mepc:#x}")
    assert mcause == 0xB, f"ecall should set mcause=11, got {mcause:#x}"

    # Handler must have executed - proves mtvec redirect worked.
    x7 = int(dut.rf_inst0.register_file[7].value)
    print(f"x7 (handler sentinel): {x7:#x}")
    assert x7 == 0xCC, f"Handler did not execute: x7={x7:#x}"

    # mret must restore MIE from MPIE. MIE was set before ecall, so trap
    # entry moves MIE(1) -> MPIE, clears MIE; mret must restore MIE = 1.
    mstatus = int(dut.csr_file_inst.mstatus.value)
    mie_bit = (mstatus >> 3) & 1
    print(f"mstatus after mret: {mstatus:#x} (MIE={mie_bit})")
    assert mie_bit == 1, f"mret did not restore MIE from MPIE: mstatus={mstatus:#x}"

    print("mret test passed!")

from cocotb_test.simulator import run

def runCocotbTests():
    # All Verilog sources under rtl directory and subdirectories
    sources = []
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    print(f"Using RTL directory: {root_dir}/rtl")
    rtl_dir = os.path.join(root_dir, "rtl")
    incl_dir = os.path.join(rtl_dir, "include")
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith(".v") or file.endswith(".sv"):
                sources.append(os.path.join(root, file))
    
    # Define the CSR tests
    tests = [
        "test_csr_basic_operations",
        "test_csr_mstatus_operations",
        "test_csr_cycle_counter",
        "test_mret_enters_supervisor_mode",
        "test_supervisor_ecall_traps_to_machine_mode",
        "test_supervisor_ecall_machine_mret_returns_to_supervisor",
        "test_delegated_supervisor_timer_interrupt_sret",
        "test_delegated_supervisor_ebreak_sret",
        "test_csr_invalid_access",
        "test_csr_mret",
    ]
    
    enable_waves = os.getenv("WAVES", "0") == "1"
    waveform_dir = None
    if enable_waves:
        curr_dir = os.getcwd()
        waveform_dir = os.path.join(curr_dir, "waveforms")
        if not os.path.exists(waveform_dir):
            os.makedirs(waveform_dir)
        waveform_dir = os.path.abspath("waveforms")
    
    # Run each test with its own waveform file
    for test_name in tests:
        print(f"\n=== Running {test_name} ===")
        plus_args = []
        if enable_waves:
            waveform_path = os.path.join(waveform_dir, f"{test_name}.fst")
            plus_args = ["--trace", "--trace-file", waveform_path,
                         f"+dumpfile={waveform_path}"]
        
        run(
            verilog_sources=sources,
            toplevel="riscv_cpu",
            module="test_csr",
            testcase=test_name,
            includes=[str(incl_dir)],
            simulator="verilator",
            timescale="1ns/1ps",
            waves=enable_waves,
            plus_args=plus_args,
        )

if __name__ == "__main__":
    runCocotbTests()
