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
input [4:0] rs1,
input [4:0] rs2,
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
    /*assign ALUoutput = (instructions[0] == 1 & ALUenabled ) ? 32'b0:(rs1 + rs2);             //add
    assign ALUoutput = (instructions[1] == 1 & ALUenabled ) ? (rs1 - rs2): 32'b0 ;           //sub
    assign ALUoutput = (instructions[2] == 1 & ALUenabled ) ? (rs1 ^ rs2): 32'b0 ;           //xor
    assign ALUoutput = (instructions[3] == 1 & ALUenabled ) ? (rs1 | rs2): 32'b0 ;           //or
    assign ALUoutput = (instructions[4] == 1 & ALUenabled ) ? (rs1 & rs2): 32'b0 ;           //and
    assign ALUoutput = (instructions[5] == 1 & ALUenabled ) ? (rs1 << rs2): 32'b0 ;          //sll
    assign ALUoutput = (instructions[6] == 1 & ALUenabled ) ? (rs1 >> rs2): 32'b0 ;          //srl
    assign ALUoutput = (instructions[7] == 1 & ALUenabled ) ? (rs1 > rs2): 32'b0 ;           //sra
    assign ALUoutput = (instructions[8] == 1 & ALUenabled ) ? ((rs1 < rs2)?1:0): 32'b0 ;     //slt
    assign ALUoutput = (instructions[9] == 1 & ALUenabled ) ? ((rs1 < rs2)?1:0): 32'b0 ;     //sltu         //doubt
    assign ALUoutput = (instructions[10] == 1 & ALUenabled ) ? (rs1 + imm): 32'b0 ;          //addi
    assign ALUoutput = (instructions[11] == 1 & ALUenabled ) ? (rs1 ^ imm): 32'b0 ;          //xori
    assign ALUoutput = (instructions[12] == 1 & ALUenabled ) ? (rs1 | imm): 32'b0 ;          //ori
    assign ALUoutput = (instructions[13] == 1 & ALUenabled ) ? (rs1 & imm): 32'b0 ;          //andi
    assign ALUoutput = (instructions[14] == 1 & ALUenabled ) ? (rs1 << imm[4:0]): 32'b0 ;    //slli
    assign ALUoutput = (instructions[15] == 1 & ALUenabled ) ? (rs1 >> imm[4:0]): 32'b0 ;    //srli
    assign ALUoutput = (instructions[16] == 1 & ALUenabled ) ? (rs1 > imm[4:0]): 32'b0 ;     //srai
    assign ALUoutput = (instructions[17] == 1 & ALUenabled ) ? ((rs1 < imm) ? 1:0): 32'b0 ;  //slti
    assign ALUoutput = (instructions[18] == 1 & ALUenabled ) ? ((rs1 < imm)?1:0): 32'b0 ;    //sltiu        //doubt
    assign ALUoutput = (instructions[33] == 1 & ALUenabled ) ? (PC + 4): 32'b0 ;             //jal          //doubt
    assign ALUoutput = (instructions[34] == 1 & ALUenabled ) ? (PC + 4): 32'b0 ;             //jalr         //doubt
    assign ALUoutput = (instructions[35] == 1 & ALUenabled ) ? (imm << 12): 32'b0 ;          //lui 
    assign ALUoutput = (instructions[36] == 1 & ALUenabled ) ? (PC + (imm << 12)): 32'b0 ;   //auipc*/
    if (ALUenabled & instructions[0])begin                                                 //add
      ALUoutput <= rs1 + rs2;
    end
    if (ALUenabled & instructions[1])begin                                                 //sub
      ALUoutput <= rs1 - rs2;
    end
    if (ALUenabled & instructions[2])begin                                                 //xor
      ALUoutput <= rs1 ^ rs2;
    end
    if (ALUenabled & instructions[3])begin                                                 //or
      ALUoutput <= rs1 | rs2;
    end
    if (ALUenabled & instructions[4])begin                                                 //and
      ALUoutput <= rs1 & rs2;
    end
    if (ALUenabled & instructions[5])begin                                                 //sll
      ALUoutput <= (rs1 << rs2);
    end
    if (ALUenabled & instructions[6])begin                                                 //srl
      ALUoutput <= (rs1 >> rs2);
    end    
    if (ALUenabled & instructions[7])begin                                                 //sra
      ALUoutput <= (rs1 > rs2);
    end
    if (ALUenabled & instructions[8])begin                                                 //slt
      ALUoutput <= (rs1 < rs2)?1:0;
    end 
    if (ALUenabled & instructions[9])begin                                                 //sltu   //doubt
      ALUoutput <= (rs1 < rs2)?1:0;
    end
    if (ALUenabled & instructions[10])begin                                                 //addi
      ALUoutput <= (rs1 + imm);
    end
    if (ALUenabled & instructions[11])begin                                                 //xori
      ALUoutput <= (rs1 ^ imm);
    end        
    if (ALUenabled & instructions[12])begin                                                 //ori
      ALUoutput <= (rs1 | imm);
    end
    if (ALUenabled & instructions[13])begin                                                 //andi
      ALUoutput <= (rs1 & imm);
    end 
    if (ALUenabled & instructions[14])begin                                                 //slli
      ALUoutput <= rs1 << imm[4:0];
    end   
    if (ALUenabled & instructions[15])begin                                                 //srli
      ALUoutput <= rs1 >> imm[4:0];
    end
    if (ALUenabled & instructions[16])begin                                                 //srai
      ALUoutput <= rs1 > imm[4:0];
    end
    if (ALUenabled & instructions[17])begin                                                 //slti
      ALUoutput <= (rs1 < imm) ? 1:0;
    end
    if (ALUenabled & instructions[18])begin                                                 //sltiu       //doubt
      ALUoutput <= (rs1 < imm) ? 1:0;
    end
    if (ALUenabled & instructions[19]) begin                                                 //lb
      rd_en <= 1;
      addr <= rs1 + imm;
      ALUoutput <= dmem_rd_data[7:0];
    end
    if (ALUenabled & instructions[20]) begin                                                 //lh
      rd_en <= 1;
      addr <= rs1 + imm;
      ALUoutput <= dmem_rd_data[15:0];
    end
    if (ALUenabled & instructions[21]) begin                                                 //lw
      rd_en <= 1;
      addr <= rs1 + imm;
      ALUoutput <= dmem_rd_data[31:0];
    end
    if (ALUenabled & instructions[22]) begin                                                 //lbu         //doubt
      rd_en <= 1;
      addr <= rs1 + imm;
      ALUoutput <= dmem_rd_data[7:0];
    end
    if (ALUenabled & instructions[23]) begin                                                //lhu          //doubt
      rd_en <= 1;
      addr <= rs1 + imm;
      ALUoutput <= dmem_rd_data[7:0];
    end
    if (ALUenabled & instructions[24]) begin                                                //sb
      wr_en <= 1;
      addr <= rs1 + imm;
      dmem_wr_data[7:0] <= rs2[7:0] ;
    end
    if (ALUenabled & instructions[25]) begin                                                //sh
      wr_en <= 1;
      addr <= rs1 + imm;
      dmem_wr_data[15:0] <= rs2[15:0] ;
    end
    if (ALUenabled & instructions[26]) begin                                                 //sw
      wr_en <= 1;
      addr <= rs1 + imm;
      dmem_wr_data[31:0] <= rs2[31:0] ;
    end
end       
endmodule
