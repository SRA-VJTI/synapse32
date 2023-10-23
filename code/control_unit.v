`timescale 1ns / 1ps

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
	input [31:0] ALUoutput,                                                                                            //output from ALU
	
	output reg [46:0] instructions,                                                                             //instruction bus for ALU
	output reg [31:0] mem_write,                                                                                //write data in memory
	output reg wr_en,                                                                                           //write signal(enable or disable)
	output reg rd_en =0,                                                                                           //read signal(enable or disable)
	output reg [31:0] addr,                                                                                     //address for memory
	output reg j_signal,                                                                                        //jump signal(enable or disable)
	output reg [31:0] jump,                                                                                     //jump output for pc
	output reg [31:0] final_output,                                                                              //goes into Rfile as rd
	output reg ALUenabled,
	output reg wr_en_rf
);

parameter A=0, B=1 ;
reg state = 2'b1;     
    
initial begin 
	wr_en_rf <= 0;
	wr_en <= 0;
	j_signal<= 0;
	instructions <= 0;
	mem_write <= 0;
	addr<=0;
	jump <= 0;
	final_output <= 0;
	ALUenabled <= 0;
end	 

always @(posedge clk,posedge rst) begin                                                                     //initializing the FSM
 
	if (rst) state<=B;
   else state <= ~state;
end    

always@(*) begin
	case(state)
		B: begin                                                                             //1st state
			case(opcode)
				7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111 : begin                                      //calling ALU
					instructions <= out_signal;
					ALUenabled<=1;                                         //sending instruction bus to ALU
					if(j_signal==1)j_signal<=0;
            end
            7'b0000011 : begin                                                                          // mem read set
					addr <= rs1_input + imm;                                                                //sending required address
               rd_en <= 2'b1; 
					if(j_signal==1)j_signal<=0;                                                                         //enable read signal
            end
            7'b0100011 : begin
					addr <= rs1_input + imm;                                                                //send assigned address
               wr_en <= 2'b1;                                                                          //enable write signal
               case(out_signal)
						47'h1000000 : mem_write <= rs2_input[7:0];                                          //sb
                  47'h2000000 : mem_write <= rs2_input[15:0];                                         //sh
                  47'h4000000 : mem_write <= rs2_input[31:0];                                         //sw
               endcase
					if(j_signal==1)j_signal<=0;
            end
            7'b1100011 :begin                                                                           //branch instruction set                                                                           
					case(out_signal)
						47'h8000000 :begin
							if(rs1_input == rs2_input) begin 
								jump <= pc_input + imm;                                                     //beq
                        j_signal <= 2'b1;   
                     end 
                  end																				    //activate jump signal
						47'h10000000 :begin
							if(rs1_input != rs2_input) begin 
								jump <= pc_input + imm;                                                     //bne
						      j_signal <= 2'b1;   
						   end	
						end																		            //activate jump signal					 
                  47'h20000000 :begin
                     if(rs1_input < rs2_input) begin 
								jump <= pc_input + imm;                                                    //blt
								j_signal <= 2'b1;   
							end	
					   end																		            //activate jump signal
						47'h40000000 :begin
							if(rs1_input >= rs2_input) begin 
								jump <= pc_input + imm;                                                     //bge
								j_signal <= 2'b1;   
							end	
						end																		            //activate jump signal 
                  47'h80000000 :begin
							if(rs1_input < rs2_input) begin 
								jump <= pc_input + imm;                                                     //bltu 
								j_signal <= 2'b1;   
							end	
						end																			        //activate jump signal
                  47'h100000000 :begin
							if(rs1_input >= rs2_input) begin 
								jump <= pc_input + imm;                                                     //bgeu
                        j_signal <= 2'b1;   
                     end 
                  end																				    //activate jump signal 
					endcase
            end
            7'b1101111 : begin
					if(out_signal == 47'h200000000) begin   						  //jal	 
						jump <= pc_input + imm;
						j_signal <= 2'b1;  
                  final_output <= pc_input + 1;
               end 
            end
            7'b1100111 : begin                                                                          //jalr
					if(out_signal == 47'h400000000) begin			
						jump <= rs1_input + imm;
						j_signal <= 2'b1;  
                  final_output <= pc_input + 1; 
               end
            end
            7'b0110111 : begin
					if(j_signal==1)j_signal<=0;
               if(out_signal == 47'h800000000) begin   
						final_output <= imm << 12;                                                          //lui
               end
            end
            7'b0010111 : begin
					if(j_signal==1)j_signal<=0;
               if(out_signal == 47'h1000000000) begin   
						final_output <= pc_input + (imm << 12);                                             //auipc 
               end                
            end
         endcase
		end
      A: begin                                                                                            //second state	
			case(opcode)
				7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111 : begin                                      //recieving ALU output
					final_output <= ALUoutput;
					wr_en_rf <= 2'b1;
            end 
            7'b0000011 : begin
					wr_en_rf <= 2'b1;
               case(out_signal) 
						47'h80000 : final_output <= mem_read[7:0];                                          //lb
                  47'h100000 : final_output <= mem_read[15:0];                                        //lh
                  47'h200000 : final_output <= mem_read[31:0];                                        //lw
                  47'h400000 : final_output <= mem_read[7:0];                                         //lbu
                  47'h800000 : final_output <= mem_read[15:0];                                        //lhu
               endcase
               rd_en = 2'b0; 
            end
         endcase
      end
   endcase
end
endmodule
