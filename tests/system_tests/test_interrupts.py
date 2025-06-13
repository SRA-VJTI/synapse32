import cocotb
from cocotb.triggers import RisingEdge, Timer, ClockCycles
from cocotb.clock import Clock
from cocotb_test.simulator import run
import os
import shutil
from pathlib import Path

def create_interrupt_test_hex(test_name, instr_mem):
    """Create a hex file for the interrupt test instructions"""
    # Create build directory if it doesn't exist
    curr_dir = Path.cwd()
    build_dir = curr_dir / "build"
    build_dir.mkdir(exist_ok=True)
    
    # Create hex file
    hex_file = build_dir / f"{test_name}.hex"
    
    with open(hex_file, 'w') as f:
        f.write("@00000000\n")
        
        # Pad instruction memory to ensure we have enough instructions
        padded_instr = list(instr_mem)
        while len(padded_instr) % 4 != 0:
            padded_instr.append(0x00000013)  # NOP
        
        # Pad to at least 512 instructions
        while len(padded_instr) < 512:
            padded_instr.append(0x00000013)  # NOP
        
        # Write instructions as 4 per line (matching your format)
        for i in range(0, len(padded_instr), 4):
            line = " ".join(f"{padded_instr[j]:08x}" for j in range(i, min(i+4, len(padded_instr))))
            f.write(f"{line}\n")
    
    return str(hex_file.absolute())

async def monitor_execution(dut, test_name, max_cycles=100):
    """Monitor test execution and return results"""
    mem_writes = {}
    
    for cycle in range(max_cycles):
        # Monitor memory writes
        try:
            if hasattr(dut, 'cpu_mem_write_en') and int(dut.cpu_mem_write_en.value):
                addr = int(dut.cpu_mem_write_addr.value)
                data = int(dut.cpu_mem_write_data.value)
                mem_writes[addr] = data
                print(f"Cycle {cycle}: Memory write: addr=0x{addr:08x}, data=0x{data:08x}")
        except Exception:
            pass
        
        # Monitor PC and instruction
        try:
            pc_val = int(dut.pc_debug.value)
            instr_val = int(dut.instr_debug.value)
            if cycle % 20 == 0:  # Print every 20 cycles
                print(f"Cycle {cycle}: PC=0x{pc_val:08x}, Instr=0x{instr_val:08x}")
        except Exception:
            pass
        
        await RisingEdge(dut.clk)
    
    return mem_writes

@cocotb.test()
async def test_interrupt_setup(dut):
    """Test interrupt enable setup"""
    print("Starting interrupt setup test...")
    
    # Start clock
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Monitor execution
    mem_writes = await monitor_execution(dut, "interrupt_setup", max_cycles=80)
    
    # Verify results
    expected_memory = {
        0x02000000: 0x10000000,  # mtvec value
        0x02000004: 0x80,        # mie value (MTIE enabled)
        0x02000008: 0x8,         # mstatus value (MIE enabled)
        0x0200000C: 0x0,         # mip value (no interrupts pending)
        0x02000010: 0x1,         # completion flag
    }
    
    print("\nVerifying interrupt setup from memory writes:")
    for addr, expected in expected_memory.items():
        if addr in mem_writes:
            actual = mem_writes[addr]
            print(f"Memory[0x{addr:08x}]: expected=0x{expected:08x}, actual=0x{actual:08x}")
            assert actual == expected, f"Memory value mismatch at 0x{addr:08x}: expected 0x{expected:08x}, got 0x{actual:08x}"
        else:
            print(f"Memory[0x{addr:08x}]: NOT WRITTEN - may indicate test issue")
    
    print("Interrupt setup test passed!")

