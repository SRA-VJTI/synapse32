# Makefile for RISC-V Core

# This Makefile is used to build and run the RISC-V Core simulation.
# It provides the following commands:
# - make generate_hex: Generates the hexadecimal file for the program.
# - make execute_program: Executes the program using gcc.
# - make sim: Builds and runs the simulation using the iverilog simulator.
# - make sim_verilator: Builds and runs the simulation using Verilator.

# Usage:
# - To generate the hexadecimal file for the program, run:
#   make generate_hex
# - To execute the program using the simulator, run:
#   make execute_program
# - To build and run the simulation using the iverilog simulator, run:
#   make sim
# - To build and run the simulation using Verilator, run:
#   make sim_verilator

# Note: Make sure to set the appropriate variables and paths in this Makefile
#       according to your system configuration, if necessary.

#------ File and Toolchain Config ------
infile_name := fibonacci
build_dir := build

CC := riscv64-unknown-elf-gcc
OBJDUMP := riscv64-unknown-elf-objdump
OBJCOPY := riscv64-unknown-elf-objcopy
SIZE := riscv64-unknown-elf-size

CFLAGS := -march=rv32i -mabi=ilp32 -O3 -g3 -nostdlib -ffreestanding -Wall
LDFLAGS := -nostdlib -Wl,-Tlink.ld -Wl,--no-relax -Wl,-m,elf32lriscv

SRC_C := fibonacci.c
SRC_S := start.S

OBJ_C := $(build_dir)/fibonacci.o
OBJ_S := $(build_dir)/start.o

ELF := $(build_dir)/$(infile_name).elf
BIN := $(build_dir)/$(infile_name).bin
HEX := $(build_dir)/$(infile_name).hex
LSS := $(build_dir)/$(infile_name).lss

#------ Rules ------

.PHONY: generate_hex clean

generate_hex: program_dump.hex machine_code.lss
	@echo "Successfully Built: program_dump.hex and machine_code.lss from $(infile_name).c"

$(OBJ_C): $(SRC_C)
	mkdir -p $(build_dir)
	$(CC) $(CFLAGS) -c $< -o $@

$(OBJ_S): $(SRC_S)
	mkdir -p $(build_dir)
	$(CC) $(CFLAGS) -c $< -o $@

$(ELF): $(OBJ_C) $(OBJ_S)
	$(CC) $(LDFLAGS) -o $@ $^
	$(SIZE) -B --common $@

$(LSS): $(ELF)
	$(OBJDUMP) --visualize-jumps -t -S --source-comment='     ### ' $< -M no-aliases,numeric > $@

machine_code.lss: $(LSS)
	cp $< $@

$(BIN): $(ELF)
	$(OBJCOPY) -O binary $< $@

$(HEX): $(BIN)
	truncate -s 2048 $<
	$(OBJCOPY) --verilog-data-width=4 --reverse-bytes=4 -I binary -O verilog $< $@

program_dump.hex: $(HEX)
	cp $< $@

.PHONY: clean
clean_program:
	rm -f $(build_dir)/*.o $(build_dir)/*.elf $(build_dir)/*.lss $(build_dir)/*.bin $(build_dir)/*.hex program_dump.hex machine_code.lss

.PHONY: execute
execute_program: $(infile)
	gcc $^ -o $(build_dir)/$(infile_name).out
	./$(build_dir)/$(infile_name).out
	rm -f $(build_dir)/$(infile_name).out

#----- Icarus Verilog -----

TB_DIR = ../tb
BUILD_DIR = build
TOP_MODULE = top
TOP_MODULE_FILE = ../rtl/$(TOP_MODULE).v
TESTBENCH = tb
TESTBENCH_FILE = $(TB_DIR)/$(TESTBENCH).v

INSTRUCTIONS = program_dump.hex

# All Verilog files in the ../rtl/ directory
OTHER_MODULES = $(wildcard ../rtl/*.v)

# Simulate the testbench using iverilog
$(BUILD_DIR)/$(TESTBENCH).vvp: $(TESTBENCH_FILE) $(TOP_MODULE_FILE) $(OTHER_MODULES)
	mkdir -p $(BUILD_DIR)
	iverilog -o $@ -s $(TESTBENCH) -D VCD_OUTPUT -D VCD_OUTPUT_FILE=\"$(BUILD_DIR)/$(TESTBENCH).vcd\" $^

# Run the simulation and generate VCD file
$(BUILD_DIR)/$(TESTBENCH).vcd: $(BUILD_DIR)/$(TESTBENCH).vvp $(INSTRUCTIONS)
	vvp $^
	mv $(TESTBENCH).vcd $@

# Create waveform using gtkwave and iverilog
.PHONY: sim
sim: $(BUILD_DIR)/$(TESTBENCH).vcd
	gtkwave $^ --dark -a work_dir.gtkw

#----- Verilator -----

# Simulate using Verilator
TP_CPP_NAME = cpu_tb_cpp
TP_CPP_FILE = $(TESTBENCH)/$(TP_CPP_NAME).cpp
CPP_VCDS = cpu.vcd

# Verilator compilation
obj_dir/V$(TOP_MODULE): $(TOP_MODULE_FILE) $(OTHER_MODULES) $(TP_CPP_FILE)
	verilator --trace --cc --exe --build -j 0 -Wno-LATCH -Wno-COMBDLY -Wno-BLKANDNBLK -Wno-INITIALDLY -Wno-CASEINCOMPLETE -Wno-UNOPTFLAT -Wno-CASEOVERLAP -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND $^

# Execute Verilator simulation
$(CPP_VCDS): obj_dir/V$(TOP_MODULE) $(INSTRUCTIONS)
	./$^

# Create waveform using gtkwave and Verilator
.PHONY: waveform
sim_verilator: $(CPP_VCDS) obj_dir/V$(TOP_MODULE)
	gtkwave $(CPP_VCDS) --dark -a verilated_cpu.gtkw

.PHONY: clean
clean: clean_program
	rm -rf $(BUILD_DIR) *.bin
	rm -rf *.vcd *.vvp
	rm -rf obj_dir
	rm -f cpu.vcd
