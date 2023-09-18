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
input [46:0] instructions, //subjected to change
output reg [31:0] ALUoutput,
output reg signed [32:0] ALUoutput_s
    );

always@(instructions) begin
    
        case(instructions)
            46'h1 : ALUoutput = rs1 + rs2;                                        //add
            46'h2 : ALUoutput <= rs1 - rs2;                                       //sub
            46'h4 : ALUoutput <= rs1 ^ rs2;                                       //xor
            46'h8 : ALUoutput <= rs1 | rs2;                                       //or
            46'h10 : ALUoutput <= rs1 & rs2;                                      //and
            46'h20 : ALUoutput <= rs1 << rs2;                                     //sll
            46'h40 : ALUoutput <= rs1 >> rs2;                                     //srl
            46'h80 : ALUoutput <= rs1 > rs2;                                      //sra 
            46'h100 : ALUoutput_s <= (rs1 > rs2)?1:0;                             //slt
            46'h200 : ALUoutput <= (rs1 > rs2)?1:0;                               //sltu
            46'h400 : ALUoutput <= (rs1 + imm);                                   //addi
            46'h800 : ALUoutput <= (rs1 ^ imm);                                   //xori
            46'h1000 : ALUoutput <= (rs1 | imm);                                  //ori
            46'h2000 : ALUoutput <= (rs1 & imm);                                  //andi
            46'h4000 : ALUoutput <= (rs1 << imm[4:0]);                            //slli
            46'h8000 : ALUoutput <= (rs1 >> imm[4:0]);                            //srli
            46'h10000 : ALUoutput <= (rs1 > imm[4:0]);                            //srai
            46'h20000 : ALUoutput_s <= (rs1 < imm)?1:0;                           //slti
            46'h40000 : ALUoutput <= (rs1 < imm)?1:0;                             //sltiu
            46'h10000000000 : ALUoutput_s <= rs1 * rs2;                           //mul
            46'h20000000000 : ALUoutput_s <= {rs1 * rs2} >> 32;                   //mulh
            46'h40000000000 :ALUoutput <= { rs1 * rs2} >> 32;                     //mulhu
            46'h80000000000 : ALUoutput <= {rs1 * rs2} >> 32;                     //mulhsu
            46'h100000000000 : ALUoutput_s <= rs1 / rs2;                          //div
            46'h200000000000 : ALUoutput <= rs1 / rs2;                            //divu
            46'h400000000000 : ALUoutput_s <= rs1 % rs2;                          //rem
            46'h800000000000 : ALUoutput <= rs1 % rs2;                            //remu
               
        endcase
end       
endmodule
