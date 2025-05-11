
module alu(

input [31:0] rs1,
input [31:0] rs2,
input [31:0] imm,
input [36:0] instructions,
input [31:0] pc_input,
output reg [31:0] ALUoutput
);
wire [31:0] Simm;

	initial begin
		ALUoutput = 0;
	end	
	
	assign Simm={{imm[31:12],{20{imm[11]}}},imm};
	always@(*) begin
	
    case(instructions) 
		   37'h1 : ALUoutput <= rs1 + rs2;     	//add                                    //add
         37'h2 : ALUoutput <= rs1 - rs2;        //sub                          //sub
         37'h4 : ALUoutput <= rs1 ^ rs2;        //xor                               //xor
         37'h8 : ALUoutput <= rs1 | rs2;        //or                               //or
         37'h10 : ALUoutput <= rs1 & rs2;       //and                               //and
         37'h20 : ALUoutput <= rs1 << rs2[4:0]; //sll                               //sll
         37'h40 : ALUoutput <= rs1 >> rs2[4:0]; //srl                               //srl
         37'h80 : ALUoutput <= rs1 >>> rs2[4:0];  //sra                             //sra 
         37'h100 : ALUoutput <= (rs1 < rs2);    //slt                               //slt
         37'h200 : ALUoutput <= (rs1 < rs2);    //sltu                               //sltu
         37'h400 : ALUoutput <= (rs1 + Simm);   //addi                               //addi
         37'h800 : ALUoutput <= (rs1 ^ Simm);   // xori                              //xori
         37'h1000 : ALUoutput <= (rs1 | Simm);  //ori                               //ori
         37'h2000 : ALUoutput <= (rs1 & Simm);  //andi                               //andi
         37'h4000 : ALUoutput <= (rs1 << imm[4:0]);  //slli :)                          //slli
         37'h8000 : ALUoutput <= (rs1 >> imm[4:0]);  //srli :)                         //srli
         37'h10000 : ALUoutput <= (rs1 >>> imm[4:0]); //srai :)                       //srai
         37'h20000 : ALUoutput <= (rs1 < Simm);       //stli                         //slti
         37'h40000 : ALUoutput <= (rs1 < Simm);       //sltiu                         //sltiu 
			37'h800000000: ALUoutput<= imm<<12;  //lui
         37'h1000000000: ALUoutput <= pc_input + (imm<<12);  //auipc
         default : ALUoutput<= 0;
        
		
	endcase  
end	
endmodule 