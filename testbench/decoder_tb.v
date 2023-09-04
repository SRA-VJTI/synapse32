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
wire [4:0] rs2;
wire [4:0] rs1;
wire [31:0] imm;
wire [4:0] rd;
wire [2:0] func3;
wire rd_valid;
wire rs1_valid;
wire rs2_valid;
wire imm_valid;
wire [6:2] opcode;
wire [7:0] func7;
wire func3_valid;
wire func7_valid;
wire [9:0] out_signal;


decoder decoder1(.instr(instr),.rs2(rs2),.rs1(rs1),.imm(imm),.rd(rd),.func3(func3),
                 .rd_valid(rd_valid), .rs1_valid(rs1_valid),.imm_valid(imm_valid),
                 .opcode(opcode),.func7(func7), .func3_valid(func3_valid),.func7_valid(func7_valid),.out_signal(out_signal));
                 
initial clk=0;

always #10 clk = ~clk;

initial begin

instr=32'h0;
#100;
instr=32'h0713;
#100;
instr=32'ha00613;
#100;
instr= 32'h80100693;
#100;
instr=32'h0e68733;
#100;
instr=32'h0168693;
#100;
instr=32'hFEC6CCE3;
#100;
instr=32'hFD470F13;
#100;
instr=32'h5063;




end





endmodule
