`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 30.08.2023 16:36:26
// Design Name: 
// Module Name: imem
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

module risc_v_tb;
reg clk;
reg rst;
reg imem_wr_en;
reg [31:0] imem_data_in;
wire [2:0]funct3;
wire [6:0]funct7;
wire rd_valid;
wire imm_valid;
wire func3_valid;
wire func7_valid;
wire [31:0] final_output;
wire [6:0] s1;
wire [6:0] s2;
wire [6:0] s3;
wire [6:0] s4;
wire [6:0] s5;
wire [6:0] s6;
wire [6:0] s7;
wire [6:0] s8;

risc_v risc_v_1(.clk(clk),.rst(rst),.imem_wr_en(imem_wr_en),.funct3(funct3),.funct7(funct7),.rd_valid(rd_valid),.imm_valid(imm_valid),.func3_valid(func3_valid),
					.func7_valid(func7_valid), .final_output(final_output),.s1(s1),.s2(s2),.s3(s3),.s4(s4),.s5(s5),.s6(s6),.s7(s7),.s8(s8));
					
initial clk = 0;
initial rst = 0;
always #10 clk = ~clk;
initial imem_wr_en = 0;
initial imem_data_in=0;


						
						





endmodule 