/**
 * @file control_unit.v
 * 
 * This module implements the control unit of a RISC-V processor, handling control signal generation, and data path control. 
 * The control unit receives input signals such as the opcode, immediate values,
 * register data, and outputs signals to the ALU, memory, and other components.
 * 
 * @param clk          Inputs clock signal.
 * @param rst          Inputs reset signal.
 * @param rs1_input    Inputs value from the first source register.
 * @param rs2_input    Inputs value from the second source register.
 * @param imm          Immediate value for instructions requiring it.
 * @param mem_read     Data read from memory.
 * @param out_signal   Instruction bus from the decoder.
 * @param opcode       Opcode for instructions from the register file.
 * @param pc_input     Program counter input address.
 * @param ALUoutput    Output from the ALU.
 * 
 * @return instructions Instruction bus for the ALU.
 * @return v1           Value going into the ALU from the first source.
 * @return v2           Value going into the ALU from the second source.
 * @return mem_write    Data to be written to memory.
 * @return wr_en        Write enable signal for memory.
 * @return addr         Address for memory operations.
 * @return j_signal     Jump signal for control flow instructions.
 * @return jump         Jump target address.
 * @return final_output Data to be written to the destination register in the register file.
 * @return wr_en_rf     Write enable signal for the register file.
 */

module control_unit(
	input clk,                                                                                                  //!input clock
	input rst,                                                                                                  //!reset pin
	input [31:0] rs2_input,                                                                                     //!rs1 value from Rfile
	input [31:0] rs1_input,                                                                                     //!rs2 value from Rfile
	input [31:0] imm,                                                                                           //!immediate value from Rfile
	input [31:0] mem_read,                                                                                      //!read data from memory
	input [44:0] out_signal,                                                                                    //!instruction bus from decoder
	input [6:0] opcode,                                                                                         //!opcode for instructions from Rfile
	input [31:0] pc_input,                                                                                      //!input from PC(its output address) 
	input [63:0] ALUoutput,                                                                                     //!output from ALU

	output reg [12:0] instructions,																				//!instruction bus for ALU																									
	output reg [31:0] v1,																						//!value going into ALU																													
	output reg [31:0] v2,					    	                                 						    //!value going into ALU                         
	output reg [31:0] mem_write,                                                                                //!write data in memory
	output reg wr_en,                                                                                           //!write signal(enable or disable)
	output reg [31:0] addr,                                                                                     //!address for memory
	output reg j_signal,                                                                                        //!jump signal(enable or disable)
	output reg [31:0] jump,                                                                                     //!jump output for pc
	output reg [31:0] final_output,                                                                             //!goes into Rfile as rd
	output reg wr_en_rf
	);
 reg [1:0] mem_count = 0;
 reg [31:0] Simm = 0;
 reg [63:0] val = 0;
initial begin 
	wr_en_rf <= 0;
	wr_en <= 0;
	j_signal<= 0;
	instructions <= 0;
	mem_write <= 0;
	addr<=0;
	jump <= 0;
	final_output <= 0;
	v1 <= 0;
	v2 <= 0;
	val <= 0;
