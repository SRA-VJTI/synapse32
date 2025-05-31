`default_nettype none
`include "instr_defines.vh"
module alu(
    input  wire [31:0] rs1,
    input  wire [31:0] rs2,
    input  wire [31:0] imm,
    input  wire [5:0]  instr_id,
    input  wire [31:0] pc_input,
    output reg  [31:0] ALUoutput
);

localparam [1:0] SS = 2'b11,
                 SU = 2'b10,
                 UU = 2'b00;

wire [1:0] mm = (instr_id==INSTR_MULHU)  ? UU :
                (instr_id==INSTR_MULHSU) ? SU : SS;

wire [63:0] op1  = mm[1] ? {{32{rs1[31]}},rs1} : {32'b0,rs1};
wire [63:0] op2  = mm[0] ? {{32{rs2[31]}},rs2} : {32'b0,rs2};
wire [63:0] prod = op1 * op2;

wire signed [31:0] rs1_s = rs1;
wire signed [31:0] rs2_s = rs2;
wire signed [31:0] quot_s = (rs2!=0)? rs1_s/rs2_s : 0;
wire        [31:0] quot_u = (rs2!=0)? rs1  /rs2   : 0;
wire signed [31:0] rem_s  = (rs2!=0)? rs1_s%rs2_s : 0;
wire        [31:0] rem_u  = (rs2!=0)? rs1  %rs2   : 0;

always @* begin
    case(instr_id)
        INSTR_ADD   : ALUoutput = rs1 + rs2;
        INSTR_SUB   : ALUoutput = rs1 - rs2;
        INSTR_XOR   : ALUoutput = rs1 ^ rs2;
        INSTR_OR    : ALUoutput = rs1 | rs2;
        INSTR_AND   : ALUoutput = rs1 & rs2;
        INSTR_SLL   : ALUoutput = rs1 << rs2[4:0];
        INSTR_SRL   : ALUoutput = rs1 >> rs2[4:0];
        INSTR_SRA   : ALUoutput = rs1_s >>> rs2[4:0];
        INSTR_SLT   : ALUoutput = {32{rs1_s < rs2_s}};
        INSTR_SLTU  : ALUoutput = {32{rs1   < rs2  }};
        INSTR_ADDI  : ALUoutput = rs1 + imm;
        INSTR_XORI  : ALUoutput = rs1 ^ imm;
        INSTR_ORI   : ALUoutput = rs1 | imm;
        INSTR_ANDI  : ALUoutput = rs1 & imm;
        INSTR_SLLI  : ALUoutput = rs1 << imm[4:0];
        INSTR_SRLI  : ALUoutput = rs1 >> imm[4:0];
        INSTR_SRAI  : ALUoutput = rs1_s >>> imm[4:0];
        INSTR_SLTI  : ALUoutput = {32{rs1_s < $signed(imm)}};
        INSTR_SLTIU : ALUoutput = {32{rs1   < imm         }};
        INSTR_MUL    : ALUoutput = prod[31:0];
        INSTR_MULH   : ALUoutput = prod[63:32];
        INSTR_MULHSU : ALUoutput = prod[63:32];
        INSTR_MULHU  : ALUoutput = prod[63:32];
        INSTR_DIV    : ALUoutput = quot_s;
        INSTR_DIVU   : ALUoutput = quot_u;
        INSTR_REM    : ALUoutput = rem_s;
        INSTR_REMU   : ALUoutput = rem_u;
        default      : ALUoutput = 0;
    endcase
end
endmodule
