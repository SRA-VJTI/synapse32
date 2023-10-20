`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 01.09.2023 09:07:00
// Design Name: 
// Module Name: decoder
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


module decoder(
input clk,
   input [31:0] instr,
   output  [31:0] rs2,
   output  [31:0] rs1,
   output [31:0] imm,
   output  [31:0] rd,
   output  [2:0] func3,
   output  [6:0] func7,
   output rd_valid,
   output rs1_valid,
   output rs2_valid,
   output imm_valid,
   output func3_valid,
   output func7_valid,
   output [6:0] opcode,
  output [46:0] out_signal
   
    );

wire  is_r_instr, is_u_instr, is_s_instr, is_b_instr, is_j_instr, is_i_instr;
 


    assign opcode=instr[6:0];
    assign is_i_instr=(instr[6:0]== 7'b0000011)||(instr[6:0]== 7'b0010011)||(instr[6:0]== 7'b1100111);
    assign is_u_instr=(instr[6:0]==7'b0010111);
    assign is_b_instr=(instr[6:0]==7'b1101111);
    assign is_j_instr=(instr[6:0]==7'b1101111);
    assign is_s_instr=(instr[6:0]==7'b0100011);
    assign is_r_instr=(instr[6:0]==7'b0110011)||(instr[6:0]==7'b0100111)||(instr[6:0]==7'b1010011);
    assign rs2=instr[24:20];
    assign rs1=instr[19:15];
    assign rd=instr[11:7];
    assign func3=instr[14:12];
    assign func7=instr[31:25];

   assign func7_valid= is_r_instr;
   assign rs1_valid=is_r_instr || is_i_instr || is_s_instr || is_b_instr;
   assign rs2_valid= is_r_instr || is_s_instr || is_b_instr; 
   assign rd_valid= is_r_instr || is_i_instr || is_u_instr || is_j_instr;
   assign func3_valid=is_r_instr || is_i_instr || is_s_instr || is_b_instr;
   
   
   assign imm = is_i_instr ? {  {21{instr[31]}},  instr[30:20]  } :
                is_s_instr ? {  {21{instr[31]}},  instr[30:25],  instr[11:7]  } :
                is_b_instr ? {  {20{instr[31]}},  instr[7], instr[30:25], instr[11:8]  } :
                is_u_instr ? {  instr[31:12]  } :
                is_j_instr ? {  {12{instr[31]}},  instr[19:12], instr[20], instr[30:25], instr[24:21]  } : 32'b0;
                
   assign imm_valid = is_i_instr || is_s_instr || is_b_instr || is_u_instr || is_j_instr;
   
   // I instructions
  assign out_signal[0]=(is_r_instr&&(func3==3'h0)&&(func7==7'h00))? 1'b1 : 1'b0; //add
  assign out_signal[1]=(is_r_instr&&(func3==3'h0)&&(func7==7'h20))? 1'b1 : 1'b0; //sub
  assign out_signal[2]=(is_r_instr&&(func3==3'h4)&&(func7==7'h00))? 1'b1 : 1'b0; //xor
  assign out_signal[3]=(is_r_instr&&(func3==3'h6)&&(func7==7'h0))? 1'b1 : 1'b0; //or
  assign out_signal[4]=(is_r_instr&&(func3==3'h7)&&(func7==7'h0))? 1'b1 : 1'b0; //and
  assign out_signal[5]=(is_r_instr&&(func3==3'h1)&&(func7==7'h0))? 1'b1 : 1'b0; //sll
  assign out_signal[6]=(is_r_instr&&(func3==3'h5)&&(func7==7'h0))? 1'b1 : 1'b0; //slr
  assign out_signal[7]=(is_r_instr&&(func3==3'h5)&&(func7==7'h20))? 1'b1 : 1'b0; //sra
  assign out_signal[8]=(is_r_instr&&(func3==3'h2)&&(func7==7'h0))? 1'b1 : 1'b0; //slt
  assign out_signal[9]=(is_r_instr&&(func3==3'h3)&&(func7==7'h0))? 1'b1 : 1'b0; //sltu
  
  assign out_signal[10]=(is_i_instr&&(func3==3'h0)&&(func7==7'h0))? 1'b1: 1'b0; //addi
  assign out_signal[11]=(is_i_instr&&(func3==3'h4)) ? 1'b1: 1'b0; //xori
  assign out_signal[12]=(is_i_instr&&(func3==3'h6))? 1'b1: 1'b0; //ori
  assign out_signal[13]=(is_i_instr&&(func3==3'h7))? 1'b1: 1'b0; //andi
  assign out_signal[14]=(is_i_instr&&(func3==3'h1)&&(imm[11:5]==7'h0))? 1'b1: 1'b0;//slli
  assign out_signal[15]=(is_i_instr&&(func3==3'h5)&&(imm[11:5]==7'h0))? 1'b1: 1'b0; //srli
  assign out_signal[16]=(is_i_instr&&(func3==3'h5)&&(imm[11:5]==7'h20))? 1'b1: 1'b0; //srai
  assign out_signal[17]=(is_i_instr&&(func3==3'h2))? 1'b1:1'b0; //slti
  assign out_signal[18]=(is_i_instr&&(func3==3'h3))? 1'b1:1'b0; //sltiu
  
  assign out_signal[19]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h0))? 1'b1:1'b0; //lb
  assign out_signal[20]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h1))? 1'b1:1'b0; //lh
  assign out_signal[21]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h2))? 1'b1:1'b0; //lw
  assign out_signal[22]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h4))? 1'b1:1'b0; //lbu
  assign out_signal[23]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h5))? 1'b1:1'b0; //lhu
  
  assign out_signal[24]=(is_s_instr&&(func3==3'h0))? 1'b1 : 1'b0; //sb
  assign out_signal[25]=(is_s_instr&&(func3==3'h1))? 1'b1 : 1'b0; //sh
  assign out_signal[26]=(is_s_instr&&(func3==3'h0))? 1'b1 : 1'b0; //sw
  
  assign out_signal[27]=(is_b_instr&&(func3==3'h0))? 1'b1 : 1'b0; //beq
  assign out_signal[28]=(is_b_instr&&(func3==3'h1))? 1'b1 : 1'b0; //bne
  assign out_signal[29]=(is_b_instr&&(func3==3'h4))? 1'b1 : 1'b0; //blt
  assign out_signal[30]=(is_b_instr&&(func3==3'h5))? 1'b1 : 1'b0; //bge
  assign out_signal[31]=(is_b_instr&&(func3==3'h6))? 1'b1 : 1'b0; //bltu
  assign out_signal[32]=(is_b_instr&&(func3==3'h7))? 1'b1 : 1'b0; //bgeu
  
  assign out_signal[33]=(is_j_instr&&(opcode==7'b1101111))? 1'b1 : 1'b0; //jal
  assign out_signal[34]=(is_i_instr&&(opcode==7'b1101111)&&(func3==3'h0))? 1'b1 : 1'b0; //jalr
  
  assign out_signal[35]=(is_u_instr&&(opcode==7'b0110111))? 1'b1 : 1'b0; //lui
  assign out_signal[36]=(is_u_instr&&(opcode==7'b0010111))? 1'b1 : 1'b0; //auipc
  
  assign out_signal[37]=(is_i_instr&&(opcode==7'b1110011)&&(func3==3'h0)&&(imm==3'h0))? 1'b1 :1'b0; //ecall
  assign out_signal[38]=(is_i_instr&&(opcode==7'b1110011)&&(func3==3'h0)&&(imm==3'h1))? 1'b1 :1'b0; //ebreak
  
  
  //M instructions
  assign out_signal[39]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h0)&&(func7==7'h01))? 1'b1 :1'b0; //mul
  assign out_signal[40]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h1)&&(func7==7'h01))? 1'b1 :1'b0; //mulh
  assign out_signal[41]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h2)&&(func7==7'h01))? 1'b1 :1'b0; //mulhsu
  assign out_signal[42]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h3)&&(func7==7'h01))? 1'b1 :1'b0; //mulu
  assign out_signal[43]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h4)&&(func7==7'h01))? 1'b1 :1'b0; //div
  assign out_signal[44]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h5)&&(func7==7'h01))? 1'b1 :1'b0; //divu
  assign out_signal[45]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h6)&&(func7==7'h01))? 1'b1 :1'b0; //rem
  assign out_signal[46]=(is_r_instr&&(opcode==7'b0110011)&&(func3==3'h7)&&(func7==7'h01))? 1'b1 :1'b0; //remu   
   
   

endmodule
