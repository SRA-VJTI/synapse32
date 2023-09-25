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
input clk,                                                                                                  //input clock
input rst,                                                                                                  //reset pin
input [31:0] rs2_input,                                                                                     //rs1 value from Rfile
input [31:0] rs1_input,                                                                                     //rs2 value from Rfile
input [31:0] imm,                                                                                           //immediate value from Rfile
input [31:0] mem_read,                                                                                      //read data from memory
input [46:0] out_signal,                                                                                    //instruction buss from decoder
input [6:0] opcode,                                                                                         //opcode for instructions from Rfile
input [31:0] pc_input,                                                                                      //input from PC(its output address) 
input ALUoutput,                                                                                            //output from ALU
output reg [46:0] instructions,                                                                             //instruction bus for ALU
output reg [31:0] mem_write,                                                                                //write data in memory
output reg wr_en,                                                                                           //write signal(enable or disable)
output reg rd_en,                                                                                           //read signal(enable or disable)
output reg [31:0] addr,                                                                                     //address for memory
output reg j_signal,                                                                                        //jump signal(enable or disable)
output reg [31:0] jump,                                                                                     //jump output for pc
output reg [31:0] final_output                                                                              //goes into Rfile as rd
    

    );
parameter A=0, B=1 ;
reg state = 2'b0;     
    
always @(posedge clk,posedge rst) begin                                                                     //initializing the FSM
 
	 if (rst) state<=B;
    else
        state <= ~state;
    end    


always@(*) begin
   wr_en=0;
rd_en=0;
j_signal=0;
instructions = 0;
mem_write = 0;
addr=0;
jump = 0;
final_output = 0;


    case(state)
        B: begin                                                                                            //1st state
            case(opcode)
                7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111 : begin                                      //calling ALU
                    instructions <= out_signal;                                                             //sending instruction bus to ALU
                end
                7'b0000011 : begin                                                                          // mem read set
                    addr <= rs1_input + imm;                                                                //sending required address
                    rd_en <= 2'b1;                                                                          //enable read signal
                end
                7'b0100011 : begin
                    addr <= rs1_input + imm;                                                                //send assigned address
                    wr_en <= 2'b1;                                                                          //enable write signal
                    case(out_signal)
                        46'h1000000 : mem_write <= rs2_input[7:0];                                          //sb
                        46'h2000000 : mem_write <= rs2_input[15:0];                                         //sh
                        46'h4000000 : mem_write <= rs2_input[31:0];                                         //sw
                    endcase
                end
                7'b1100011 :begin                                                                           //branch instruction set
                                                                                       
                    case(out_signal)
                        46'h8000000 :begin
                            if(rs1_input == rs2_input) begin jump <= pc_input + imm;                              //beq
                          j_signal <= 2'b1;   end end																				//activate jump signal
								  
                        46'h10000000 :begin
                            if(rs1_input != rs2_input) begin jump <= pc_input + imm;                              //bne
								 j_signal <= 2'b1;   end	end																		//activate jump signal					
								 
                        46'h20000000 :begin
                            if(rs1_input < rs2_input) begin jump <= pc_input + imm;                               //blt
								 j_signal <= 2'b1;   end	end																		//activate jump signal
								 
                        46'h40000000 :begin
                            if(rs1_input >= rs2_input) begin jump <= pc_input + imm;                              //bge
								 j_signal <= 2'b1;   end	end																		//activate jump signal
								 
                        46'h80000000 :begin
                            if(rs1_input < rs2_input) begin jump <= pc_input + imm;                               //bltu 
								 j_signal <= 2'b1;   end	end																			//activate jump signal
                        46'h100000000 :begin
                            if(rs1_input >= rs2_input) begin jump <= pc_input + imm;                              //bgeu
                         j_signal <= 2'b1;   end end																				//activate jump signal 
								 
                    endcase
                end
                7'b1101111 : begin                                                                          //jal
                    jump <= pc_input + imm;
                    final_output <= pc_input + 4; 
                end
                7'b1100111 : begin                                                                          //jalr
                    jump <= rs1_input + imm;
                    final_output <= pc_input + 4;
                end
                7'b0110111 : begin
                    final_output <= imm << 12;                                                              //lui
                end
                7'b0010111 : begin
                    final_output <= pc_input + (imm << 12);                                                 //auipc 
                end
            endcase
        end
        A: begin                                                                                            //second state
            case(opcode)
                7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111 : begin                                      //recieving ALU output
                    final_output <= ALUoutput;
                end 
                7'b0000011 : begin                                                                            
                    case(out_signal) 
                        46'h80000 : final_output <= mem_read[7:0];                                          //lb
                        46'h100000 : final_output <= mem_read[15:0];                                        //lh
                        46'h200000 : final_output <= mem_read[31:0];                                        //lw
                        46'h400000 : final_output <= mem_read[7:0];                                         //lbu
                        46'h800000 : final_output <= mem_read[15:0];                                        //lhu
                    endcase 
                end
            endcase
        end
    endcase
end
endmodule
