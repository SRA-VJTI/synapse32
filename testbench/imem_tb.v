`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 30.08.2023 16:36:46
// Design Name: 
// Module Name: imem_tb
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


module imem_tb;

reg clk;

wire [31:0] data_out;
reg [4:0] addr;

imem imem1(.clk(clk), .data_out(data_out), .addr(addr));

initial clk=0;

always #10 clk = ~clk;
initial begin
addr=5'd0;
#100;
addr=5'd1;
#100;
addr=5'd2;
#100;
addr=5'd3;
#100;
addr=5'd4;
#100;
addr=5'd5;

end

    
    
endmodule
