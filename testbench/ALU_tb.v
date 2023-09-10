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
    reg [4:0] rs1;
    reg [4:0] rs2;
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
    initial ALUenabled = 32'b1;
    always #10 clk = ~clk;
    initial begin
        #50 
        instructions[0] <= 1;
        #50 
        instructions[1] <= 1;
        #50 
        instructions[2] <= 1;
        #50 
        instructions[3] <= 1;
        #50 
        instructions[4] <= 1;
        #50 
        instructions[5] <= 1;
        #50 
        instructions[6] <= 1;
        #50 
        instructions[7] <= 1;
        #50 
        instructions[8] <= 1;
        #50 
        instructions[9] <= 1;
        #50 
        instructions[10] <= 1;
        #50 
        instructions[11] <= 1;
        #50 
        instructions[12] <= 1;
        #50 
        instructions[13] <= 1;
        #50 
        instructions[14] <= 1;
        #50 
        instructions[15] <= 1;
        #50 
        instructions[16] <= 1;
        #50 
        instructions[17] <= 1;
        #50 
        instructions[18] <= 1;
        #50 
        instructions[33] <= 1;
        #50 
        instructions[34] <= 1;
        #50 
        instructions[35] <= 1;
        #50 
        instructions[36] <= 1;
        
    
    end
    


endmodule