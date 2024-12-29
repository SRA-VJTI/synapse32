/**
 * @file riscv_cpu.v
 * 
 * This module implements the bare CPU modules and interconnects various signals
 * of the submodules.
 * 
 * @input clk                       Inputs the clock signal.
 * @input reset                     Inputs the reset signal.
 * @input Instr                     Inputs the instruction from the instruction memory.
 * @input ReadData                  Inputs the data read from memory.
 *
 * @output PC                       Outputs the program counter value.
 * @output MemWrite                 Outputs the memory write enable signal.
 * @output Mem_WrAddr               Outputs the memory write address.
 * @output Mem_WrData               Outputs the data to be written to memory.
 * 
 * @internal Jump_ADDR              Internal signal for the jump address.
 * @internal IMM_ADDR               Internal signal for the immediate address.
 * @internal alu_instruction        Internal signal for ALU instruction.
 * @internal ProgramCounter         Internal signal for the program counter value.
 * @internal source_val1            Internal signal for the value of the first source register.
 * @internal source_val2            Internal signal for the value of the second source register.
 * @internal ALUoutput              Internal signal for the ALU output.
 * @internal opcode                 Internal signal for the operation code.
 * @internal out_signal             Internal signal for the control unit output signals.
 * @internal destination_register   Internal signal for the destination register.
 * @internal final_output           Internal signal for the final output value.
 * @internal rs1                    Internal signal for the first source register.
 * @internal rs2                    Internal signal for the second source register.
 * @internal input_val1             Internal signal for the first ALU input value.
 * @internal input_val2             Internal signal for the second ALU input value.
 * @internal mtvec                  Internal signal for the machine trap-vector base-address register.
 * @internal csr_addr               Internal signal for the CSR address.
 * @internal csr_data               Internal signal for the CSR data to be written.
 * @internal csr_rdata              Internal signal for the data read from the CSR.
 * @internal Jump_sign              Internal signal indicating a jump operation.
 * @internal rs1_valid              Internal signal indicating if the first source register is valid.
 * @internal rs2_valid              Internal signal indicating if the second source register is valid.
 * @internal registerfile_write     Internal signal for enabling write operations in the register file.
 * @internal trap_detected          Internal signal indicating if a trap is detected.
 * @internal i_is_ebreak            Internal signal indicating if the current instruction is EBREAK.
 */



module riscv_cpu (
    input           clk, reset,
    input  [31:0]   ReadData,
    input  [31:0]   Instr,

    output [31:0]   PC,
    output [31:0]   Mem_WrAddr, Mem_WrData,
    output          MemWrite
);

wire [31:0] Jump_ADDR;
wire [31:0] IMM_ADDR;
wire [15:0] alu_instruction;
wire [31:0] ProgramCounter;
wire [31:0] source_val1;
wire [31:0] source_val2;
wire [63:0] ALUoutput;
wire [06:0] opcode;
wire [60:0] out_signal;
wire [31:0] destination_register;
wire [31:0] final_output;
wire [04:0] rs1;
wire [04:0] rs2;
wire [31:0] input_val1;
wire [31:0] input_val2;
wire [11:0] csr_addr;
wire [31:0] csr_data;
wire [31:0] csr_rdata;
wire        Jump_sign;
wire        rs1_valid;
wire        rs2_valid;
wire        registerfile_write;


assign PC = ProgramCounter;
PC b2v_inst(
    .clk            (   clk                 ),
    .reset          (   reset               ),
    .j_signal       (   Jump_sign           ),
    .jump           (   Jump_ADDR           ),
    .out_sign       (   ProgramCounter      )
);

alu b2v_inst1(
    .instructions   (   alu_instruction     ),
    .in1            (   input_val1          ),
    .in2            (   input_val2          ),
    .ALUoutput      (   ALUoutput           )
);

csr csr_0 (
    .clk            (   clk                 ),
    .rst            (   reset               ),
    .csr_wr_en      (   csr_wr_en           ),
    .csr_ren        (   csr_ren             ),
    .addr           (   csr_addr            ),
    .wr_data        (   csr_data            ),
    .rdata          (   csr_rdata           ),
    .i_is_ebreak    (   i_is_ebreak         ),
    .i_is_ecall     (   i_is_ecall          )
);

control_unit b2v_inst2(
    .clk            (   clk                 ),
    .rst            (   reset               ),
    .rs1_input      (   source_val1         ),
    .csr_wr_en      (   csr_wr_en           ),
    .csr_ren        (   csr_ren             ),
    .rs2_input      (   source_val2         ),
    .imm            (   IMM_ADDR            ),
    .mem_read       (   ReadData            ),
    .out_signal     (   out_signal          ),
    .opcode         (   opcode              ),
    .pc_input       (   ProgramCounter      ),
    .ALUoutput      (   ALUoutput           ),
    .i_is_ebreak    (   i_is_ebreak         ),
    .i_is_ecall     (   i_is_ecall          ),
    .csr_rdata      (   csr_rdata           ),
    .instructions   (   alu_instruction     ),
    .unsigned_rs1   (   input_val1          ),
    .unsigned_rs2   (   input_val2          ),
    .mem_write      (   Mem_WrData          ),
    .wr_en          (   MemWrite            ),
    .addr           (   Mem_WrAddr          ),
    .j_signal       (   Jump_sign           ),
    .jump           (   Jump_ADDR           ),
    .final_output   (   final_output        ),
    .wr_en_rf       (   registerfile_write  ),
    .csr_wr_data    (   csr_data            ),
    .csr_addr       (   csr_addr            )
);

decoder b2v_inst3(
    .instr          (   Instr               ),
    .rs1_valid      (   rs1_valid           ),
    .rs2_valid      (   rs2_valid           ),
    .imm            (   IMM_ADDR            ),
    .csr_addr       (   csr_addr            ),
    .opcode         (   opcode              ),
    .out_signal     (   out_signal          ),
    .rd             (   destination_register),
    .rs1            (   rs1                 ),
    .rs2            (   rs2                 )
);

registerfile registerfile_0(
    .clk            (   clk                 ),
    .rs1_valid      (   rs1_valid           ),
    .rs2_valid      (   rs2_valid           ),
    .wr_en          (   registerfile_write  ),
    .rd             (   destination_register),
    .rd_value       (   final_output        ),
    .rs1            (   rs1                 ),
    .rs2            (   rs2                 ),
    .rs1_value      (   source_val1         ),
    .rs2_value      (   source_val2         )
);

endmodule