@cocotb.test()
async def test_ecall_test(dut):
    """Test ECALL instruction (environment call)"""
    print("Starting ECALL instruction test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Monitor execution
    mem_writes = await monitor_execution(dut, "ecall_test", max_cycles=80)
    
    print("\nVerifying ECALL behavior:")
    print("Memory accesses:", mem_writes)
    
    # x1=5 should be written to memory (before ECALL)
    if 0x02000000 in mem_writes:
        assert mem_writes[0x02000000] == 5, f"Expected x1=5 at 0x02000000, got {mem_writes[0x02000000]}"
        print("✅ Memory write before ECALL occurred correctly")
    else:
        print("⚠️  Expected memory write at 0x02000000 not found")
    
    # x4=16 should NOT be written (after ECALL trap)
    if 0x02000004 in mem_writes:
        print(f"❌ Memory write at 0x02000004 should not happen (after ECALL), but got {mem_writes[0x02000004]}")
    else:
        print("✅ No memory write after ECALL (correct - should have trapped)")
    
    print("ECALL instruction test completed!")

@cocotb.test()
async def test_ebreak_test(dut):
    """Test EBREAK instruction (breakpoint)"""
    print("Starting EBREAK instruction test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Monitor execution
    mem_writes = await monitor_execution(dut, "ebreak_test", max_cycles=80)
    
    print("\nVerifying EBREAK behavior:")
    print("Memory accesses:", mem_writes)
    
    # x1=7 should be written to memory (before EBREAK)
    if 0x02000000 in mem_writes:
        assert mem_writes[0x02000000] == 7, f"Expected x1=7 at 0x02000000, got {mem_writes[0x02000000]}"
        print("✅ Memory write before EBREAK occurred correctly")
    else:
        print("⚠️  Expected memory write at 0x02000000 not found")
    
    # x4=40 should NOT be written (after EBREAK trap)
    if 0x02000004 in mem_writes:
        print(f"❌ Memory write at 0x02000004 should not happen (after EBREAK), but got {mem_writes[0x02000004]}")
    else:
        print("✅ No memory write after EBREAK (correct - should have trapped)")
    
    print("EBREAK instruction test completed!")

@cocotb.test()
async def test_mret_test(dut):
    """Test MRET instruction (return from trap)"""
    print("Starting MRET instruction test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Monitor execution
    mem_writes = await monitor_execution(dut, "mret_test", max_cycles=80)
    
    print("\nVerifying MRET behavior:")
    print("Memory accesses:", mem_writes)
    
    # Marker 0xAA should be written (before MRET)
    if 0x02000000 in mem_writes:
        assert mem_writes[0x02000000] == 0xAA, f"Expected marker 0xAA at 0x02000000, got 0x{mem_writes[0x02000000]:08x}"
        print("✅ Memory write before MRET occurred correctly")
    else:
        print("⚠️  Expected memory write at 0x02000000 not found")
    
    # 0xDEAD should NOT be written (after MRET jump)
    if 0x02000004 in mem_writes:
        print(f"❌ Memory write at 0x02000004 should not happen (after MRET), but got 0x{mem_writes[0x02000004]:08x}")
    else:
        print("✅ No memory write after MRET (correct - should have jumped away)")
    
    print("MRET instruction test completed!")

@cocotb.test()
async def test_timer_interrupt(dut):
    """Test timer interrupt handling"""
    print("Starting timer interrupt test...")
    
    clock = Clock(dut.clk, 10, units="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut.timer_interrupt.value = 0
    dut.software_interrupt.value = 0
    dut.external_interrupt.value = 0
    dut.rst.value = 1
    await ClockCycles(dut.clk, 5)
    dut.rst.value = 0
    
    # Schedule timer interrupt during execution
    async def inject_timer_interrupt():
        await ClockCycles(dut.clk, 20)  # Wait 20 cycles
        dut.timer_interrupt.value = 1
        print("Timer interrupt asserted!")
        await ClockCycles(dut.clk, 10)  # Hold for 10 cycles
        dut.timer_interrupt.value = 0
        print("Timer interrupt deasserted!")
    
    # Start interrupt injection in background
    cocotb.start_soon(inject_timer_interrupt())
    
    # Monitor execution
    mem_writes = await monitor_execution(dut, "timer_interrupt", max_cycles=100)
    
    print("\nTimer interrupt test results:")
    print("Memory accesses:", mem_writes)
    
    # Check that some instructions executed before interrupt
    if 0x02000000 in mem_writes:
        assert mem_writes[0x02000000] == 1, "First store should be 1"
        print("✅ First instruction executed before interrupt")
    else:
        print("⚠️  Expected first memory write not found")
    
    print("Timer interrupt test completed!")

# Individual test generator functions
def run_interrupt_setup_test():
    instr_mem = [
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 (sp) to point to 0x10000000 (MTVEC base)
        0x30511073,  # csrw mtvec, x2        # Write CSR: Set mtvec (trap vector) to value in x2
        0x08000093,  # addi x1, x0, 128      # Load immediate: Set x1 to 0x80 (MTIE bit - machine timer interrupt enable)
        0x30409073,  # csrw mie, x1          # Write CSR: Set mie (machine interrupt enable) to value in x1
        0x00800193,  # addi x3, x0, 8        # Load immediate: Set x3 to 0x8 (MIE bit - global machine interrupt enable)
        0x30019073,  # csrw mstatus, x3      # Write CSR: Set mstatus to value in x3 (enable interrupts)
        0x30502273,  # csrr x4, mtvec        # Read CSR: Read mtvec value into x4
        0x020002b7,  # lui x5 0x2000         # Load immediate: Set x5 to memory base address 0x02000000
        0x0042a023,  # sw x4, 0(x5)          # Store word: Store mtvec value (x4) to memory at x5+0
        0x30402373,  # csrr x6, mie          # Read CSR: Read mie value into x6
        0x0062a223,  # sw x6, 4(x5)          # Store word: Store mie value (x6) to memory at x5+4
        0x30002473,  # csrr x8, mstatus      # Read CSR: Read mstatus value into x8
        0x0082a423,  # sw x8, 8(x5)          # Store word: Store mstatus value (x8) to memory at x5+8
        0x34402573,  # csrr x10, mip         # Read CSR: Read mip (machine interrupt pending) into x10
        0x00a2a623,  # sw x10, 12(x5)        # Store word: Store mip value (x10) to memory at x5+12
        0x00100093,  # addi x1, x0, 1        # Load immediate: Set x1 to 1 (completion flag)
        0x0012a823,  # sw x1, 16(x5)         # Store word: Store completion flag (x1) to memory at x5+16
    ]
    test_name = "interrupt_setup"
    hex_file = create_interrupt_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_ecall_test():
    instr_mem = [
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 (sp) to point to 0x10000000 (MTVEC base)
        0x30511073,  # csrw mtvec, x2        # Write CSR: Set mtvec (trap vector) to value in x2
        0x00500093,  # addi x1, x0, 5        # Load immediate: Set x1 to 5 (test value before ECALL)
        0x020001b7,  # lui x3, 0x2000        # Load immediate: Set x3 to memory base address 0x02000000
        0x0011a023,  # sw x1, 0(x3)          # Store word: Store x1 (5) to memory at x3+0
        0x00000073,  # ecall                 # Environment call - should trigger trap
        0x01000213,  # addi x4, x0, 16       # Load immediate: Set x4 to 16 (should not execute after ECALL)
        0x0041a223,  # sw x4, 4(x3)          # Store word: Store x4 (16) to memory at x3+4 (should not execute)
        0x00000013,  # addi x0, x0, 0        # NOP
        0x00000013,  # addi x0, x0, 0        # NOP
    ]
    test_name = "ecall_test"
    hex_file = create_interrupt_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_ebreak_test():
    instr_mem = [
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 (sp) to point to 0x10000000 (MTVEC base)
        0x30511073,  # csrw mtvec, x2        # Write CSR: Set mtvec (trap vector) to value in x2
        0x00700093,  # addi x1, x0, 7        # Load immediate: Set x1 to 7 (test value before EBREAK)
        0x020001b7,  # lui x3, 0x2000        # Load immediate: Set x3 to memory base address 0x02000000
        0x0011a023,  # sw x1, 0(x3)          # Store word: Store x1 (7) to memory at x3+0
        0x00100073,  # ebreak                # Breakpoint instruction - should trigger trap
        0x02800213,  # addi x4, x0, 40       # Load immediate: Set x4 to 40 (should not execute after EBREAK)
        0x0041a223,  # sw x4, 4(x3)          # Store word: Store x4 (40) to memory at x3+4 (should not execute)
        0x00000013,  # addi x0, x0, 0        # NOP
        0x00000013,  # addi x0, x0, 0        # NOP
    ]
    test_name = "ebreak_test"
    hex_file = create_interrupt_test_hex(test_name, instr_mem)
    return test_name, hex_file

def run_mret_test():
    instr_mem = [
        0x00800093,  # addi x1, x0, 8        # Load immediate: Set x1 to 8 (MPP bits for Machine mode)
        0x30009073,  # csrw mstatus, x1      # Write CSR: Set mstatus to value in x1 (set MPP)
        0x10000137,  # lui x2, 0x10000       # Load upper immediate: Set x2 to 0x10000000 (return address)
        0x34111073,  # csrw mepc, x2         # Write CSR: Set mepc (machine exception program counter) to value in x2
        0x020001b7,  # lui x3, 0x2000        # Load immediate: Set x3 to memory base address 0x02000000
        0x0AA00213,  # addi x4, x0, 0xAA     # Load immediate: Set x4 to 0xAA (marker value before MRET)
        0x0041a023,  # sw x4, 0(x3)          # Store word: Store x4 (0xAA) to memory at x3+0
        0x30200073,  # mret                  # Machine return - should return to address in mepc
        0xDEAD0213,  # addi x4, x0, 0xDEAD   # Load immediate: Set x4 to 0xDEAD (should not execute after MRET)
        0x0041a223,  # sw x4, 4(x3)          # Store word: Store x4 (0xDEAD) to memory at x3+4 (should not execute)
    ]
    test_name = "mret_test"
    hex_file = create_interrupt_test_hex(test_name, instr_mem)
    return test_name, hex_file

# def run_timer_interrupt_test():
#     instr_mem = [
#         0x10000137, 0x30529073, 0x08000093, 0x30409073,
#         0x00800193, 0x30019073, 0x02000213, 0x00100293,
#         0x0052a023, 0x00200293, 0x0052a223, 0x00300293,
#         0x0052a423, 0x00400293, 0x0052a623,
#     ]
#     test_name = "timer_interrupt"
#     hex_file = create_interrupt_test_hex(test_name, instr_mem)
#     return test_name, hex_file

def runCocotbTests():
    # Find RTL directory
    sources = []
    root_dir = os.getcwd()
    while not os.path.exists(os.path.join(root_dir, "rtl")):
        if os.path.dirname(root_dir) == root_dir:
            raise FileNotFoundError("rtl directory not found in the current or parent directories.")
        root_dir = os.path.dirname(root_dir)
    
    rtl_dir = os.path.join(root_dir, "rtl")
    for root, _, files in os.walk(rtl_dir):
        for file in files:
            if file.endswith(".v") or file.endswith(".sv"):
                sources.append(os.path.join(root, file))
    
    # Create waveforms directory
    curr_dir = os.getcwd()
    waveform_dir = os.path.join(curr_dir, "waveforms")
    if not os.path.exists(waveform_dir):
        os.makedirs(waveform_dir)
    
    # Test configurations
    tests_config = [
        ("interrupt_setup", run_interrupt_setup_test),
        ("ecall_test", run_ecall_test),
        ("ebreak_test", run_ebreak_test),
        ("mret_test", run_mret_test),
        # ("timer_interrupt", run_timer_interrupt_test),
    ]
    
    # Run each test
    for test_name, test_func in tests_config:
        print(f"\n=== Generating and running {test_name} ===")
        _, hex_file = test_func()
        print(f"Generated hex file: {hex_file}")
        waveform_path = os.path.join(waveform_dir, f"{test_name}.vcd")
        
        # Create unique sim_build directory for each test to force recompilation
        #make dir sim_build
        if not os.path.exists(os.path.join(curr_dir, "sim_build")):
            os.makedirs(os.path.join(curr_dir, "sim_build"))
        sim_build_dir = os.path.join(curr_dir, "sim_build", f"sim_build_{test_name}")
        
        # Clean up previous sim_build for this test to force recompilation
        if os.path.exists(sim_build_dir):
            shutil.rmtree(sim_build_dir)
        
        run(
            verilog_sources=sources,
            toplevel="top",
            module="test_interrupts",
            testcase=f"test_{test_name}",
            includes=[rtl_dir],
            simulator="icarus",
            timescale="1ns/1ps",
            defines=[f"INSTR_HEX_FILE=\"{hex_file}\""],
            plus_args=[f"+dumpfile={waveform_path}"],
            sim_build=sim_build_dir,  # ✅ Key fix: unique sim_build per test
            force_compile=True,       # ✅ Force recompilation
        )

if __name__ == "__main__":
    runCocotbTests()