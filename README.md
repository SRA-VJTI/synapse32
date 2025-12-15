# Synapse-32

Synapse-32 is a 32-bit RISC-V CPU core written in Verilog, supporting RV32I instructions, along with Zicsr and Zifencei extensions.

## Processor Architecture

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


## Formal Verification

Formal verification of the Synapse-32 CPU is performed using [Yosys's riscv-formal](https://github.com/cliffordwolf/riscv-formal) together with [SymbiYosys (SBY)](https://symbiyosys.readthedocs.io/en/latest/).

### Prerequisites

- [Yosys](https://yosyshq.net/yosys/)
- [SymbiYosys (`sby`)](https://symbiyosys.readthedocs.io/en/latest/)
- [Boolector](https://boolector.github.io/) (the `.sby` files are configured for `smtbmc boolector` by default) or another SMT solver supported by SymbiYosys
- Python 3.8+

Verify that these tools are in your `PATH`:

```bash
yosys -V
sby --version
boolector --version
python3 --version
```

### Running the Suite

The top-level driver lives in `formal/run_verification_suite.py` and automatically runs every integration, system, and per-instruction SymbiYosys job:

```bash
cd formal
python3 run_verification_suite.py
```

Useful options:

- `--workers N` limits the number of parallel jobs (defaults to the number of CPU cores, capped at 8).
- `--timeout SECONDS` overrides the per-test timeout (default 300 s).
- `--categories ...` narrows the run to any subset of `instructions`, `system`, `integration`.

While the suite runs, live progress is printed, and a machine-readable summary is written to `formal/verification_report.json`. Individual job directories (e.g. `formal/instructions/verify_instructions_add/`) contain the SBY logs and traces for debugging failing proofs.

### Cleaning Generated Artifacts

The suite leaves only transient artifacts—handled by `.gitignore`—but you can wipe them manually when needed:

```bash
find formal/instructions -maxdepth 1 -type d -name 'verify_instructions*' -exec rm -rf {} +
find formal -maxdepth 2 -type d -name 'verify_*' -exec rm -rf {} +
rm -f formal/verification_report.json
```

### Verification Flow

- Initialize the riscv-formal submodule (once per clone):
  ```bash
  git submodule update --init --recursive
  ```
- The verification environment is set up in the `formal/` directory, with integration tests and instruction-specific checks in subfolders.
- SBY configuration files (e.g., `formal/integration/verify_rv32i.sby`) define the verification tasks, including the modules to check, properties to prove, and the engines to use. By default they use `smtbmc boolector`; to use another solver, edit the `[engines]` section accordingly.
- The [riscv-formal](https://github.com/YosysHQ/riscv-formal) framework provides a set of formal properties for RISC-V cores, which are instantiated and checked against the Synapse-32 design.
- To run a verification task, use:
   ```bash
   cd formal
   python run_verification_suite.py
   ```
- The results and counterexamples (if any) are generated in the corresponding output folders.

### What Is Verified

- The CPU is checked for compliance with the RV32I instruction set and correct pipeline behavior.
- Properties such as correct instruction execution, hazard handling, and control flow are formally proven using riscv-formal checkers.
- Additional checks can be added for integration and fault scenarios.

### Interpreting Results

- If all properties are proven, the verification passes.
- If a counterexample is found, the output folder will contain traces to help debug the issue.

### Acknowledgements and Resources

- [SRA VJTI Eklavya 2023](https://sravjti.in/)
- https://www.chipverify.com/verilog/verilog-tutorial
- https://www.edx.org/course/building-a-risc-v-cpu-core
