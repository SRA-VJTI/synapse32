`timescale 1ns / 1ps



module control_unit_tb;
reg clk;
reg rst;
reg [31:0] rs2_input;
reg [31:0] rs1_input;
reg [31:0] imm;
reg [31:0] mem_read;
reg [44:0] out_signal;
reg [6:0] opcode;
reg [31:0] pc_input;
reg [63:0] ALUoutput;
wire [15:0] instructions;                   
wire  [31:0] mem_write;
wire wr_en;
wire [31:0] addr;
wire j_signal;
wire [31:0] jump;
wire [31:0] final_output;
wire [31:0] v1;
wire [31:0] v2;

control_unit control_unit1 (.clk(clk),.rst(rst),.rs2_input(rs2_input),.rs1_input(rs1_input),.imm(imm),.mem_read(mem_read),.out_signal(out_signal),
									.opcode(opcode),.pc_input(pc_input), .ALUoutput(ALUoutput), .instructions(instructions), .mem_write(mem_write),
									.wr_en(wr_en),.addr(addr),.j_signal(j_signal),.jump(jump),.final_output(final_output),.v1(v1),.v2(v2));

initial clk = 0;
always #10 clk = ~clk;
initial begin 
 
rst=0;
opcode=7'b0110011;
ALUoutput = 32'd10;
out_signal=44'h2000;
mem_read= 32'h3ffff;
rs1_input=32'd13;
rs2_input=32'd13;
imm=32'd1;
pc_input=32'd10;

#100;


opcode=7'b0010011;
ALUoutput = 32'd11;
out_signal=44'h4000;
#100;

opcode=7'b0110111;
ALUoutput = 32'd12;
out_signal=44'h8000;
imm=32'd1;


#100;

opcode=7'b0010111;
ALUoutput = 32'd13;
out_signal=44'h16000;

#100;

opcode= 7'b0000011;
mem_read= 32'h3ffff;
out_signal=44'h100000;
rs1_input=32'd13;

#100;

opcode=  7'b0100011 ;
rs2_input=32'h3ffff;
imm=32'd1;
out_signal=44'h2000000;

#100;

opcode=  7'b1100011 ;
out_signal= 44'h8000000;
rs1_input=32'd13;
rs2_input=32'd13;
pc_input=32'd10;
imm=32'h1;


#100;

opcode=  7'b1101111 ;
pc_input=32'd10;
imm=32'h1;

#100;

opcode=7'b1100111;
rs1_input=32'd10;
imm=32'd1;


#100;

opcode=  7'b0110111 ;
imm=32'd1;


#100;

opcode=  7'b0010111;
imm=32'd1;
pc_input=32'd10;


 



end

endmodule 

    