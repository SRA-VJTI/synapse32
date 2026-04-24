// Instruction Decode Constants

`ifndef INSTR_DEFINES_VH
`define INSTR_DEFINES_VH

// R-type
localparam [6:0] INSTR_ADD   = 7'h01;
localparam [6:0] INSTR_SUB   = 7'h02;
localparam [6:0] INSTR_XOR   = 7'h03;
localparam [6:0] INSTR_OR    = 7'h04;
localparam [6:0] INSTR_AND   = 7'h05;
localparam [6:0] INSTR_SLL   = 7'h06;
localparam [6:0] INSTR_SRL   = 7'h07;
localparam [6:0] INSTR_SRA   = 7'h08;
localparam [6:0] INSTR_SLT   = 7'h09;
localparam [6:0] INSTR_SLTU  = 7'h0A;

// R-type M extension
localparam [6:0] INSTR_MUL    = 7'h30;
localparam [6:0] INSTR_MULH   = 7'h31;
localparam [6:0] INSTR_MULHSU = 7'h32;
localparam [6:0] INSTR_MULHU  = 7'h33;
localparam [6:0] INSTR_DIV    = 7'h34;
localparam [6:0] INSTR_DIVU   = 7'h35;
localparam [6:0] INSTR_REM    = 7'h36;
localparam [6:0] INSTR_REMU   = 7'h37;

// I-type arithmetic
localparam [6:0] INSTR_ADDI  = 7'h0B;
localparam [6:0] INSTR_XORI  = 7'h0C;
localparam [6:0] INSTR_ORI   = 7'h0D;
localparam [6:0] INSTR_ANDI  = 7'h0E;
localparam [6:0] INSTR_SLLI  = 7'h0F;
localparam [6:0] INSTR_SRLI  = 7'h10;
localparam [6:0] INSTR_SRAI  = 7'h11;
localparam [6:0] INSTR_SLTI  = 7'h12;
localparam [6:0] INSTR_SLTIU = 7'h13;

// Loads
localparam [6:0] INSTR_LB    = 7'h14;
localparam [6:0] INSTR_LH    = 7'h15;
localparam [6:0] INSTR_LW    = 7'h16;
localparam [6:0] INSTR_LBU   = 7'h17;
localparam [6:0] INSTR_LHU   = 7'h18;

// Stores
localparam [6:0] INSTR_SB    = 7'h19;
localparam [6:0] INSTR_SH    = 7'h1A;
localparam [6:0] INSTR_SW    = 7'h1B;

// Branches
localparam [6:0] INSTR_BEQ   = 7'h1C;
localparam [6:0] INSTR_BNE   = 7'h1D;
localparam [6:0] INSTR_BLT   = 7'h1E;
localparam [6:0] INSTR_BGE   = 7'h1F;
localparam [6:0] INSTR_BLTU  = 7'h20;
localparam [6:0] INSTR_BGEU  = 7'h21;

// Jumps
localparam [6:0] INSTR_JAL   = 7'h22;
localparam [6:0] INSTR_JALR  = 7'h23;

// U-type
localparam [6:0] INSTR_LUI   = 7'h24;
localparam [6:0] INSTR_AUIPC = 7'h25;

// System instructions
localparam [6:0] INSTR_FENCE_I = 7'h26;

// CSR instructions
localparam [6:0] INSTR_CSRRW  = 7'h27;
localparam [6:0] INSTR_CSRRS  = 7'h28;
localparam [6:0] INSTR_CSRRC  = 7'h29;
localparam [6:0] INSTR_CSRRWI = 7'h2A;
localparam [6:0] INSTR_CSRRSI = 7'h2B;
localparam [6:0] INSTR_CSRRCI = 7'h2C;

// System instructions (add these after CSR instructions)
localparam [6:0] INSTR_MRET    = 7'h2D;
localparam [6:0] INSTR_ECALL   = 7'h2E;
localparam [6:0] INSTR_EBREAK  = 7'h2F;
localparam [6:0] INSTR_WFI     = 7'h38;

// RV32A instruction IDs
localparam [6:0] INSTR_LR_W       = 7'h40;
localparam [6:0] INSTR_SC_W       = 7'h41;
localparam [6:0] INSTR_AMOSWAP_W  = 7'h42;
localparam [6:0] INSTR_AMOADD_W   = 7'h43;
localparam [6:0] INSTR_AMOAND_W   = 7'h44;
localparam [6:0] INSTR_AMOOR_W    = 7'h45;
localparam [6:0] INSTR_AMOXOR_W   = 7'h46;
localparam [6:0] INSTR_AMOMAX_W   = 7'h47;
localparam [6:0] INSTR_AMOMIN_W   = 7'h48;
localparam [6:0] INSTR_AMOMAXU_W  = 7'h49;
localparam [6:0] INSTR_AMOMINU_W  = 7'h4A;

// Unknown or NOP
localparam [6:0] INSTR_INVALID = 7'h00;

`endif
