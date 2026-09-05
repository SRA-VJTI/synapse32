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

wire signed [31:0] rs1_signed = $signed(rs1);
wire signed [31:0] rs2_signed = $signed(rs2);
wire signed [63:0] rs1_signed_ext = {{32{rs1[31]}}, rs1};
wire signed [63:0] rs2_signed_ext = {{32{rs2[31]}}, rs2};
wire [63:0] rs1_unsigned_ext = {32'b0, rs1};
wire [63:0] rs2_unsigned_ext = {32'b0, rs2};
wire signed [63:0] mul_signed = rs1_signed_ext * rs2_signed_ext;
wire signed [63:0] mul_mixed = rs1_signed_ext * $signed(rs2_unsigned_ext);
wire [63:0] mul_unsigned = rs1_unsigned_ext * rs2_unsigned_ext;
wire div_by_zero = (rs2 == 0);
wire div_overflow = (rs1 == 32'h80000000) && (rs2 == 32'hFFFFFFFF);

`ifdef FORMAL
    // Simplified ALU for formal verification - only basic operations
    always @(*) begin
        case (instr_id)
            INSTR_ADD:   ALUoutput = rs1 + rs2;
            INSTR_SUB:   ALUoutput = rs1 - rs2;
            INSTR_XOR:   ALUoutput = rs1 ^ rs2;
            INSTR_OR:    ALUoutput = rs1 | rs2;
            INSTR_AND:   ALUoutput = rs1 & rs2;
            INSTR_ADDI:  ALUoutput = rs1 + imm;
            INSTR_XORI:  ALUoutput = rs1 ^ imm;
            INSTR_ORI:   ALUoutput = rs1 | imm;
            INSTR_ANDI:  ALUoutput = rs1 & imm;
            default:     ALUoutput = 32'h0;
        endcase
    end
`else
    // Full ALU implementation for synthesis
    always @(*) begin
        case (instr_id)
            INSTR_ADD:   ALUoutput = $signed(rs1) + $signed(rs2);
            INSTR_SUB:   ALUoutput = $signed(rs1) - $signed(rs2);
            INSTR_XOR:   ALUoutput = rs1 ^ rs2;
            INSTR_OR:    ALUoutput = rs1 | rs2;
            INSTR_AND:   ALUoutput = rs1 & rs2;
            INSTR_SLL:   ALUoutput = rs1 << rs2[4:0];
            INSTR_SRL:   ALUoutput = rs1 >> rs2[4:0];
            INSTR_SRA:   ALUoutput = $signed(rs1) >>> rs2[4:0];
            INSTR_SLT:   ALUoutput = {31'b0, $signed(rs1) < $signed(rs2)};
            INSTR_SLTU:  ALUoutput = {31'b0, rs1 < rs2};
            INSTR_ADDI:  ALUoutput = $signed(rs1) + $signed(imm);
            INSTR_XORI:  ALUoutput = rs1 ^ imm;
            INSTR_ORI:   ALUoutput = rs1 | imm;
            INSTR_ANDI:  ALUoutput = rs1 & imm;
            INSTR_SLLI:  ALUoutput = rs1 << imm[4:0];
            INSTR_SRLI:  ALUoutput = rs1 >> imm[4:0];
            INSTR_SRAI:  ALUoutput = $signed(rs1) >>> imm[4:0];
            INSTR_SLTI:  ALUoutput = {31'b0, $signed(rs1) < $signed(imm)};   // bugfix: returns 1 or 0
            INSTR_SLTIU: ALUoutput = {31'b0, rs1 < imm};                     // bugfix: returns 1 or 0
            INSTR_MUL:   ALUoutput = mul_signed[31:0];
            INSTR_MULH:  ALUoutput = mul_signed[63:32];
            INSTR_MULHSU: ALUoutput = mul_mixed[63:32];
            INSTR_MULHU: ALUoutput = mul_unsigned[63:32];
            INSTR_DIV: begin
                if (div_by_zero)       ALUoutput = 32'hFFFFFFFF;
                else if (div_overflow) ALUoutput = 32'h80000000;
                else                   ALUoutput = rs1_signed / rs2_signed;
            end
            INSTR_DIVU: begin
                if (div_by_zero) ALUoutput = 32'hFFFFFFFF;
                else             ALUoutput = rs1 / rs2;
            end
            INSTR_REM: begin
                if (div_by_zero)       ALUoutput = rs1;
                else if (div_overflow) ALUoutput = 32'h00000000;
                else                   ALUoutput = rs1_signed % rs2_signed;
            end
            INSTR_REMU: begin
                if (div_by_zero) ALUoutput = rs1;
                else             ALUoutput = rs1 % rs2;
            end
            default:     ALUoutput = 0;
        endcase
    end
`endif
endmodule
