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
input [31:0] mem_read,
input [46:0] out_signal,
input [6:0] opcode,
input [31:0] decoder_signal,
input [31:0] pc_input,
input ALUoutput,
output [46:0] instructions,
output [31:0] pc_output,                         //pc_output
output rs1_output,
output rs2_output,
output reg [31:0] mem_write,
output wr_en,
output rd_en,
output addr,
output reg j_signal,
output [31:0] jump,
output reg [31:0] final_output
    

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
                7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111 : begin             //calling ALU
                    instructions <= out_signal;                     
                end
                7'b0000011 : begin                                                 // I set
                    addr <= rs1 + imm;
                    rd_en <= 2'b1;
                end
            endcase
        end
        A: begin 
            case(opcode)
                7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111 : begin
                    final_output <= ALUoutput;
                end 
                7'b0000011 : begin
                    case(out_signal) 
                        46'h80000 : final_output <= mem_read[7:0]; 
                        46'h100000 : final_output <= mem_read[15:0];
                        46'h200000 : final_output <= mem_read[31:0];
                        46'h400000 : final_output <= mem_read[7:0];
                        46'h800000 : final_output <= mem_read[15:0];
                    endcase 
                end
                7'b0100011 : begin
                    case(out_signal)
                        46'h1000000 : mem_write <= rs2_input[7:0];
                        46'h2000000 : mem_write <= rs2_input[15:0];
                        46'h4000000 : mem_write <= rs2_input[31:0];
                    endcase    
                end
            endcase
        end
    endcase
    
end

endmodule
