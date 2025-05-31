// Instruction Decode Constants

`ifndef INSTR_DEFINES_VH
`define INSTR_DEFINES_VH

// R-type
localparam [5:0] INSTR_ADD   = 6'h01;
localparam [5:0] INSTR_SUB   = 6'h02;
localparam [5:0] INSTR_XOR   = 6'h03;
localparam [5:0] INSTR_OR    = 6'h04;
localparam [5:0] INSTR_AND   = 6'h05;
localparam [5:0] INSTR_SLL   = 6'h06;
localparam [5:0] INSTR_SRL   = 6'h07;
localparam [5:0] INSTR_SRA   = 6'h08;
localparam [5:0] INSTR_SLT   = 6'h09;
localparam [5:0] INSTR_SLTU  = 6'h0A;

// I-type arithmetic
localparam [5:0] INSTR_ADDI  = 6'h0B;
localparam [5:0] INSTR_XORI  = 6'h0C;
localparam [5:0] INSTR_ORI   = 6'h0D;
localparam [5:0] INSTR_ANDI  = 6'h0E;
localparam [5:0] INSTR_SLLI  = 6'h0F;
localparam [5:0] INSTR_SRLI  = 6'h10;
localparam [5:0] INSTR_SRAI  = 6'h11;
localparam [5:0] INSTR_SLTI  = 6'h12;
localparam [5:0] INSTR_SLTIU = 6'h13;

// Loads
localparam [5:0] INSTR_LB    = 6'h14;
localparam [5:0] INSTR_LH    = 6'h15;
localparam [5:0] INSTR_LW    = 6'h16;
localparam [5:0] INSTR_LBU   = 6'h17;
localparam [5:0] INSTR_LHU   = 6'h18;

// Stores
localparam [5:0] INSTR_SB    = 6'h19;
localparam [5:0] INSTR_SH    = 6'h1A;
localparam [5:0] INSTR_SW    = 6'h1B;

// Branches
localparam [5:0] INSTR_BEQ   = 6'h1C;
localparam [5:0] INSTR_BNE   = 6'h1D;
localparam [5:0] INSTR_BLT   = 6'h1E;
localparam [5:0] INSTR_BGE   = 6'h1F;
localparam [5:0] INSTR_BLTU  = 6'h20;
localparam [5:0] INSTR_BGEU  = 6'h21;

// Jumps
localparam [5:0] INSTR_JAL   = 6'h22;
localparam [5:0] INSTR_JALR  = 6'h23;

// U-type
localparam [5:0] INSTR_LUI   = 6'h24;
localparam [5:0] INSTR_AUIPC = 6'h25;

// M Extensions
localparam [5:0] INSTR_MUL   = 6'h26;
localparam [5:0] INSTR_MULH  = 6'h27;
localparam [5:0] INSTR_MULHSU = 6'h28;
localparam [5:0] INSTR_MULHU = 6'h29;
localparam [5:0] INSTR_DIV   = 6'h2A;
localparam [5:0] INSTR_DIVU  = 6'h2B;
localparam [5:0] INSTR_REM   = 6'h2C;
localparam [5:0] INSTR_REMU  = 6'h2D;

// Unknown or NOP
localparam [5:0] INSTR_INVALID = 6'h00;

`endif
