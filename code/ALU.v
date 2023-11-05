

module ALU(
input clk,
input [31:0] rs1,
input [31:0] rs2,
input [31:0] imm,
input ALUenabled,
input [46:0] instructions,

output reg [31:0] ALUoutput
);

	initial begin
		ALUoutput = 0;
	end	
	 
	always@(*) begin
		if (ALUenabled) begin
        case(instructions)
			  47'h1 : ALUoutput <= rs1 + rs2;                                       //add
           47'h2 : ALUoutput <= rs1 - rs2;                                       //sub
           47'h4 : ALUoutput <= rs1 ^ rs2;                                       //xor
           47'h8 : ALUoutput <= rs1 | rs2;                                       //or
           47'h10 : ALUoutput <= rs1 & rs2;                                      //and
           47'h20 : ALUoutput <= rs1 << rs2;                                     //sll
           47'h40 : ALUoutput <= rs1 >> rs2;                                     //srl
           47'h80 : ALUoutput <= rs1 > rs2;                                      //sra 
           47'h100 : ALUoutput <= (rs1 > rs2)?1:0;                             //slt
           47'h200 : ALUoutput <= (rs1 > rs2)?1:0;                               //sltu
           47'h400 : ALUoutput <= (rs1 + imm);                                   //addi
           47'h800 : ALUoutput <= (rs1 ^ imm);                                   //xori
           47'h1000 : ALUoutput <= (rs1 | imm);                                  //ori
           47'h2000 : ALUoutput <= (rs1 & imm);                                  //andi
           47'h4000 : ALUoutput <= (rs1 << imm[4:0]);                            //slli
           47'h8000 : ALUoutput <= (rs1 >> imm[4:0]);                            //srli
           47'h10000 : ALUoutput <= (rs1 > imm[4:0]);                            //srai
           47'h20000 : ALUoutput <= (rs1 < imm)?1:0;                             //slti
           47'h40000 : ALUoutput <= (rs1 < imm)?1:0;                             //sltiu 
           47'h10000000000 : ALUoutput <= rs1 * rs2;                              //mul 
			  47'h20000000000 : ALUoutput <= {rs1 * rs2} >> 32;                     //mulh
           47'h40000000000 :ALUoutput <= {{32'd0, rs1} * rs2} >> 32;             //mulhu
           47'h80000000000 : ALUoutput <= {rs1 * rs2} >> 32;                     //mulhsu
           47'h100000000000 : ALUoutput <= rs1 / rs2;                             //div
			  47'h200000000000 : ALUoutput <= rs1 / rs2;                            //divu
           47'h400000000000 : ALUoutput <= rs1 % rs2;                            //rem
           47'h800000000000 : ALUoutput <= rs1 % rs2;                            //remu
           default : ALUoutput<= 0;
        endcase
		end
	end       
endmodule
