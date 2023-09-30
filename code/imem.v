`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 30.08.2023 16:36:26
// Design Name: 
// Module Name: imem
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


module imem(
input clk,
input wr_en,
input [31:0]data_in,
input  [31:0]addr,
output [31:0] data_out
  );
    
reg [31:0] ins_mem [31:0] ;
    
reg [31:0] data_out_reg;

initial begin

      ins_mem[0] = 32'h0;
      ins_mem[1] = 32'h0713;
      ins_mem[2] = 32'ha00613;
      ins_mem[3] = 32'h80100693;
      ins_mem[4] = 32'h0e68733;
      ins_mem[5] = 32'h0168693;
      ins_mem[6] = 32'hFEC6CCE3;
      ins_mem[7] = 32'hFD470F13;
      ins_mem[8] = 32'h5063;
end
 
assign data_out = ins_mem[addr[4:0]];

always@(*) begin
 if(wr_en) begin
    ins_mem[addr[4:0]]<=data_in;
    end
end



endmodule