end	 
always@(*) begin
	case(opcode)
		7'b0110011, 7'b0010011 : begin
			case (out_signal)
				45'h1: begin
					instructions <= 13'd1;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h2: begin
					instructions <= 13'd2;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h4: begin
					instructions <= 13'd4;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h8: begin
					instructions <= 13'd8;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h10: begin
					instructions <= 13'd16;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h20: begin
					instructions <= 13'd32;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h40: begin
					instructions <= 13'd64;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h80: begin
					instructions <= 13'd128;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h100: begin
					instructions <= 13'd256;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h200: begin
					instructions <= 13'd512;
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput;
				end

				45'h400: begin
					instructions <= 13'd1;
					v1 <= rs1_input;
					v2 <= imm;
					final_output <= ALUoutput;
				end

				45'h800: begin
					instructions <= 13'd4;
					v1 <= rs1_input;
					v2 <= Simm;
					final_output <= ALUoutput;
				end

				45'h1000: begin
					instructions <= 13'd8;
					v1 <= rs1_input;
					v2 <= Simm;
					final_output <= ALUoutput;
				end

				45'h2000: begin
					instructions <= 13'd16;
					v1 <= rs1_input;
					v2 <= Simm;
					final_output <= ALUoutput;
				end

				45'h4000: begin
					instructions <= 13'd32;
					v1 <= rs1_input;
					v2 <= imm;
					final_output <= ALUoutput;
				end

				45'h8000: begin
					instructions <= 13'd64;
					v1 <= rs1_input;
					v2 <= imm;
					final_output <= ALUoutput;
				end

				45'h10000: begin
					instructions <= 13'd128;
					v1 <= rs1_input;
					v2 <= imm;
					final_output <= ALUoutput;
				end

				45'h20000: begin
					instructions <= 13'd256;
					v1 <= rs1_input;
					v2 <= Simm;
					final_output <= ALUoutput;
				end

				45'h40000: begin
					instructions <= 13'd512;
					v1 <= rs1_input;
					v2 <= Simm;
					final_output <= ALUoutput;
				end

			//!M extension instructions
				//!multiplication instructions
				45'h2000000000 : begin
					instructions <= 13'd1024; //!mul
						v1 <= rs1_input;
						v2 <= rs2_input;
					final_output <= ALUoutput[31:0];
				end
				45'h4000000000 : begin
					instructions <= 13'd1024; //! mulh
					if (rs1_input[31] == 1 && rs2_input[31] == 1) final_output[31] <= 1'b0;
					if (rs1_input[31] == 1 || rs2_input[31] == 1) final_output[31] <= 1'b1;
					if (rs1_input[31] == 1) begin
						v1 <= ~rs1_input + 1;
					end else begin
						v1 <= rs1_input;
					end
					if (rs2_input[31] == 1) begin
						v2 <= ~rs2_input + 1;
					end else begin
						v2 <= rs2_input;
					end
					final_output[30:0] <= ALUoutput[62:32];
				end
				45'h8000000000 : begin
					instructions <= 13'd1024; //!mulhsu
					final_output[31] <= rs1_input[31];
					v1 <= ~rs1_input + 1;
					v2 <= rs2_input;
					final_output[30:0] <= ALUoutput[62:32];
				end
				45'h10000000000 : begin
					instructions <= 13'd1024; //!mulhu
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput[63:32];
				end
				//!division instructions
				45'h20000000000 : begin
					instructions <= 13'd2048; //!div
					if (rs1_input[31] == 1 && rs2_input[31] == 1) final_output[31] <= 1'b0;
					if (rs1_input[31] == 1 || rs2_input[31] == 1) final_output[31] <= 1'b1;					
					if (rs1_input[31] == 1) begin
						v1 <= ~rs1_input + 1;
					end else begin
						v1 <= rs1_input;
					end
					if (rs2_input[31] == 1) begin
						v2 <= ~rs2_input + 1;
					end else begin
						v2 <= rs2_input;
					end
					final_output[30:0] <= ALUoutput[30:0];
				end
				45'h40000000000 : begin
					instructions <= 13'd2048; //!divu
					v1 <= rs1_input;
					v2 <= rs2_input;
					final_output <= ALUoutput[31:0];
				end
				//!remainder instructions
				45'h80000000000 : begin
					instructions <= 13'd4096; //!rem
					if (rs1_input[31] == 1 && rs2_input[31] == 1) final_output[31] <= 1'b0;
					if (rs1_input[31] == 1 || rs2_input[31] == 1) final_output[31] <= 1'b1;
					if (rs1_input[31] == 1) begin
						v1 <= ~rs1_input + 1;
					end else begin
						v1 <= rs1_input;
					end
					if (rs2_input[31] == 1) begin
						v2 <= ~rs2_input + 1;
					end else begin
						v2 <= rs2_input;
					end
					final_output[30:0] <= ALUoutput[30:0];
				end
				45'h100000000000 : begin
					instructions <= 13'd4096; //!remu
					v1 <= rs1_input;
					v2 <=rs2_input;
					final_output <= ALUoutput[31:0];
				end
			endcase
			if (j_signal == 1) j_signal <= 0;
			if (wr_en_rf == 0) wr_en_rf <= 1;
		end 
        7'b0000011 : begin                                                                          //! mem read set
			addr <= rs1_input[imm[11:0] +: 32];																						//!sending required address
			mem_count <= addr % 4;
			wr_en_rf <= 0;
			wr_en <= 0;
			case(out_signal) 
				45'h80000 :begin
					case (mem_count)
						2'b00:final_output <= { {24{mem_read[7]}}, mem_read[7:0]};                        				 //!lb
						2'b01:final_output <= { {24{mem_read[15]}}, mem_read[15:8]};
						2'b10:final_output <= { {24{mem_read[23]}}, mem_read[23:16]};
						2'b11:final_output <= { {24{mem_read[31]}},  mem_read[31:24]};
					endcase
				end
				45'h100000 :begin
						case (mem_count)
							2'b00: final_output <= { {16{mem_read[15]}}, mem_read[15:0]};                 										//!lh
							2'b10: final_output <= { {16{mem_read[31]}}, mem_read[31:16]};
						endcase
					end
				45'h200000 : final_output <= mem_read[31:0];                                        //!lw
				45'h400000 :begin
						case (mem_count)
							2'b00: final_output <= mem_read[7:0];                                         //!lbu
							2'b01: final_output <= mem_read[15:8];
							2'b10: final_output <= mem_read[23:16];
							2'b11: final_output <= mem_read[31:24];
						endcase
					end
				45'h800000 :begin
					case(mem_count)
						2'b00: final_output <= mem_read[15:0];                                        //!lhu
						2'b10: final_output <= mem_read[31:16];
					endcase
				end
			endcase                                                            
			if(j_signal==1)j_signal<=0;			                                           //!enable read signal
			if(wr_en==1) wr_en<=0;
        end
        7'b0100011 : begin
			addr <= rs1_input + imm;                                                                //!send assigned address
            wr_en <= 2'b1;                                                                          //!enable write signal
            mem_count <= addr % 4;
				case(out_signal)
					 45'h1000000 :begin
						case(mem_count)
							2'b00: mem_write <= {mem_read[31:8], rs2_input[7:0]};                                      //!sb
							2'b01: mem_write <= { mem_read[31:16],  rs2_input[7:0], mem_read[7:0]};
							2'b10: mem_write <= { mem_read[31:24], rs2_input[7:0], mem_read[15:0]};
							2'b11: mem_write <= { rs2_input[7:0], mem_read[23:0]};
						endcase
					end
					45'h2000000 :begin
							case(mem_count)
								2'b00: mem_write <= {mem_read[31:16], rs2_input[15:0]};                                     //!sh
								2'b10: mem_write <= { rs2_input[15:0], mem_read[15:0]};
							endcase
						end
					45'h4000000 : mem_write <= rs2_input[31:0];													//!sw
				endcase
				if(j_signal==1)j_signal<=0;
        		end
        7'b1100011 :begin                                                                           //!branch instruction set                                                                           
			case(out_signal)
				45'h8000000 :begin
					if(rs1_input == rs2_input) begin 
						jump <= pc_input + {{20{imm[12]}},imm[12:1],1'b0};                                                     //!beq
                    	j_signal <= 2'b1;   
            		end 
						else begin
						j_signal <= 2'b0;
					end
						if(wr_en==1) wr_en<=0;
                end																				    //!activate jump signal
				45'h10000000 :begin
					if(rs1_input != rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //!bne
						j_signal <= 2'b1;   
					end	
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																		            //!activate jump signal					 
                45'h20000000 :begin
                    if(rs1_input < rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                    //!blt
						j_signal <= 2'b1;   
					end
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																		            //!activate jump signal
				45'h40000000 :begin
					if(rs1_input >= rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //!bge
						j_signal <= 2'b1;   
					end
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																		            //!activate jump signal 
                45'h80000000 :begin
					if(rs1_input < rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //!bltu 
						j_signal <= 2'b1;   
					end
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																			        //!activate jump signal
                45'h100000000 :begin
					if(rs1_input >= rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //!bgeu
                        j_signal <= 2'b1;   
                     end
					 else begin
						j_signal <= 2'b0;
					end
							if(wr_en==1) wr_en<=0;
                  end																		       //!activate jump signal 
			endcase
        end
        7'b1101111 : begin
			if(out_signal == 45'h200000000) begin   						  //!jal	 
				jump <= pc_input + imm;
				j_signal <= 1;  
                final_output <= pc_input + 4;
            end 
				if(wr_en==1) wr_en<=0;
        end
        7'b1100111 : begin                                                                          //!jalr
			if(out_signal == 45'h400000000) begin			
				jump <= rs1_input + imm;
				j_signal <= 1;  
            final_output <= pc_input + 4; 
            end
				if(wr_en==1) wr_en<=0;
        end
       
		7'b0110111 : begin
			if(j_signal==1)j_signal<=0;
            if(out_signal == 45'h800000000) begin   
				final_output <= {imm[31:12],12'b0};                                                          //!lui
            end
				if(wr_en==1) wr_en<=0;
        end
        7'b0010111 : begin
			if(j_signal==1)j_signal<=0;
            if(out_signal == 45'h1000000000) begin   
				final_output <= pc_input +{imm[31:12],12'b0};                                             //!auipc 
            end   
				if(wr_en==1) wr_en<=0;				
	  	end 

    endcase
end
endmodule 