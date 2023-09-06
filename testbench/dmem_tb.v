`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06.09.2023 21:23:00
// Design Name: 
// Module Name: dmem_tb
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


module dmem_tb;
reg clk;
reg [31:0] read;
reg [31:0] write;
reg rd_en;
reg wr_en;
reg [31:0] in_data;
wire [31:0] out_data;

dmem dmem1(.clk(clk),.read(read),.write(write),.rd_en(rd_en),.in_data(in_data),.out_data(out_data));

initial clk = 0;
always #10 clk=~clk;

initial begin

rd_en = 0;
wr_en = 1;
read = 32'd1;
write = 32'd2;
in_data=32'd3;
#100;

rd_en = 1;
wr_en = 1;
read = 32'd1;
write = 32'd2;
in_data=32'd2;
#100;

rd_en = 1;
wr_en = 0;
read = 32'd1;
write = 32'd1;
in_data=32'd4;
#100;
end

endmodule
