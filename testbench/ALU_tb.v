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
module ALU_td;
    reg clk;
    reg [31:0] rs1;
    reg [31:0] rs2;
    reg [11:0] imm;
    reg [31:0] PC;
    reg [31:0] dmem_rd_data;
    reg [38:0] instructions; //subjected to change
    reg ALUenabled;
    wire [14:0] addr;
    wire rd_en;
    wire wr_en;
    wire [31:0] dmem_wr_data;
    wire [31:0] ALUoutput;
    
    ALU ALU1( .clk(clk), .rs1(rs1), .rs2(rs2), .imm(imm), .PC(PC), .dmem_rd_data(dmem_rd_data), .instructions(instructions), .ALUenabled(ALUenabled), .addr(addr), .rd_en(rd_en), .wr_en(wr_en), .dmem_wr_data(dmem_wr_data), .ALUoutput(ALUoutput));
    
    initial clk = 0;
    initial rs1 = 5'd5;
    initial rs2 = 5'd4;
    initial imm = 12'd12;
    initial PC = 32'b10;
    initial instructions = 39'b0;
    initial dmem_rd_data = 32'b0;
    initial ALUenabled = 1;
    always #10 clk = ~clk;
    initial begin
        #50 
        instructions <= 39'h1;
        #50 
        instructions <= 39'h2;
        #50 
        instructions <= 39'h4;
        #50 
        instructions <= 39'h8;
        #50 
        instructions <= 39'h10;
        #50 
        instructions <= 39'h20;
        #50 
        instructions <= 39'h40;
        #50 
        instructions <= 39'h80;
        #50 
        instructions <= 39'h100;
        #50 
        instructions <= 39'h200;
        #50 
        instructions <= 39'h400;
        #50 
        instructions <= 39'h800;
        #50 
        instructions <= 39'h1000;
        #50 
        instructions <= 39'h2000;
        #50 
        instructions <= 39'h4000;
        #50 
        instructions <= 39'h8000;
        #50 
        instructions <= 39'h10000;
        #50 
        instructions <= 39'h20000;
        #50 
        instructions <= 39'h40000;
        #50 
        instructions <= 39'h100000000 ;
        #50 
        instructions <= 39'h200000000 ;
        #50 
        instructions <= 39'h400000000 ;
        #50 
        instructions <= 39'h800000000 ;
        
    
    end
    


endmodule