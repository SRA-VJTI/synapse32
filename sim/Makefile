SHELL := /bin/bash
.DEFAULT_GOAL := help

ROOT_DIR := $(abspath $(CURDIR)/..)
VENV_DIR ?= $(ROOT_DIR)/.venv
PYTHON ?= python3
VENV_PYTHON := $(VENV_DIR)/bin/python
DEPS_STAMP := $(VENV_DIR)/.sim-deps-stamp
DEPS_IMPORT_CHECK := import cocotb, cocotb_test, find_libpython, pytest, numpy
OUT_DIR ?= $(CURDIR)/.out
OPEN_SBI_OUT_DIR ?= $(OUT_DIR)/opensbi
IMAGE ?= $(OPEN_SBI_OUT_DIR)/opensbi.hex
LINUX_OUT_DIR ?= $(OUT_DIR)/linux
LINUX_IMAGE   ?= $(LINUX_OUT_DIR)/synapse32.hex
SIM_BUILD ?= $(OUT_DIR)/sim_build_opensbi
UART_PTY_LINK ?= $(OUT_DIR)/synapse32-tty
UART_PTY_TRANSCRIPT ?= $(OUT_DIR)/linux-pty-uart.log
UART_PTY_RX_TRANSCRIPT ?= $(OUT_DIR)/linux-pty-input.log
BOOT_TIMEOUT_CYCLES ?= 5000000
UART_IDLE_CYCLES ?= 200000
STATUS_INTERVAL_CYCLES ?= 250000
CLOCK_PERIOD_NS ?= 20
DOCKER_IMAGE ?= synapse32-dev
DOCKER_WORKDIR ?= /workspace
DOCKER_CONTAINER_LINUX ?= synapse32-linux
DOCKER_VENV_DIR ?= /tmp/synapse32-venv
DOCKER_RUN = docker run --rm -v "$(ROOT_DIR):$(DOCKER_WORKDIR)" -w "$(DOCKER_WORKDIR)/sim" $(DOCKER_IMAGE)
HOST_OS := $(shell uname -s)

.PHONY: help venv deps docker-build docker-opensbi-run docker-opensbi-waves opensbi-build opensbi-run opensbi-waves docker-linux-build docker-linux-run docker-linux-clean docker-linux-tty linux-build linux-build-local linux-run linux-run-local linux-tty linux-tty-local linux-pty linux-pty-local uart-run clean

help:
	@printf "\nSynapse32 OpenSBI sim targets:\n"
	@printf "  make deps           Create venv and install cocotb/verilator Python deps\n"
	@printf "  make docker-build   Build the Synapse32 dev image\n"
	@printf "  make docker-opensbi-run   Run OpenSBI boot flow inside Docker\n"
	@printf "  make docker-opensbi-waves Run OpenSBI boot flow with waves inside Docker\n"
	@printf "  make docker-linux-run     Build Linux + initramfs and boot it inside Docker (reuses container)\n"
	@printf "  make docker-linux-clean   Remove the persistent Linux build container\n"
	@printf "  make docker-linux-tty     Interactive TTY session on synapse32 Linux (Ctrl-] to exit)\n"
	@printf "  make linux-pty-local      Boot Linux on the host and expose UART as a PTY symlink\n"
	@printf "  make linux-pty            Build Linux if needed, then expose UART as a host PTY\n"
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
	@if $(VENV_PYTHON) -c '$(DEPS_IMPORT_CHECK)' >/dev/null 2>&1; then \
		echo "Using existing Python sim dependencies from $(VENV_DIR)"; \
	else \
		$(VENV_PYTHON) -m ensurepip --upgrade; \
		$(VENV_PYTHON) -m pip install -r $(ROOT_DIR)/tests/requirements.txt; \
	fi
	touch $(DEPS_STAMP)

docker-build:
	docker build -t $(DOCKER_IMAGE) -f $(ROOT_DIR)/.devcontainer/Dockerfile $(ROOT_DIR)

docker-opensbi-run: docker-build
	$(DOCKER_RUN) make VENV_DIR="$(DOCKER_VENV_DIR)" opensbi-run

docker-opensbi-waves: docker-build
	$(DOCKER_RUN) make VENV_DIR="$(DOCKER_VENV_DIR)" opensbi-waves

docker-linux-shell: docker-build
	docker rm -f $(DOCKER_CONTAINER_LINUX) 2>/dev/null || true
	docker run -d --name $(DOCKER_CONTAINER_LINUX) \
		-v "$(ROOT_DIR):$(DOCKER_WORKDIR)" \
		-w "$(DOCKER_WORKDIR)/sim" \
		$(DOCKER_IMAGE) tail -f /dev/null

docker-linux-build: docker-build
	$(MAKE) docker-linux-shell
	docker exec -w "$(DOCKER_WORKDIR)/sim" $(DOCKER_CONTAINER_LINUX) make linux-build-local

docker-linux-run: docker-build
	@if ! docker inspect $(DOCKER_CONTAINER_LINUX) > /dev/null 2>&1; then \
		$(MAKE) docker-linux-build; \
	fi
	@docker start $(DOCKER_CONTAINER_LINUX) > /dev/null
	docker exec -w "$(DOCKER_WORKDIR)/sim" $(DOCKER_CONTAINER_LINUX) make VENV_DIR="$(DOCKER_VENV_DIR)" deps linux-run-local

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

