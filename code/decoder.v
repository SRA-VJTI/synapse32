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
   input  [31:0] instr,
   output reg [4:0] rs2,
   output reg [4:0] rs1,
   output [31:0] imm,
   output reg [4:0] rd,
   output reg [2:0] func3,
   output reg [6:0] func7,
   output rd_valid,
   output rs1_valid,
   output rs2_valid,
   output imm_valid,
   output func3_valid,
   output func7_valid,
   output reg [6:0] opcode,
  output [9:0] out_signal
   
    );

 reg is_r_instr, is_u_instr, is_s_instr, is_b_instr, is_j_instr, is_i_instr;
 
always @(instr) begin 

    opcode<=instr[6:0];
    is_i_instr<=(instr[6:0]== 7'b0000x11)||(instr[6:0]== 7'b001x011)||(instr[6:0]== 7'b1100111);
    is_u_instr<=(instr[6:0]==7'b0x10111);
    is_b_instr<=(instr[6:0]==7'b1101111);
    is_j_instr<=(instr[6:0]==7'b1101111);
    is_s_instr<=(instr[6:0]==7'b0100x11);
    is_r_instr<=(instr[6:0]==7'b011x011)||(instr[6:0]==7'b0100111)||(instr[6:0]==7'b1010011);
    rs2[4:0]<=instr[24:20];
    rs1[4:0]<=instr[19:15];
    rd[4:0]<=instr[11:7];
    func3[2:0]<=instr[14:12];
    func7<=instr[31:25];
end
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
  
  
  
  
  
   
   
   

endmodule
