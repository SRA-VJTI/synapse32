# Makefile for RISC-V Core

# C file
infile_name := fibonacci
infile := fibonacci.c
build_dir := build

# RISC-V toolchain and flags
CC := riscv64-unknown-elf-gcc
OBJDUMP := riscv64-unknown-elf-objdump
OBJCOPY := riscv64-unknown-elf-objcopy
SIZE := riscv64-unknown-elf-size
CFLAGS := -march=rv32i -mabi=ilp32 --specs=picolibc.specs -O3 -g3 -flto -DPICOLIBC_INTEGER_PRINTF_SCANF -Wall
LDFLAGS := -march=rv32i -mabi=ilp32 --specs=picolibc.specs -O3 -g3 -flto -DPICOLIBC_INTEGER_PRINTF_SCANF
LDFLAGS += -Wl,--gc-sections,--defsym=__flash=0x00000000,--defsym=__flash_size=2048 --crt0=minimal
LDFLAGS += -Wl,--defsym=__ram=0x02000000,--defsym=__ram_size=256,--defsym=__stack_size=64 -Tpicolibc.ld


$(build_dir)/%.o : %.c
	mkdir -p $(build_dir)
	$(CC) $(CFLAGS) -c $^ -o $@
	
$(build_dir)/%.elf : $(build_dir)/%.o
	$(CC) $(LDFLAGS) -o $@ $^
	$(SIZE) -B --common $@

$(build_dir)/%.lss : $(build_dir)/%.elf
	$(OBJDUMP) --visualize-jumps -t -S --source-comment='     ### ' $< -M no-aliases,numeric > $@
machine_code.lss : $(build_dir)/$(infile_name).lss
	mv $^ $@

$(build_dir)/%.bin : $(build_dir)/%.elf
	$(OBJCOPY) -O binary $^ $@

$(build_dir)/%.hex : $(build_dir)/%.bin
	truncate -s 2048 $^
	$(OBJCOPY) --verilog-data-width=4 --reverse-bytes=4 -I binary -O verilog $^ $@

program_dump.hex: $(build_dir)/$(infile_name).hex
	mv $^ $@

.PHONY: generate_hex
generate_hex: program_dump.hex machine_code.lss
	@echo "program_dump.hex and machine_code.lss have been successfully generated from $(infile)" || \
	echo "And therefore, $(infile) could not be converted into binary format. :("

.PHONY: clean
clean_program:
	rm -f $(build_dir)/*.o $(build_dir)/*.elf $(build_dir)/*.lss $(build_dir)/*.bin $(build_dir)/*.hex program_dump.hex machine_code.lss

.PHONY: execute
execute_program: $(infile)
	gcc $^ -o $(build_dir)/$(infile_name).out
	./$(build_dir)/$(infile_name).out
	rm -f $(build_dir)/$(infile_name).out

#-----
TB_DIR = ../tb
BUILD_DIR = build
TOP_MODULE = top
TOP_MODULE_FILE = ../rtl/$(TOP_MODULE).v
TESTBENCH = tb
TESTBENCH_FILE = $(TB_DIR)/$(TESTBENCH).v

INSTRUCTIONS = program_dump.hex

# All Verilog files in the ../rtl/ directory
OTHER_MODULES = $(wildcard ../rtl/*.v)

all: sim

# Simulate the testbench using iverilog
$(BUILD_DIR)/$(TESTBENCH).vvp: $(TESTBENCH_FILE) $(TOP_MODULE_FILE) $(OTHER_MODULES)
	mkdir -p $(BUILD_DIR)
	iverilog -o $@ -s $(TESTBENCH) -D VCD_OUTPUT -D VCD_OUTPUT_FILE=\"$(BUILD_DIR)/$(TESTBENCH).vcd\" $^

$(BUILD_DIR)/$(TESTBENCH).vcd: $(BUILD_DIR)/$(TESTBENCH).vvp $(INSTRUCTIONS)
	vvp $^
	mv $(TESTBENCH).vcd $@

.PHONY: sim
sim: $(BUILD_DIR)/$(TESTBENCH).vcd
	gtkwave $^ --dark -a work_dir.gtkw

#simulating using verilator

TP_CPP_NAME = cpu_tb_cpp
TP_CPP_FILE = $(TESTBENCH)/$(TP_CPP_NAME).cpp
CPP_VCDS = cpu.vcd

# Verilator compilation
obj_dir/V$(TOP_MODULE): $(TOP_MODULE_FILE) $(OTHER_MODULES) $(TP_CPP_FILE)
	verilator --trace --cc --exe --build -j 0 -Wno-LATCH -Wno-COMBDLY -Wno-BLKANDNBLK -Wno-INITIALDLY -Wno-CASEINCOMPLETE -Wno-UNOPTFLAT -Wno-CASEOVERLAP -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND $^

# Execute Verilator simulation
$(CPP_VCDS): obj_dir/V$(TOP_MODULE) $(INSTRUCTIONS)
	./$^

# Create waveform using gtkwave
.PHONY: waveform
waveform: $(CPP_VCDS) obj_dir/V$(TOP_MODULE)
	gtkwave $(CPP_VCDS) --dark -a verilated_cpu.gtkw

.PHONY: clean
clean: clean_program
	rm -rf $(BUILD_DIR) *.bin
	rm -rf *.vcd *.vvp
	rm -rf obj_dir
	rm -f cpu.vcd