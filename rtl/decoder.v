module decoder(
   
   input [31:0] instr,
   output  [4:0] rs2,
   output  [4:0] rs1,
   output [31:0] imm,
   output  [31:0] rd,
  
   output rs1_valid,
   output rs2_valid,

   output [6:0] opcode,
  output [36:0] out_signal
   
    );

wire  is_r_instr, is_u_instr, is_s_instr, is_b_instr, is_j_instr, is_i_instr;
wire [2:0]func3;
wire [6:0]func7;


    assign opcode=instr[6:0];
    assign is_i_instr=(instr[6:0]== 7'b0000011)||(instr[6:0]== 7'b0010011)||(instr[6:0]== 7'b1100111);
    assign is_u_instr=(instr[6:0]==7'b0010111)||(instr[6:0] == 7'b0110111);
    assign is_b_instr=(instr[6:0]==7'b1100011);
    assign is_j_instr=(instr[6:0]==7'b1101111);
    assign is_s_instr=(instr[6:0]==7'b0100011);
    assign is_r_instr=(instr[6:0]==7'b0110011)||(instr[6:0]==7'b0100111)||(instr[6:0]==7'b1010011);
    assign rs2= (is_r_instr || is_s_instr || is_b_instr) ? instr[24:20] :  0;
    assign rs1= (is_r_instr || is_s_instr || is_b_instr || is_i_instr) ? instr[19:15]: 0;
    assign rd= (is_r_instr || is_u_instr || is_j_instr || is_i_instr) ? instr[11:7] : 0;
    assign func3= (is_r_instr || is_s_instr || is_b_instr || is_i_instr) ? instr[14:12] : 0;
    assign func7= is_r_instr ? instr[31:25] : 0;

   
   assign rs1_valid=is_r_instr || is_i_instr || is_s_instr || is_b_instr;
   assign rs2_valid= is_r_instr || is_s_instr || is_b_instr; 
  
  
   
   
   assign imm = is_i_instr ? {  {21{instr[31]}},  instr[30:20]  } :
                is_s_instr ? {  {21{instr[31]}},  instr[30:25],  instr[11:7]  } :
                is_b_instr ? {  {19{1'b0}}, instr[31],  instr[7], instr[30:25], instr[11:8], 1'b0 } :
                is_u_instr ? {  instr[31:12]  } :
                is_j_instr ? {  {13{instr[31]}},  instr[19:12], instr[20], instr[30:25], instr[24:21], 1'b0  } : 32'b0;
                
   
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
  
  assign out_signal[10]=(is_i_instr&&(func3==3'h0)&&(func7==7'h0)&&(opcode == 7'b0010011))? 1'b1: 1'b0; //addi
  assign out_signal[11]=(is_i_instr&&(func3==3'h4)&&(opcode == 7'b0010011)) ? 1'b1: 1'b0; //xori
  assign out_signal[12]=(is_i_instr&&(func3==3'h6)&&(opcode == 7'b0010011))? 1'b1: 1'b0; //ori
  assign out_signal[13]=(is_i_instr&&(func3==3'h7)&&(opcode == 7'b0010011))? 1'b1: 1'b0; //andi
  assign out_signal[14]=(is_i_instr&&(func3==3'h1)&&(imm[11:5]==7'h0)&&(opcode == 7'b0010011))? 1'b1: 1'b0;//slli
  assign out_signal[15]=(is_i_instr&&(func3==3'h5)&&(imm[11:5]==7'h0)&&(opcode == 7'b0010011))? 1'b1: 1'b0; //srli
  assign out_signal[16]=(is_i_instr&&(func3==3'h5)&&(imm[11:5]==7'h20)&&(opcode == 7'b0010011))? 1'b1: 1'b0; //srai
  assign out_signal[17]=(is_i_instr&&(func3==3'h2)&&(opcode == 7'b0010011))? 1'b1:1'b0; //slti
  assign out_signal[18]=(is_i_instr&&(func3==3'h3)&&(opcode == 7'b0010011))? 1'b1:1'b0; //sltiu
  
  assign out_signal[19]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h0))? 1'b1:1'b0; //lb
  assign out_signal[20]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h1))? 1'b1:1'b0; //lh
  assign out_signal[21]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h2))? 1'b1:1'b0; //lw
  assign out_signal[22]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h4))? 1'b1:1'b0; //lbu
  assign out_signal[23]=(is_i_instr&&(opcode==7'b0000011)&&(func3==3'h5))? 1'b1:1'b0; //lhu
  
  assign out_signal[24]=(is_s_instr&&(func3==3'h0))? 1'b1 : 1'b0; //sb
  assign out_signal[25]=(is_s_instr&&(func3==3'h1))? 1'b1 : 1'b0; //sh
  assign out_signal[26]=(is_s_instr&&(func3==3'h2))? 1'b1 : 1'b0; //sw
  
  assign out_signal[27]=(is_b_instr&&(func3==3'h0))? 1'b1 : 1'b0; //beq
  assign out_signal[28]=(is_b_instr&&(func3==3'h1))? 1'b1 : 1'b0; //bne
  assign out_signal[29]=(is_b_instr&&(func3==3'h4))? 1'b1 : 1'b0; //blt
  assign out_signal[30]=(is_b_instr&&(func3==3'h5))? 1'b1 : 1'b0; //bge
  assign out_signal[31]=(is_b_instr&&(func3==3'h6))? 1'b1 : 1'b0; //bltu
  assign out_signal[32]=(is_b_instr&&(func3==3'h7))? 1'b1 : 1'b0; //bgeu
  
  assign out_signal[33]=(is_j_instr&&(opcode==7'b1101111))? 1'b1 : 1'b0; //jal
  assign out_signal[34]=((opcode==7'b1100111)&&(func3==3'h0))? 1'b1 : 1'b0; //jalr
  
  assign out_signal[35]=(opcode==7'b0110111)? 1'b1 : 1'b0; //lui
  assign out_signal[36]=(opcode==7'b0010111)? 1'b1 : 1'b0; //auipc


endmodule