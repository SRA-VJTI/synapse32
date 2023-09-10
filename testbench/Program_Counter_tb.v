`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 02.09.2023 11:11:03
// Design Name: 
// Module Name: Program_Counter_tb
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


module PC_tb;
reg clk ;
reg reset ;
reg j_signal ;
reg [31:0] jump ;
wire [31:0] out ;

PC pc1(.clk(clk), .reset(reset), .j_signal(j_signal), .jump(jump), .out(out));

initial clk = 0;
initial reset = 0;
always begin
  #10;
  clk = ~clk;
end

initial begin
j_signal = 0;
jump = 0;
#60;reset = 2'b1;#20;reset = 2'b0;
#40;j_signal = 2'b1;jump = 32'b1;#20;jump = 32'b0;
j_signal = 2'b0;jump = 32'b101;

end
endmodule