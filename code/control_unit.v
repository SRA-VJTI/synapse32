`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 17.09.2023 18:17:03
// Design Name: 
// Module Name: control_unit
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


module control_unit(
input clk,
input rst,
input [31:0] rs2_input,
input [31:0] rs1_input,
input [31:0] rd_input,
input [31:0] imm,
input [2:0] func3,
input [6:0] func7,
input rd_valid,
input rs1_valid,
input rs2_valid,
input imm_valid,
input [6:0] opcode,
input [31:0] decoder_signal,
input [31:0] pc_input,
input ALU_output,
output [31:0] pc_output,
output rs1_output,
output rs2_output,
output wr_en,
output rd_en,
output sig_to_ALU,
output pc_jump

    

    );
parameter A=0, B=1 ;
reg state, next_state; 
reg temp_pc, temp_pc_jump;   
    
always @(posedge clk,posedge rst) begin
    if (rst) state<=B;
    else
        state<=next_state;
    end    


always@(*) begin
    case(state)
        B: begin
            case(opcode)
                7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111
 
            endcase
        end
        A: begin 
  
        end
    endcase
    
end

endmodule
