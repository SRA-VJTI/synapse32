`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06.09.2023 21:22:42
// Design Name: 
// Module Name: dmem
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


module dmem(
input clk,
input [31:0] addr,
input rd_en,
input wr_en,
input [31:0] in_data,
output [31:0] out_data

    );

reg [31:0] data_memory [31:0];

initial begin
for(integer i = 0;i<32;i=i+1)
        data_memory[i] = 32'b0;
    

 end

assign out_data= ((rd_en==1) && (wr_en==0))? data_memory[addr[4:0]] : 0;

always @(posedge clk) begin
 if ((wr_en==1) && (rd_en==0))
    data_memory[addr[4:0]] <= in_data;
    end
    


endmodule
