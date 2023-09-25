`timescale 1ns / 1ps



module control_unit_tb;
reg clk;
reg rst;
reg [31:0] rs2_input;
reg [31:0] rs1_input;
reg [31:0] imm;
reg [31:0] mem_read;
reg [46:0] out_signal;
reg [6:0] opcode;
reg [31:0] pc_input;
reg ALUoutput;
wire [46:0] instructions;                   
wire  [31:0] mem_write;
wire wr_en;
wire rd_en;
wire addr;
wire j_signal;
wire [31:0] jump;
wire [31:0] final_output;

control_unit control_unit1 (.clk(clk),.rst(rst),.rs2_input(rs2_input),.rs1_input(rs1_input),.imm(imm),.mem_read(mem_read),.out_signal(out_signal),
									.opcode(opcode),.pc_input(pc_input), .ALUoutput(ALUoutput), .instructions(instructions), .mem_write(mem_write),
									.wr_en(wr_en),.rd_en(rd_en),.addr(addr),.j_signal(j_signal),.jump(jump),.final_output(final_output));

initial clk = 0;
always #10 clk = ~clk;
initial begin 
 

opcode=7'b0110011;

#100;


opcode=7'b0010011;


#100;

opcode=7'b0110111;


#100;

opcode=7'b0010111;

#100;

opcode= 7'b0000011;

#100;

opcode=  7'b0100011 ;
#100;

opcode=  7'b1100011 ;

#100;

opcode=  7'b1101111 ;


#100;

opcode=7'b1100111;

#100;

opcode=  7'b0110111 ;

#100;

opcode=  7'b0010111;

#100;

opcode=  7'b0010111;
 



end

endmodule 

    