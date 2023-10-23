module seven_seg(
input clk,
input [31:0]bcd,
input [6:0]opcode,
output [6:0]s1,
output [6:0]s2,
output [6:0]s3,
output [6:0]s4,
output [6:0]s5,
output [6:0]s6,
output [6:0]s7,
output [6:0]s8
);

function [6:0] seg7 (
input [3:0] bcd

);
	begin
		if (opcode!= 7'b1101111 || opcode!= 7'b1100111 || opcode!= 7'b0110111 || opcode != 7'b0010111) //jal, jalr, lui, auipc
			begin 
				case(bcd)
					4'b0000 : seg7 = 7'h7E; //0
					4'b0001 : seg7 = 7'h30; //1
					4'b0010 : seg7 = 7'h6D; //2
					4'b0011 : seg7 = 7'h79; //3
					4'b0100 : seg7 = 7'h33; //4         
					4'b0101 : seg7 = 7'h5B;	//5
					4'b0110 : seg7 = 7'h5F;	//6
					4'b0111 : seg7 = 7'h70;	//7
					4'b1000 : seg7 = 7'h7F;	//8
					4'b1001 : seg7 = 7'h7B;	//9
					4'b1010 : seg7 = 7'h77;	//a
					4'b1011 : seg7 = 7'h1F; //b
					4'b1100 : seg7 = 7'h4E;	//c
					4'b1101 : seg7 = 7'h3D;	//d
					4'b1110 : seg7 = 7'h4F;	//e
					4'b1111 : seg7 = 7'h47;	//f
				endcase 
			end 
		end
endfunction  


 assign s1 = seg7(bcd[3:0]);
 assign s2 = seg7(bcd[7:4]);
 assign s3 = seg7(bcd[11:8]);
 assign s4 = seg7(bcd[15:12]);
 assign s5 = seg7(bcd[19:16]);
 assign s6 = seg7(bcd[23:20]);
 assign s7 = seg7(bcd[27:24]);
 assign s8 = seg7(bcd[31:28]);

endmodule 