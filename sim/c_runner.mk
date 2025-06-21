# Makefile

TOPLEVEL_LANG = verilog
VERILATOR = verilator

# The name of the top-level module in your design
TOPLEVEL = top

# The Python test file (without .py)
MODULE = run_c_code

# RTL sources
VERILOG_SOURCES = $(wildcard $(shell pwd)/../rtl/**/*.v)
VERILOG_SOURCES += $(wildcard $(shell pwd)/../rtl/*.v)
INCLUDES = -I$(shell pwd)/../rtl/include/ -I$(shell pwd)/../rtl/
EXTRA_ARGS = $(INCLUDES)
# Simulator
SIM = verilator

#Check if INSTRUCTION_MEMORY_HEX is set, if not, raise an error
ifndef INSTRUCTION_MEMORY_HEX
$(echo "Error: INSTRUCTION_MEMORY_HEX is not set. Please define it in your environment or Makefile.")
endif

# Optional: Any additional compile flags (Add trace and instruction memory hex file from environment variable)
EXTRA_ARGS += --trace -DINSTR_HEX_FILE=\"$(INSTRUCTION_MEMORY_HEX)\"

include $(shell cocotb-config --makefiles)/Makefile.sim
