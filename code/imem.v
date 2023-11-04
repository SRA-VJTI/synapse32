
module imem(
input clk,
input wr_en,
input [31:0]data_in,
input  [31:0]addr,

output  [31:0] data_out
);    

reg [31:0] ins_mem [31:0] ;    
reg [31:0] data_out_reg;

initial begin 
ins_mem[0] = 32'h0;
      ins_mem[1] = 32'h00100113;                                                                                           //addi
      ins_mem[2] = 32'h00100193;                                                                                           //addi 
      ins_mem[3] = 32'h00218133;                                                                                           //add 
      ins_mem[4] = 32'h002181b3;                                                                                           //add 
      ins_mem[5] = 32'hfffff26f;

end



	always@(posedge clk) begin
		

		if(wr_en) begin
			ins_mem[addr[4:0]]<=data_in;
		end
	end
	assign data_out = ins_mem[addr[4:0]];

endmodule