docker-linux-clean:
	docker rm -f $(DOCKER_CONTAINER_LINUX) 2>/dev/null || true

docker-linux-tty: docker-build
	@if ! docker inspect $(DOCKER_CONTAINER_LINUX) > /dev/null 2>&1; then \
		$(MAKE) docker-linux-build; \
	fi
	@docker start $(DOCKER_CONTAINER_LINUX) > /dev/null
	docker exec -it -w "$(DOCKER_WORKDIR)/sim" $(DOCKER_CONTAINER_LINUX) \
		make VENV_DIR="$(DOCKER_VENV_DIR)" deps linux-tty-local

linux-build:
	@if [ "$(HOST_OS)" != "Linux" ] || ! command -v riscv32-unknown-linux-gnu-gcc >/dev/null 2>&1 || ! command -v riscv64-linux-gnu-gcc >/dev/null 2>&1 || ! command -v dtc >/dev/null 2>&1; then \
		echo "Using Docker for Linux image build..."; \
		$(MAKE) docker-linux-build; \
	else \
		$(MAKE) linux-build-local; \
	fi

linux-build-local:
	LINUX_OUT_DIR="$(LINUX_OUT_DIR)" bash $(CURDIR)/build_linux.sh

linux-run:
	@if [ "$(HOST_OS)" != "Linux" ] || ! command -v riscv32-unknown-linux-gnu-gcc >/dev/null 2>&1 || ! command -v riscv64-linux-gnu-gcc >/dev/null 2>&1 || ! command -v dtc >/dev/null 2>&1; then \
		echo "Using Docker for Linux run..."; \
		$(MAKE) docker-linux-run; \
	else \
		$(MAKE) linux-build; \
		$(MAKE) linux-run-local; \
	fi

linux-run-local: deps
	rm -rf "$(OUT_DIR)/sim_build_linux"
	PATH="$(VENV_DIR)/bin:$$PATH" \
	BOOT_TIMEOUT_CYCLES=250000000 \
	UART_IDLE_CYCLES=80000000 \
	STATUS_INTERVAL_CYCLES="$(STATUS_INTERVAL_CYCLES)" \
	CLOCK_PERIOD_NS="$(CLOCK_PERIOD_NS)" \
	PYTHON_BIN="$(VENV_DIR)/bin/python" \
	WAVES=0 \
	MODULE=linux_tty \
	SIM_BUILD="$(OUT_DIR)/sim_build_linux" \
	$(MAKE) -f $(CURDIR)/opensbi_runner.mk sim \
		INSTRUCTION_MEMORY_HEX="$(abspath $(LINUX_IMAGE))"

linux-tty: deps linux-build linux-tty-local

linux-tty-local: deps
	rm -rf "$(OUT_DIR)/sim_build_linux"
	PATH="$(VENV_DIR)/bin:$$PATH" \
	BOOT_TIMEOUT_CYCLES=250000000 \
	UART_IDLE_CYCLES=80000000 \
	CLOCK_PERIOD_NS="$(CLOCK_PERIOD_NS)" \
	PYTHON_BIN="$(VENV_DIR)/bin/python" \
	INTERACTIVE_TTY=1 \
	WAVES=0 \
	MODULE=linux_tty \
	SIM_BUILD="$(OUT_DIR)/sim_build_linux" \
	$(MAKE) -f $(CURDIR)/opensbi_runner.mk sim \
		INSTRUCTION_MEMORY_HEX="$(abspath $(LINUX_IMAGE))"

linux-pty: deps linux-build linux-pty-local

linux-pty-local: deps
	rm -rf "$(OUT_DIR)/sim_build_linux"
	PATH="$(VENV_DIR)/bin:$$PATH" \
	BOOT_TIMEOUT_CYCLES=250000000 \
	UART_IDLE_CYCLES=80000000 \
	CLOCK_PERIOD_NS="$(CLOCK_PERIOD_NS)" \
	PYTHON_BIN="$(VENV_DIR)/bin/python" \
	UART_PTY=1 \
	UART_PTY_LINK="$(abspath $(UART_PTY_LINK))" \
	UART_PTY_TRANSCRIPT="$(abspath $(UART_PTY_TRANSCRIPT))" \
	UART_PTY_RX_TRANSCRIPT="$(abspath $(UART_PTY_RX_TRANSCRIPT))" \
	WAVES=0 \
	MODULE=linux_tty \
	SIM_BUILD="$(OUT_DIR)/sim_build_linux" \
	$(MAKE) -f $(CURDIR)/opensbi_runner.mk sim \
		INSTRUCTION_MEMORY_HEX="$(abspath $(LINUX_IMAGE))"

clean:
	rm -rf $(OUT_DIR) $(CURDIR)/sim_build $(CURDIR)/sim_build_* $(CURDIR)/results.xml $(CURDIR)/__pycache__ $(CURDIR)/dump.vcd $(CURDIR)/riscv_cpu.fst $(CURDIR)/fw_jump.bin $(CURDIR)/fw_jump.elf $(CURDIR)/opensbi.hex $(CURDIR)/synapse32.dtb
