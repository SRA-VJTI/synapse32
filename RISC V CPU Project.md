
# RISC-V CPU Report 

# Introduction
RISC-V  is an instruction set architecture like ARM based on RISC (Reduced Instruction Set Architecture) principles. What sets RISC-V ISA different from others ISAs is its completely open source and free to use.

Due to being open-source in nature, RISC-V provides a vital step in designing, building and testing new hardware without paying any license fees or royalties

# Project Overview
Our project aims to create a RISC-V CPU on an Upduino 3.0 FPGA using Verilog HDL. Quartus Prime IDE and Modelsim-Altera along with GTKwave was used to simulate and debug the CPU before programming the hardware

To achieve this, resources like Steeve Hoover's edX course on RISC-V CPU on TL-Verilog, Chipverify's Verilog documentation and HDLBits to practice and sharpen up the concepts of designing techniques in verilog are used to reach the conclusion of the project

# Acknowledgement 
This project saw the daylight due to the mentorship program of Eklavya by SRA-VJTI, whose members helped me on every obstracle which ultimately shaped this project 

Our entire project went under the guidance of our mentors, Zain Siddavatam and Chanchal Bahrani. They are the reason why this project was developed on such a scale in short amount of time

The Society of Robotics and Automation (SRA) community of VJTI has created a nice ecosystem to grow and learn something new and to explore various domains. From having weekly update meets and doubts sessions, our mentors took efforts to see if we don’t go off track during this entire program. The edX course and various resources across the internet helped us to clear our doubts.

# Table of Contents

| Sr No. | Title                                   |
| ------ | --------------------------------------- |
| 1      | Sofwares Used                           |
| 2      | Workflow                                |
| 3      | Components of CPU                       |
| 3.1    | Program Counter                         |
| 3.2    | Instruction Memory                      |
| 3.3    | Decoder                                 |
| 3.4    | Register File                           |
| 3.5    | Control Unit                            |
| 3.6    | Arithmetic Logic Unit                   |
| 3.7    | Data Memory                             | 
| 3.8    | Binary to BCD Converter                 |
| 3.9    | Seven Segment Display                   |
| 4      | FPGA                                    |
| 5      | Conclusion                              |

## Software used 
Intel Quartus Prime IDE with Modelsim-Altera and GTKwave for simulation testing. Upduino 3.0 FPGA was used and the code was flashed with the help of lattice framework consisting of yosys, icepack, nextpnr to convert the code in binary format before flashing. All the commands are executed with the help of Makefile


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

Following is the block diagram and workflow in simple terms of our CPU:-
![image.png](https://hackmd.io/_uploads/rJScfOEXT.png)


![image.png](https://hackmd.io/_uploads/rk-YYoMXp.png)



## Components of CPU 
Following are the components of our RISC-V CPU:-
#### Program Counter 
Program counter(or PC)in the CPU holds the address of the next instructions that is to be executed. It's output is then send to Imem and Control unit for further execution
![image.png](https://hackmd.io/_uploads/B1GmUTQQp.png)



#### Instruction memory 
Instruction memory(or Imem in short) is an instruction bank containing all the instructions needed for the CPU to execute its function. These instructions are accessed from the addresses received from PC. It's output is then send to Decoder for further execution on the instructions

![image.png](https://hackmd.io/_uploads/HkJfKaX76.png)


#### Decoder 
Decoder is the module where we decode all the needed data from the received 32 bit instructions. This data is important as it tells what operations we have to execute and which register we have to access to store the values. It's output is then send to register file, control unit and ALU for further execution
![image.png](https://hackmd.io/_uploads/ryTDaT7m6.png)



#### Register file 
Register file is the module where we store the values of operands that will used for executing the instruction and the final result received from executing the information and also send those stored instructions whenever they are required. It's output is then send to ALU and Control Unit for further execution 
![image.png](https://hackmd.io/_uploads/HkVSb0QQ6.png)

#### Control Unit 
Control Unit can be termed as a heart of the CPU. This module receives decoded instructions and then send those instructions to ALU to perform the specified instructions. If the instructions are branch, jump, load or storing data then these instructions are also handled by Control Unit. It also enables signals for ALU to start the operation and register file and data memory to start storing the output they'll receive. 
![image.png](https://hackmd.io/_uploads/HkFVT0XQp.png)



#### Arithmatic Logic Unit 
Arithmatic Logic Unit (or ALU in short) is the brain behind the calculations happens in the CPU. According to received instructions, ALU performs the required operations like add, subtract, multiply, divide, etc. After these operations, the data is then send to Control Unit back
![image.png](https://hackmd.io/_uploads/Skrd-xV7a.png)



#### Data Memory 
Data memory in a computer is a much longer, volatile data storage which can be used to store data for an intermediate term, data which cannot be held in the register file. It can be read and written only once at a time, since writing to the same memory location while reading can lead to some errors in writing. This module gets its input and send its output to Control Unit whenever it is required according to the instructions 
![image.png](https://hackmd.io/_uploads/r1CyJxNm6.png)


#### Binary to BCD converter 
This module's main function is to convert the 32 bits binary output into 32 bits BCD (Binary Coded Decimal) output for the Seven Segment Display. Binary is converted into BCD using shift operators. It receives instructions from Control Unit and then send it to Seven Segment Display module. 
![image.png](https://hackmd.io/_uploads/H18vMgVmp.png)


#### Seven Segment Display 
This module receives output in the form of BCD and then send bits according to the BCD to seven segment display to activate it![7-segment-display-pin-diagr_0.png](https://hackmd.io/_uploads/S1JxLq47a.png)
.
The Display will show the final output of the CPU.
![image.png](https://hackmd.io/_uploads/H15vBx4Qa.png)


## FPGA
Field Programmable Gate Arrays (FPGAs) are integrated circuits that can be reprogrammed to meet specific use case requirements after manufacturing. They contain configurable logic blocks (CLBs) and programmable interconnects that allow designers to connect blocks and configure them to perform everything from simple logic gates to complex functions.
FPGAs also have a simpler architecture, which can result in faster performance.
FPGAs can be customized to perform specific tasks, which can lead to more efficient and faster processing along with a lot of compatibility for parallel processing.
![c8gwswxdxiu61.png](https://hackmd.io/_uploads/Bkg6Y5EQp.png)


## Conclusion
From above project, we have successfully implemented a RISC-V architecture that can execute RV321 and RV32M instructions on a FPGA

We also got to explore basics of computer architecture, FPGA programming and mathematical operations at a bit level and how circuits can be made to do all of these.