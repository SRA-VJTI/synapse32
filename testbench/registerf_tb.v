`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 05.09.2023 11:11:23
// Design Name: 
// Module Name: registerf_tb
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


module registerf_tb;

reg clk;
reg [31:0] rs1;
reg [31:0] rs2;
reg rs1_valid;
reg rs2_valid;
reg [31:0] rd;
reg wr_en;
reg [31:0] result;
wire [31:0]src1_value;
wire [31:0]src2_value;

registerf registerf1(.clk(clk),.rs1(rs1),.rs2(rs2),.rs1_valid(rs1_valid),.rs2_valid(rs2_valid),
                     .rd(rd),.wr_en(wr_en),.result(result),.src1_value(src1_value),.src2_value(src2_value));
                     
 initial clk = 0;
 always #10 clk =~clk;
  
 initial begin
 
 rs1_valid = 32'd0; 
 rs2_valid = 32'd0; 
 wr_en = 32'd1;
 rd = 32'd1;
 result = 32'd3;
 rs1 = 32'd1;
 rs2 = 32'd2;
  #100;
  
  rs1_valid = 32'd0; 
 rs2_valid = 32'd0; 
 wr_en = 32'd1;
 rd = 32'd2;
 result = 32'd3;
 #100
 
 rs1_valid = 32'd1; 
 rs2_valid = 32'd1; 
 wr_en = 32'd1;
 rd = 32'd3;
 result = 32'd3;
 rs1 = 32'd1;
 rs2 = 32'd2;
 #100
 
 rs1_valid = 32'd1; 
 rs2_valid = 32'd1; 
 wr_en = 32'd0;
 rs1 = 32'd1;
 rs2 = 32'd2;
   
 end  
   
   
   
   
endmodule
