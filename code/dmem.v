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
        data_memory[0] = 32'b0;
		  data_memory[1] = 32'b0;
		  data_memory[2] = 32'b0;
		  data_memory[3] = 32'b0;
		  data_memory[4] = 32'b0;
		  data_memory[5] = 32'b0;
		  data_memory[6] = 32'b0;
		  data_memory[7] = 32'b0;
		  data_memory[8] = 32'b0;
		  data_memory[9] = 32'b0;
		  data_memory[10] = 32'b0;
		  data_memory[11] = 32'b0;
		  data_memory[12] = 32'b0;
		  data_memory[13] = 32'b0;
		  data_memory[14] = 32'b0;
		  data_memory[15] = 32'b0;
		  data_memory[16] = 32'b0;
		  data_memory[17] = 32'b0;
		  data_memory[18] = 32'b0;
		  data_memory[19] = 32'b0;
		  data_memory[20] = 32'b0;
		  data_memory[21] = 32'b0;
		  data_memory[22] = 32'b0;
		  data_memory[23] = 32'b0;
		  data_memory[24] = 32'b0;
		  data_memory[25] = 32'b0;
		  data_memory[26] = 32'b0;
		  data_memory[27] = 32'b0;
		  data_memory[28] = 32'b0;
		  data_memory[29] = 32'b0;
		  data_memory[30] = 32'b0;
		  data_memory[31] = 32'b0;
		  
    

 end

assign out_data= ((rd_en==1) && (wr_en==0))? data_memory[addr[4:0]] : 0;

always @(posedge clk) begin
 if ((wr_en==1) && (rd_en==0))
    data_memory[addr[4:0]] <= in_data;
    end
    


endmodule
