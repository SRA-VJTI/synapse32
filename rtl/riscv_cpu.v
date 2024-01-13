module riscv_cpu (
    input clk, reset,
    output [31:0] PC,
    input  [31:0] Instr,
    output MemWrite,
    output [31:0] Mem_WrAddr, Mem_WrData,
    input  [31:0] ReadData
);

// Uncomment the following lines if you are going to use module instantiation method

// wire ALUSrc, RegWrite, Jump, Zero;
// wire [1:0] ResultSrc, ImmSrc;
// wire [2:0] ALUControl;

// controller c (Instr[6:0], Instr[14:12], Instr[30], Zero,
//              ResultSrc, MemWrite, PCSrc,
//              ALUSrc, RegWrite, Jump, Op5, ImmSrc, ALUControl);

// datapath dp (clk, reset, ResultSrc, PCSrc, Op5,
//              ALUSrc, RegWrite, ImmSrc, ALUControl,
//              Zero, PC, Instr, Mem_WrAddr, Mem_WrData, ReadData);


wire	SYNTHESIZED_WIRE_0;
wire	[31:0] SYNTHESIZED_WIRE_1;
wire	[31:0] SYNTHESIZED_WIRE_21;
wire	[36:0] SYNTHESIZED_WIRE_3;
wire	[31:0] SYNTHESIZED_WIRE_22;
wire	[31:0] SYNTHESIZED_WIRE_23;
wire	[31:0] SYNTHESIZED_WIRE_24;
wire	[31:0] SYNTHESIZED_WIRE_7;
wire	[6:0] SYNTHESIZED_WIRE_9;
wire	[36:0] SYNTHESIZED_WIRE_10;
wire	SYNTHESIZED_WIRE_14;
wire	SYNTHESIZED_WIRE_15;
wire	SYNTHESIZED_WIRE_16;
wire	[31:0] SYNTHESIZED_WIRE_17;
wire	[31:0] SYNTHESIZED_WIRE_18;
wire	[4:0] SYNTHESIZED_WIRE_19;
wire	[4:0] SYNTHESIZED_WIRE_20;

assign	PC = SYNTHESIZED_WIRE_22;




PC	b2v_inst(
	.clk(clk),
	.reset(reset),
	.j_signal(SYNTHESIZED_WIRE_0),
	.jump(SYNTHESIZED_WIRE_1),
	.out(SYNTHESIZED_WIRE_22));


alu	b2v_inst1(
	.imm(SYNTHESIZED_WIRE_21),
	.instructions(SYNTHESIZED_WIRE_3),
	.pc_input(SYNTHESIZED_WIRE_22),
	.rs1(SYNTHESIZED_WIRE_23),
	.rs2(SYNTHESIZED_WIRE_24),
	.ALUoutput(SYNTHESIZED_WIRE_7));


control_unit	b2v_inst2(
	.clk(clk),
	.rst(reset),
	.ALUoutput(SYNTHESIZED_WIRE_7),
	.imm(SYNTHESIZED_WIRE_21),
	.mem_read(ReadData),
	.opcode(SYNTHESIZED_WIRE_9),
	.out_signal(SYNTHESIZED_WIRE_10),
	.pc_input(SYNTHESIZED_WIRE_22),
	.rs1_input(SYNTHESIZED_WIRE_23),
	.rs2_input(SYNTHESIZED_WIRE_24),
	.j_signal(SYNTHESIZED_WIRE_0),
	.wr_en_rf(SYNTHESIZED_WIRE_16),
	.wr_en(MemWrite),
	.addr(Mem_WrAddr),
	.final_output(SYNTHESIZED_WIRE_18),
	.instructions(SYNTHESIZED_WIRE_3),
	.jump(SYNTHESIZED_WIRE_1),
	.mem_write(Mem_WrData));


decoder	b2v_inst3(
	.instr(Instr),
	.rs1_valid(SYNTHESIZED_WIRE_14),
	.rs2_valid(SYNTHESIZED_WIRE_15),
	.imm(SYNTHESIZED_WIRE_21),
	.opcode(SYNTHESIZED_WIRE_9),
	.out_signal(SYNTHESIZED_WIRE_10),
	.rd(SYNTHESIZED_WIRE_17),
	.rs1(SYNTHESIZED_WIRE_19),
	.rs2(SYNTHESIZED_WIRE_20));


registerfile	b2v_inst4(
	.clk(clk),
	.rs1_valid(SYNTHESIZED_WIRE_14),
	.rs2_valid(SYNTHESIZED_WIRE_15),
	.wr_en(SYNTHESIZED_WIRE_16),
	.rd(SYNTHESIZED_WIRE_17),
	.rd_value(SYNTHESIZED_WIRE_18),
	.rs1(SYNTHESIZED_WIRE_19),
	.rs2(SYNTHESIZED_WIRE_20),
	.rs1_value(SYNTHESIZED_WIRE_23),
	.rs2_value(SYNTHESIZED_WIRE_24));

endmodule

