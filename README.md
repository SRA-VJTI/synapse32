# Synapse-32

Synapse-32 is a 32-bit RISC-V CPU core written in Verilog, supporting RV32IMA instructions, along with Zicsr, Zifencei, and Zihintpause.

## Processor Architecture

Detailed block diagrams are available in [docs/system_diagram.md](docs/system_diagram.md).

### 5-Stage Pipeline
This processor implements a classic 5-stage RISC pipeline:

1. **IF (Instruction Fetch)**: 
   - Fetches the next instruction from instruction memory
   - Updates the Program Counter (PC)

2. **ID (Instruction Decode)**:
   - Decodes the instruction
   - Reads values from register file
   - Generates immediate values and control signals

3. **EX (Execute)**:
   - Performs ALU operations
   - Calculates branch/jump addresses
   - Makes branch decisions

4. **MEM (Memory Access)**:
   - Performs memory reads and writes
   - Handles load and store instructions

5. **WB (Write Back)**:
   - Writes results back to the register file
   - Selects appropriate data source (ALU or memory)

### Pipeline Hazard Handling

The CPU implements several techniques to handle pipeline hazards:

1. **Data Forwarding**:
   - Resolves Read-After-Write (RAW) hazards
   - Forwards data from EX/MEM and MEM/WB stages to the EX stage
   - Avoids pipeline stalls in most cases

2. **Load-Use Hazard Detection**:
   - Detects when an instruction immediately needs data from a preceding load
   - Inserts pipeline stalls when necessary

3. **Control Hazard Management**:
   - Handles branch and jump instructions
   - Flushes the pipeline when branches are taken
   - Supports efficient control flow

### MMU Organization

MMU-specific RTL now lives under [`rtl/mmu/`](rtl/mmu). The current Sv32 page-walk
and unified backing-memory implementation is in [`rtl/mmu/unified_mem.v`](rtl/mmu/unified_mem.v).

## Running Code on the CPU

To compile the CPU and view the simulation, you need to have the following tools installed:

- [Icarus Verilog](https://steveicarus.github.io/iverilog/usage/installation.html)
- [Verilator](https://verilator.org/guide/latest/install.html)
- [Gtkwave](https://gtkwave.sourceforge.net/)
- [Cocotb](https://cocotb.readthedocs.io/en/stable/)

You can write any C program to test the CPU, we provide a linker and startup file to help you with that. You can find the linker script and startup file in the `sim` folder of this repository. An example hello world program is provided in the `sim` folder as well.

### Compiling the CPU and Running Simulation of the Example Program

To compile the CPU and run the simulation of the example hello world program, follow these steps:

1. Navigate to the `sim` folder in your cloned repository:
   ```bash
   cd sim
   ```
2. Create a virtual environment and install the required dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use .venv\Scripts\activate
   pip install -r ../tests/requirements.txt # install cocotb and other dependencies
   ```

3. Compile the CPU using python script:
   ```bash
   python run_c_code.py test_uart_hello.c
   ```

The helper script `run_c_code.py` will compile the C code, generate the necessary files, and run the simulation using verilator. It will also generate a waveform file for viewing in GTKWave.

## CPU Regression Tests

The CPU comes with a set of regression tests to ensure its functionality. These tests cover various aspects of the CPU, including instruction execution, pipeline behavior, and hazard handling.

These tests are written in Python using the Cocotb framework, which allows for writing testbenches in Python and simulating them with Verilog.

To run the regression tests, follow these steps:

1. Navigate to the `tests` folder in your cloned repository:
   ```bash
   cd tests
   ```
2. Create a virtual environment and install the required dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows use .venv\Scripts\
   pip install -r requirements.txt
   ```
3. Run the regression tests using pytest:
   ```bash
   pytest
   ```

## Booting OpenSBI In Simulation

There is a dedicated OpenSBI simulation flow under [`sim/`](sim). It builds the
firmware image, loads it into Verilator, and streams UART output live.

From inside the devcontainer or Docker environment:

```bash
cd sim
make opensbi-run
```

Useful targets:

- `make deps` installs the Python simulator dependencies into `/workspace/.venv`
- `make opensbi-build` rebuilds `sim/.out/opensbi/opensbi.hex`
- `make uart-run` boots the current `IMAGE` without rebuilding OpenSBI
- `make opensbi-waves` keeps an FST waveform at `sim/.out/waveforms/opensbi_boot.fst`

Useful overrides:

```bash
make uart-run IMAGE=$PWD/.out/opensbi/opensbi.hex BOOT_TIMEOUT_CYCLES=8000000 UART_IDLE_CYCLES=300000
```

## Booting Linux In Simulation

The Linux image flow lives under [`sim/`](sim). It builds:

- a Linux kernel image
- a BusyBox-based initramfs
- an OpenSBI `fw_payload`

The initramfs now hands off to BusyBox `init` and respawns a shell on `ttyS0`.

```bash
cd sim
make linux-build
make linux-run
```

`make linux-build` uses the local toolchain when it is available on a Linux host.
On macOS or on hosts without the required RISC-V/Linux build dependencies, it
falls back to the existing Docker image automatically and writes the generated
artifacts back into `sim/.out/linux/`.

### Interactive Linux Console

For normal interactive use, prefer the PTY-backed serial flow instead of the
older stdin bridge:

```bash
cd sim
make docker-linux-build   # or: make linux-build
make linux-pty-local
```

That starts the simulator on the host and exposes the guest UART as a host PTY
symlink at `sim/.out/synapse32-tty`.

Attach from a second terminal with:

```bash
picocom -q -b 115200 sim/.out/synapse32-tty
```

or:

```bash
screen sim/.out/synapse32-tty 115200
```

Use `Ctrl-A d` to detach from `screen` without stopping the simulator. `Ctrl-]`
terminates the simulator session.

The PTY flow also keeps raw UART logs under `sim/.out/`:

- `linux-pty-uart.log` for guest TX output
- `linux-pty-input.log` for host-to-guest input

Useful targets:

- `make docker-linux-build` rebuilds the Linux/OpenSBI payload in Docker
- `make linux-pty-local` runs the current Linux image with a host PTY
- `make linux-pty` rebuilds Linux if needed, then runs the PTY flow
- `make docker-linux-clean` removes the persistent Linux build container

### Available Tests

The regression tests include:
- **Basic Arithmetic Operations**: Tests for addition, subtraction, and other arithmetic instructions.
- **Decoder Tests**: Verifies the instruction decoding logic.
- **Hazard Handling Tests**: Ensures that data forwarding and hazard detection work correctly.
- **Control Flow Tests**: Validates branch and jump instructions.
- **Memory Access Tests**: Checks load and store operations.
- **CSR Tests**: Validates the control and status register operations.
- **UART Tests**: Validates the UART communication functionality.

## Contributors

- [Saish Karole](https://github.com/saishock1504)
- [Atharva Kashalkar](https://github.com/RapidRoger18)
- [Zain Siddavatam](https://github.com/SuperChamp234)
- [Chanchal Bahrani](https://github.com/Chanchal1010)
- [Shri Vishakh Devanand](https://github.com/5iri)

### Acknowledgements and Resources

- [SRA VJTI Eklavya 2023](https://sravjti.in/)
- https://www.chipverify.com/verilog/verilog-tutorial
- https://www.edx.org/course/building-a-risc-v-cpu-core
