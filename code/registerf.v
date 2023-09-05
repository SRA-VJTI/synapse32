`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 05.09.2023 11:10:53
// Design Name: 
// Module Name: registerf
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



module registerf(
input clk,
 input [31:0]rs1,
 input [31:0]rs2,
 input rs1_valid,
 input rs2_valid,
 input [31:0]rd,
 input wr_en,
 input [31:0]result,
 output [31:0]src1_value,
 output [31:0]src2_value

 );
    
 reg [31:0] register_file [31:0];

 assign src1_value = rs1_valid? register_file[rs1[4:0]]:0;
 assign src2_value = rs2_valid ? register_file[rs2[4:0]]:0;


always @(posedge clk) begin 
 if (wr_en) begin
    register_file[rd[4:0]]<=result;
   end
 end
 
 
endmodule
