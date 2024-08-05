# RISC-V-CPU

---
### Introduction

RISC-V  is an instruction set architecture like ARM based on RISC (Reduced Instruction Set Architecture) principles. What sets RISC-V ISA different from others ISAs is its completely open source and free to use.

Above project is a 32-bit RISC-V CPU core written in Verilog , supporting RV32IM instructions. This CPU has been tested on a simulator with an example program and flashed on an UPduino 3.0 FPGA board using Icestorm toolchain

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
## Workflow
This a 2-stage processor. In the first stage, 
- The instructions are fetched and decoded.
- Values are read from register file.
- Determination of instruction type. 
- Sending necessary parameters to ALU if needed.
- Writing in DMem and sending read signals. 
- Send jump to PC. 

And in 2nd stage,
- Get ALU output
- Read Data from DMem.
- Control Unit writes to register file 
- PC executes jump instruction 
- Show output on seven segment display.




---

### Tech Stack

- Verilog
- Quartus Prime IDE
- Modelsim Altera
- Icarus Verilog
- Verilator
- Gtkwave
- Lattice Framework 
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
---
