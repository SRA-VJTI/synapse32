`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 01.09.2023 09:07:55
// Design Name: 
// Module Name: decoder_tb
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module decoder_tb;
reg clk;
reg [31:0]instr;
wire [31:0] rs2;
wire [31:0] rs1;
wire [31:0] imm;
wire [31:0] rd;
wire [2:0] func3;
wire rd_valid;
wire rs1_valid;
wire rs2_valid;
wire imm_valid;
wire [6:0] opcode;
wire [6:0] func7;
wire func3_valid;
wire func7_valid;
wire [44:0] out_signal;


decoder decoder1(.instr(instr),.rs2(rs2),.rs1(rs1),.imm(imm),.rd(rd),.func3(func3),
                 .rd_valid(rd_valid), .rs1_valid(rs1_valid),.imm_valid(imm_valid), .rs2_valid(rs2_valid),
                 .opcode(opcode),.func7(func7), .func3_valid(func3_valid),.func7_valid(func7_valid),.out_signal(out_signal),.clk(clk));
                 
initial clk=0;

always #10 clk = ~clk;

initial begin


instr= 32'h00000033;
#50;
instr=32'h40000033;
#50;
instr=32'h00004033;
#50 ;
instr=32'h00006033;
#50;
instr=32'h00007033;
#50;
instr=32'h00001033;
#50;
instr=32'h00005033;
#50;
instr=32'h40005033;
#50;
instr=32'h00002033;
#50;
instr=32'h00003033;
#50;
instr=32'h00000013;
#50;
instr=32'h00004013;
#50;
instr=32'h00006013;
#50;
instr=32'h00007013;
#50;
instr=32'h00001013;
#50;
instr=32'h00005013;
#50;
instr=32'h40005013;
#50;
instr=32'h00002013;
#50;
instr=32'h00003013;
#50;
instr=32'h00000003;
#50;
instr=32'h00001003;
#50;
instr=32'h00002003;
#50;
instr=32'h00004003;
#50 ;
instr=32'h00005003;
#50;
instr=32'h00000023;
#50;
instr=32'h00001023;
#50;
instr=32'h00002023;
#50;
instr=32'h00000063;
#50;
instr=32'h00001063;
#50;
instr=32'h00004063;
#50;
instr=32'h00005063;
#50;
instr=32'h00006063;
#50;
instr=32'h00007063;
#50;
instr=32'h0000006f;
#50;
instr=32'h00000067;
#50;
instr=32'h00000037;
#50;
instr=32'h00000017;
#50;
instr=32'h00000073;
#50;
instr=32'h00100073;
#50;
instr=32'h02000033;
#50;
instr=32'h02001033;
#50;
instr=32'h02002033;
#50;
instr=32'h02003033;
#50;
instr=32'h02004033;
#50;
instr=32'h02005033;
#50;
instr=32'h02006033;




end





endmodule
