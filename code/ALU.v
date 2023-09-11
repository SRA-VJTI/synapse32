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
input [31:0] dmem_rd_data,
input [38:0] instructions, //subjected to change
input ALUenabled,
output reg [14:0] addr,
output reg rd_en,
output reg wr_en,
output reg [31:0] dmem_wr_data,
output reg [31:0] ALUoutput
    );

always@(posedge clk) begin
    assign rd_en = 2'b0;
  	assign wr_en = 2'b0;
    
    if (ALUenabled) begin
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
            39'h80000 : begin                                                     //lb
                            rd_en <= 1;
                            addr <= rs1 + imm;
                            ALUoutput <= dmem_rd_data[7:0];
                        end
            39'h100000 : begin                                                    //lh
                            rd_en <= 1;
                            addr <= rs1 + imm;
                            ALUoutput <= dmem_rd_data[15:0];
                        end
            39'h200000 : begin                                                    //lw
                            rd_en <= 1;
                            addr <= rs1 + imm;
                            ALUoutput <= dmem_rd_data[31:0];
                        end
            39'h400000 : begin                                                    //lbu
                            rd_en <= 1;
                            addr <= rs1 + imm;
                            ALUoutput <= dmem_rd_data[7:0];
                        end 
            39'h800000 : begin                                                    //lhu
                            rd_en <= 1;
                            addr <= rs1 + imm;
                            ALUoutput <= dmem_rd_data[15:0];
                        end 
            39'h1000000 : begin                                                   //sb
                            wr_en <= 1;
                            addr <= rs1 + imm;
                            dmem_wr_data[7:0] <= rs2[7:0] ;
                        end
            39'h2000000 : begin                                                   //sh
                            wr_en <= 1;
                            addr <= rs1 + imm;
                            dmem_wr_data[7:0] <= rs2[15:0] ;
                        end 
            39'h4000000 : begin                                                   //sw
                            wr_en <= 1;
                            addr <= rs1 + imm;
                            dmem_wr_data[7:0] <= rs2[31:0] ;
                        end
            39'h100000000 : ALUoutput <= (PC + 1);                                           //jal
            39'h200000000 : ALUoutput <= (PC + 1) ;                                           //jalr
            39'h400000000 : ALUoutput <= (imm << 12);                                         //lui
            39'h800000000 : ALUoutput <= (PC + (imm << 12));                                  //auipc
            default : ALUoutput <= 32'b0 ;
        endcase
    end
end       
endmodule
