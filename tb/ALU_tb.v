`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 06.09.2023 01:18:37
// Design Name: 
// Module Name: ALU_tb
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
module ALU_tb;
    reg clk;
    reg [31:0] rs1;
    reg [31:0] rs2;
    reg [15:0] instructions; //subjected to change
    wire [63:0] ALUoutput; 

    alu ALU1( .in1(rs1), .in2(rs2), .instructions(instructions), .ALUoutput(ALUoutput));
    
    initial rs1 = 32'd5;
    initial rs2 = 32'd4;
    initial instructions = 16'd0;
    always #10 clk = ~clk;
    initial begin
        #50 
        instructions <= 16'd1;
        #50
        instructions <= 16'd2;
        #50
        instructions <= 16'd4;
        #50
        instructions <= 16'd8;
        #50
        instructions <= 16'd16;
        #50
        instructions <= 16'd32;
        #50
        instructions <= 16'd64;
        #50
        instructions <= 16'd128;
        #50
        instructions <= 16'd256;
        #50
        instructions <= 16'd512;
        #50
        instructions <= 16'd1024;
        #50
        instructions <= 16'd2048;
        #50
        instructions <= 16'd4096;
    end
    
endmodule