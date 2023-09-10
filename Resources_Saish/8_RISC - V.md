

"RISC", in fact, stands for "reduced instruction set computing" and contrasts with "complex instruction set computing" (CISC). RISC-V is the fifth in a series of RISC ISAs from UC Berkeley. You will implement the core instructions of the base RISC-V instruction set (RV32I), which contains just 47 instructions. Of these, you will implement 31 (Of the remaining 16, 10 have to do with the surrounding system, and 6 provide support for storing and loading small values to and from memory).

Like other RISC (and even CISC) ISAs, RISC-V is a _load-store architecture_. It contains a register file capable of storing up to 32 values (well, actually 31). Most instructions read from and write back to the register file. Load and store instructions transfer values between memory and the register file.

RISC-V instructions may provide the following fields:

- **opcode**  
    Provides a general classification of the instruction and determines which of the remaining fields are needed, and how they are laid out, or encoded, in the remaining instruction bits.
- **function field** (funct3/funct7)  
    Specifies the exact function performed by the instruction, if not fully specified by the opcode.
- **rs1/rs2**  
    The indices (0-31) identifying the register(s) in the register file containing the source operand values on which the instruction operates.
- **rd**  
    The index (0-31) of the register into which the instruction’s result is written.
- **immediate**  
    A value contained within the instruction bits themselves. This value may provide an offset for indexing into memory or a value upon which to operate (in place of the register value indexed by rs2).

All instructions are 32 bits. The R-type encoding provides a general layout of the instruction fields used by all instruction types. R-type instructions have no immediate value. Other instruction types use a subset of the R-type fields and provide an immediate value in the remaining bits.

![](https://courses.edx.org/assets/courseware/v1/3f0c44f5f251e9c795bd0f0671ea7bb3/asset-v1:LinuxFoundationX+LFD111x+3T2022+type@asset+block/RISC-V_base_instruction_formats__from_the_RISC-V_specifications_.png)
