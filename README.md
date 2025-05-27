# RISC-V-CPU

---
### Introduction

RISC-V  is an instruction set architecture like ARM based on RISC (Reduced Instruction Set Architecture) principles. What sets RISC-V ISA different from others ISAs is its completely open source and free to use.

Above project is a 32-bit RISC-V CPU core written in Verilog , supporting RV32IM instructions. This CPU has been tested on a simulator with an example program and flashed on an UPduino 3.0 FPGA board using Icestorm toolchain

---

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

---

### Instructions to compile the CPU and view simulation

An example C program can be loaded on the CPU’s program memory for operations.(We have provided an example code under `sim/fibonacci.c` for testing purposes).

Using RISC-V toolchain, we compile this C code into binary file and then convert into hex files which will be loaded into Instruction memory of our CPU

To compile Verilog files, we are using both Icarus Verilog and Verilator to cross verify our CPU output which will be simulated on Gtkwave. Installation process of above software are linked below:-

-[Icarus Verilog](https://steveicarus.github.io/iverilog/usage/installation.html)
-[Verilator](https://verilator.org/guide/latest/install.html)
-[Gtkwave](https://gtkwave.sourceforge.net/)

All the necessary commands have been added to the `sim/Makefile`

##### Steps to compile and view simulation-

Navigate to your cloned repository and into the sim folder
``` 
cd RISC_V_CPU/sim  
```
and run the following command to compile with Icarus Verilog
``` 
make sim 
```
or run the following command to compile with Verilator
```
make sim_verilator
```

---
### Instructions to flash the code on FPGA

To flash the code in your FPGA, you must have first have yosys suite installed. Installations can be done from [here](https://github.com/YosysHQ/yosys)

All the necessary commands have been added to the `flash/Makefile`

After installation, navigate to your cloned repository and into the flash folder
```
$ cd RISC-V-CPU/flash
```

and run following command 
```
$ make flash
```

This will create binary file for flashing on FPGA, make sure that your FPGA is connected to your device before running above command

---

### Tech Stack

- Verilog
- Quartus Prime IDE
- Modelsim Altera
- Icarus Verilog
- Verilator
- Gtkwave
- Lattice Framework 
- Python with Cocotb
---

## Contributors

- [Saish Karole](https://github.com/saishock1504)
- [Atharva Kashalkar](https://github.com/RapidRoger18)

--- 
## Mentors 

- [Zain Siddavatam](https://github.com/SuperChamp234)
- [Chanchal Bahrani](https://github.com/Chanchal1010)

---
### Acknowledgements and Resources

- [SRA VJTI Eklavya 2023](https://sravjti.in/)
- https://www.chipverify.com/verilog/verilog-tutorial
- https://www.edx.org/course/building-a-risc-v-cpu-core

### Cocotb Testing Framework

The CPU is thoroughly tested using the Cocotb framework, a Python-based testing framework for hardware design.

#### Setting Up Cocotb Environment
```
cd tests
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### Running Cocotb Tests
```
cd tests/system_tests
python test_riscv_cpu_basic.py
```

#### Available Tests
1. **Raw Hazards Test**: Verifies data forwarding functionality
2. **Control Hazards Test**: Validates branch and jump handling
3. **Memory Hazards Test**: Tests memory operations and store-load hazards

#### Viewing Test Results
Test results are saved as FST waveform files in the `waveforms` directory and can be viewed with GTKWave:
```
gtkwave waveforms/test_riscv_cpu_raw_hazards.fst
```
