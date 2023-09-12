`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 04.09.2023 12:40:30
// Design Name: 
// Module Name: ALU
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


module ALU(
input clk,
input [31:0] rs1,
input [31:0] rs2,
input [11:0] imm,
input [31:0] PC,
input [38:0] instructions, //subjected to change
output reg [31:0] ALUoutput
    );

always@(instructions) begin
    
        case(instructions)
            39'h1 : ALUoutput = rs1 + rs2;                                       //add
            39'h2 : ALUoutput <= rs1 - rs2;                                       //sub
            39'h4 : ALUoutput <= rs1 ^ rs2;                                       //xor
            39'h8 : ALUoutput <= rs1 | rs2;                                       //or
            39'h10 : ALUoutput <= rs1 & rs2;                                      //and
            39'h20 : ALUoutput <= rs1 << rs2;                                     //sll
            39'h40 : ALUoutput <= rs1 >> rs2;                                     //srl
            39'h80 : ALUoutput <= rs1 > rs2;                                      //sra 
            39'h100 : ALUoutput <= (rs1 > rs2)?1:0;                               //slt
            39'h200 : ALUoutput <= (rs1 > rs2)?1:0;                               //sltu
            39'h400 : ALUoutput <= (rs1 + imm);                                   //addi
            39'h800 : ALUoutput <= (rs1 ^ imm);                                   //xori
            39'h1000 : ALUoutput <= (rs1 | imm);                                  //ori
            39'h2000 : ALUoutput <= (rs1 & imm);                                  //andi
            39'h4000 : ALUoutput <= (rs1 << imm[4:0]);                            //slli
            39'h8000 : ALUoutput <= (rs1 >> imm[4:0]);                            //srli
            39'h10000 : ALUoutput <= (rs1 > imm[4:0]);                            //srai
            39'h20000 : ALUoutput <= (rs1 < imm)?1:0;                             //slti
            39'h40000 : ALUoutput <= (rs1 < imm)?1:0;                             //sltiu
        endcase
end       
endmodule
