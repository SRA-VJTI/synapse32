`default_nettype none
`include "instr_defines.vh"
module alu (
    input wire [31:0] rs1,
    input wire [31:0] rs2,
    input wire [31:0] imm,
    input wire [ 5:0] instr_id,
    input wire [31:0] pc_input,
    output reg [31:0] ALUoutput
);

    always @(*) begin
        case (instr_id)
            INSTR_ADD:   ALUoutput = rs1 + rs2;   // Addition
            INSTR_SUB:   ALUoutput = rs1 - rs2;   // Subtraction
            INSTR_XOR:   ALUoutput = rs1 ^ rs2;   // Bitwise XOR
            INSTR_OR:    ALUoutput = rs1 | rs2;   // Bitwise OR
            INSTR_AND:   ALUoutput = rs1 & rs2;   // Bitwise AND
            INSTR_SLL:   ALUoutput = rs1 << rs2[4:0];  // Logical left shift
            INSTR_SRL:   ALUoutput = rs1 >> rs2[4:0];  // Logical right shift
            INSTR_SRA:   ALUoutput = $signed(rs1) >>> rs2[4:0];  // Arithmetic right shift
            INSTR_SLT:   ALUoutput = {32{$signed(rs1) < $signed(rs2)}};  // Set less than (signed comparison)
            INSTR_SLTU:  ALUoutput = {32{rs1 < rs2}};  // Set less than (unsigned comparison)
            INSTR_ADDI:  ALUoutput = rs1 + imm;  // Add immediate
            INSTR_XORI:  ALUoutput = rs1 ^ imm;  // Bitwise XOR with immediate
            INSTR_ORI:   ALUoutput = rs1 | imm;  // Bitwise OR with immediate
            INSTR_ANDI:  ALUoutput = rs1 & imm;  // Bitwise AND with immediate
            INSTR_SLLI:  ALUoutput = rs1 << imm[4:0];  // Logical left shift with immediate
            INSTR_SRLI:  ALUoutput = rs1 >> imm[4:0];  // Logical right shift with immediate
            INSTR_SRAI:  ALUoutput = $signed(rs1) >>> imm[4:0];  // Arithmetic right shift with immediate
            INSTR_SLTI:  ALUoutput = {32{$signed(rs1) < $signed(imm)}};  // Set less than immediate (signed comparison)
            INSTR_SLTIU: ALUoutput = {32{rs1 < imm}};  // Set less than immediate (unsigned comparison)
            default:     ALUoutput = 0;  // Default case: output zero
        endcase
    end
endmodule
