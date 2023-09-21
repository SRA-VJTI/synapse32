module control_unit_tb;
reg clk;
reg rst;
reg [31:0] rs2_input;
reg [31:0] rs1_input;
reg [31:0] rd_input;
reg [31:0] imm;
reg [2:0] func3;
reg [6:0] func7;
reg rd_valid;
reg rs1_valid;
reg rs2_valid;
reg imm_valid;
reg [31:0] mem_read;
reg [46:0] out_signal;
reg [6:0] opcode;
reg [31:0] decoder_signal;
reg [31:0] pc_input;
reg ALUoutput;
wire [46:0] instructions;
wire [31:0] pc_output;                     
wire rs1_output;
wire rs2_output;
wire  [31:0] mem_write;
wire wr_en;
wire rd_en;
wire addr;
wire j_signal;
wire [31:0] jump;
wire [31:0] final_output;

control_unit control_unit1 (.clk(clk),.rst(rst),.rs2_input(rs2_input),.rs1_input(rs1_input),.rs2_input(rs2_input),.rd_input(rd_input),.imm(imm),		
									.func3(func3),.func7(func7),.rd_valid(rd_valid),.rs1_valid(rs1_valid),.rs2_valid(rs2_valid),.imm_valid(imm_valid),.mem_read(mem_read),
									.out_signal(out_signal),.opcode(opcode),.decoder_signal(decoder_signal),.pc_input(pc_input),.instructions(instructions),
									.pc_output(pc_output),.rs1_output(rs1_output),.rs2_output(rs2_output),.mem_write(mem_write),.wr_en(wr_en),.rd_en(rd_en),
									.addr(addr),.j_signal(j_signal),.jump(jump),.final_output(final_output));

initial clk = 0;
always #10 clk = ~clk;
initial begin 


end

endmodule 

    