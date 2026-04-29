TOPLEVEL_LANG = verilog
VERILATOR = verilator
TOPLEVEL = top
MODULE = opensbi_uart
SIM = verilator

ROOT_DIR := $(abspath $(CURDIR)/..)
PYTHON_BIN ?= python3
INSTRUCTION_MEMORY_HEX ?= $(abspath $(CURDIR)/opensbi.hex)
SIM_BUILD ?= $(CURDIR)/sim_build_opensbi
WAVES ?= 0

VERILOG_SOURCES = $(wildcard $(ROOT_DIR)/rtl/**/*.v)
VERILOG_SOURCES += $(wildcard $(ROOT_DIR)/rtl/*.v)
INCLUDES = -I$(ROOT_DIR)/rtl/include -I$(ROOT_DIR)/rtl
EXTRA_ARGS = $(INCLUDES) --trace -DINSTR_HEX_FILE=\"$(INSTRUCTION_MEMORY_HEX)\"

export PYTHONPATH := $(CURDIR):$(PYTHONPATH)
export COCOTB_LOG_LEVEL ?= INFO
export COCOTB_REDUCED_LOG_FMT ?= 1
export BOOT_TIMEOUT_CYCLES ?= 5000000
export UART_IDLE_CYCLES ?= 200000
export STATUS_INTERVAL_CYCLES ?= 250000
export CLOCK_PERIOD_NS ?= 20

ifeq ($(WAVES),1)
DUMPFILE ?= $(CURDIR)/waveforms/opensbi_boot.fst
PLUSARGS += +dumpfile=$(DUMPFILE)
endif

include $(shell $(PYTHON_BIN) -m cocotb.config --makefiles)/Makefile.sim
