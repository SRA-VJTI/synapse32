
module registerfile(
	input clk,
	input [4:0]rs1,
	input [4:0]rs2,
	input rs1_valid,
	input rs2_valid,
	input [31:0]rd,
	input wr_en,
	input [31:0]rd_value,
 
	output reg [31:0]rs1_value,
	output reg [31:0]rs2_value
);    
	reg [31:0] register_file [31:0];
 
initial begin
	register_file[0]=0;
	register_file[1]=0;
	register_file[2]=0;
	register_file[3]=0;
    register_file[4]=0;
	register_file[5]=0;
	register_file[6]=0;
	register_file[7]=0;
	register_file[8]=0;
	register_file[9]=0;
	register_file[10]=0;
	register_file[11]=0;
	register_file[12]=0;
	register_file[13]=0;
	register_file[14]=0;
	register_file[15]=0;
	register_file[16]=0;
	register_file[17]=0;
	register_file[18]=0;
	register_file[19]=0;
	register_file[20]=0;
	register_file[21]=0;
	register_file[22]=0;
	register_file[23]=0;
	register_file[24]=0;
	register_file[25]=0;
	register_file[26]=0;
	register_file[27]=0;
	register_file[28]=0;
	register_file[29]=0;
	register_file[30]=0;
	register_file[31]=0;
end

always@(*) begin
	if (rs1_valid) 
	rs1_value <= register_file[rs1[4:0]];
	else rs1_value <= 0;
	if (rs2_valid) rs2_value <= register_file[rs2[4:0]];
	else rs2_value <= 0;
end

always @(posedge clk) begin 
	register_file[0]<=0;
	if (wr_en&&rd[4:0]!=0) begin
		register_file[rd[4:0]]<=rd_value;
   end
end 
endmodule