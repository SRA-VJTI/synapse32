SHELL := /bin/bash
.DEFAULT_GOAL := help

ROOT_DIR := $(abspath $(CURDIR)/..)
VENV_DIR ?= $(ROOT_DIR)/venv
PYTHON ?= python3
PIP := $(VENV_DIR)/bin/pip
DEPS_STAMP := $(VENV_DIR)/.sim-deps-stamp
OUT_DIR ?= $(CURDIR)/.out
OPEN_SBI_OUT_DIR ?= $(OUT_DIR)/opensbi
IMAGE ?= $(OPEN_SBI_OUT_DIR)/opensbi.hex
SIM_BUILD ?= $(OUT_DIR)/sim_build_opensbi
BOOT_TIMEOUT_CYCLES ?= 5000000
UART_IDLE_CYCLES ?= 200000
STATUS_INTERVAL_CYCLES ?= 250000
CLOCK_PERIOD_NS ?= 20
DOCKER_IMAGE ?= synapse32-dev
DOCKER_WORKDIR ?= /workspace
DOCKER_RUN = docker run --rm -it -v "$(ROOT_DIR):$(DOCKER_WORKDIR)" -w "$(DOCKER_WORKDIR)/sim" $(DOCKER_IMAGE)

.PHONY: help venv deps docker-build docker-opensbi-run docker-opensbi-waves opensbi-build opensbi-run opensbi-waves uart-run clean

help:
	@printf "\nSynapse32 OpenSBI sim targets:\n"
	@printf "  make deps           Create venv and install cocotb/verilator Python deps\n"
	@printf "  make docker-build   Build the Synapse32 dev image\n"
	@printf "  make docker-opensbi-run   Run OpenSBI boot flow inside Docker\n"
	@printf "  make docker-opensbi-waves Run OpenSBI boot flow with waves inside Docker\n"
	@printf "  make opensbi-build  Build sim/.out/opensbi/opensbi.hex inside the current environment\n"
	@printf "  make opensbi-run    Build OpenSBI, boot it in Verilator, and stream UART\n"
	@printf "  make opensbi-waves  Same as opensbi-run, but keep an FST waveform\n"
	@printf "  make uart-run       Run the current IMAGE without rebuilding OpenSBI\n"
	@printf "  make clean          Remove generated sim build directories and results\n\n"
	@printf "Artifacts live under %s\n" "$(OUT_DIR)"
	@printf "Overrides: IMAGE=%s/opensbi.hex BOOT_TIMEOUT_CYCLES=8000000 UART_IDLE_CYCLES=300000\n\n" "$(OPEN_SBI_OUT_DIR)"

$(VENV_DIR)/bin/activate:
	$(PYTHON) -m venv $(VENV_DIR)

venv: $(VENV_DIR)/bin/activate

deps: venv
deps: $(DEPS_STAMP)

$(DEPS_STAMP): $(VENV_DIR)/bin/activate $(ROOT_DIR)/tests/requirements.txt
	$(PIP) install -r $(ROOT_DIR)/tests/requirements.txt
	touch $(DEPS_STAMP)

docker-build:
	docker build -t $(DOCKER_IMAGE) -f $(ROOT_DIR)/.devcontainer/Dockerfile $(ROOT_DIR)

docker-opensbi-run: docker-build
	$(DOCKER_RUN) make opensbi-run

docker-opensbi-waves: docker-build
	$(DOCKER_RUN) make opensbi-waves

opensbi-build:
	SIM_OUT_DIR="$(OPEN_SBI_OUT_DIR)" bash $(CURDIR)/build_opensbi.sh

opensbi-run: deps opensbi-build
	$(MAKE) uart-run IMAGE="$(OPEN_SBI_OUT_DIR)/opensbi.hex"

opensbi-waves: deps opensbi-build
	mkdir -p $(OUT_DIR)/waveforms
	PATH="$(VENV_DIR)/bin:$$PATH" \
	BOOT_TIMEOUT_CYCLES="$(BOOT_TIMEOUT_CYCLES)" \
	UART_IDLE_CYCLES="$(UART_IDLE_CYCLES)" \
	STATUS_INTERVAL_CYCLES="$(STATUS_INTERVAL_CYCLES)" \
	CLOCK_PERIOD_NS="$(CLOCK_PERIOD_NS)" \
	PYTHON_BIN="$(VENV_DIR)/bin/python" \
	WAVES=1 \
	SIM_BUILD="$(SIM_BUILD)" \
	DUMPFILE="$(OUT_DIR)/waveforms/opensbi_boot.fst" \
	$(MAKE) -f $(CURDIR)/opensbi_runner.mk sim INSTRUCTION_MEMORY_HEX="$(abspath $(IMAGE))"

uart-run: deps
	PATH="$(VENV_DIR)/bin:$$PATH" \
	BOOT_TIMEOUT_CYCLES="$(BOOT_TIMEOUT_CYCLES)" \
	UART_IDLE_CYCLES="$(UART_IDLE_CYCLES)" \
	STATUS_INTERVAL_CYCLES="$(STATUS_INTERVAL_CYCLES)" \
	CLOCK_PERIOD_NS="$(CLOCK_PERIOD_NS)" \
	PYTHON_BIN="$(VENV_DIR)/bin/python" \
	WAVES=0 \
	SIM_BUILD="$(SIM_BUILD)" \
	$(MAKE) -f $(CURDIR)/opensbi_runner.mk sim INSTRUCTION_MEMORY_HEX="$(abspath $(IMAGE))"

clean:
	rm -rf $(OUT_DIR) $(CURDIR)/sim_build $(CURDIR)/sim_build_* $(CURDIR)/results.xml $(CURDIR)/__pycache__ $(CURDIR)/dump.vcd $(CURDIR)/riscv_cpu.fst $(CURDIR)/fw_jump.bin $(CURDIR)/fw_jump.elf $(CURDIR)/opensbi.hex $(CURDIR)/synapse32.dtb
