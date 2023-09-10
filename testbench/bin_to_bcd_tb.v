`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 07.09.2023 12:04:23
// Design Name: 
// Module Name: bin_to_bcd_tb
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


module bin_to_bcd_tb;
reg clk;
reg [31:0] bin;
wire [31:0] bcd;

bin_to_bcd bin_to_bcd1(.clk(clk),.bin(bin),.bcd(bcd));

initial clk = 0;
always #10 clk = ~clk;
initial begin

bin=32'd4;
#100;
bin=32'd6;
#100;
bin=32'd5;
#100;
bin=32'd10;
#100;
bin=32'd12;
#100;
bin=32'd14;
#100;
bin=32'd485;


end
endmodule
