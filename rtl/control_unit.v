module control_unit(
	input clk,                                                                                                  //input clock
	input rst,                                                                                                  //reset pin
	input [31:0] rs2_input,                                                                                     //rs1 value from Rfile
	input [31:0] rs1_input,                                                                                     //rs2 value from Rfile
	input [31:0] imm,                                                                                           //immediate value from Rfile
	input [31:0] mem_read,                                                                                      //read data from memory
	input [36:0] out_signal,                                                                                    //instruction buss from decoder
	input [6:0] opcode,                                                                                         //opcode for instructions from Rfile
	input [31:0] pc_input,                                                                                      //input from PC(its output address) 
	input [31:0] ALUoutput,                                                                                            //output from ALU
	
	output reg [36:0] instructions,                                                                             //instruction bus for ALU
	output reg [31:0] mem_write,                                                                                //write data in memory
	output reg wr_en,                                                                                           //write signal(enable or disable
	output reg [31:0] addr,                                                                                     //address for memory
	output reg j_signal,                                                                                        //jump signal(enable or disable)
	output reg [31:0] jump,                                                                                     //jump output for pc
	output reg [31:0] final_output,                                                                              //goes into Rfile as rd
	output reg wr_en_rf
);
 reg [31:0] temp = 0;
 reg [1:0] mem_count = 0;
initial begin 
	wr_en_rf <= 0;
	wr_en <= 0;
	j_signal<= 0;
	instructions <= 0;
	mem_write <= 0;
	addr<=0;
	jump <= 0;
	final_output <= 0;
end	 

always@(*) begin
	case(opcode)
		7'b0110011, 7'b0010011, 7'b0110111, 7'b0010111, 7'b0110111, 7'b0010111 : begin                                      //calling ALU
			instructions <= out_signal;
			final_output <= ALUoutput;
			wr_en_rf <= 2'b1;
			if(j_signal==1) j_signal<=0;
			if(wr_en==1) wr_en<=0;
        end
        7'b0000011 : begin                                                                          // mem read set
			addr <= rs1_input + imm;																						//sending required address
			mem_count <= addr % 4;
			case(out_signal) 
				37'h80000 :begin
					case (mem_count)
						2'b00:final_output <= { {24{mem_read[7]}}, mem_read[7:0]};                        				 //lb
						2'b01:final_output <= { {24{mem_read[15]}}, mem_read[15:8]};
						2'b10:final_output <= { {24{mem_read[23]}}, mem_read[23:16]};
						2'b11:final_output <= { {24{mem_read[31]}},  mem_read[31:24]};
					endcase
				end
            37'h100000 :begin
					case (mem_count)
						2'b00: final_output <= { {16{mem_read[15]}}, mem_read[15:0]};                 										//lh
						2'b10: final_output <= { {16{mem_read[31]}}, mem_read[31:16]};
					endcase
				end
				37'h200000 : final_output <= mem_read[31:0];                                        //lw
            37'h400000 :begin
					case (mem_count)
						2'b00: final_output <= mem_read[7:0];                                         //lbu
						2'b01: final_output <= mem_read[15:8];
						2'b10: final_output <= mem_read[23:16];
						2'b11: final_output <= mem_read[31:24];
					endcase
				end
				37'h800000 :begin
					case(mem_count)
						2'b00: final_output <= mem_read[15:0];                                        //lhu
						2'b10: final_output <= mem_read[31:16];
					endcase
				end
			endcase                                                            
			if(j_signal==1)j_signal<=0;			                                           //enable read signal
			if(wr_en==1) wr_en<=0;
        end
        7'b0100011 : begin
				addr <= rs1_input + imm;                                                                //send assigned address
            wr_en <= 2'b1;                                                                          //enable write signal
            mem_count <= addr % 4;
				case(out_signal)
					 37'h1000000 :begin
						case(mem_count)
							2'b00: mem_write <= {mem_read[31:8], rs2_input[7:0]};                                      //sb
							2'b01: mem_write <= { mem_read[31:16],  rs2_input[7:0], mem_read[7:0]};
							2'b10: mem_write <= { mem_read[31:24], rs2_input[7:0], mem_read[15:0]};
							2'b11: mem_write <= { rs2_input[7:0], mem_read[23:0]};
						endcase
					end
                37'h2000000 :begin
						case(mem_count)
							2'b00: mem_write <= {mem_read[31:16], rs2_input[15:0]};                                     //sh
							2'b10: mem_write <= { rs2_input[15:0], mem_read[15:0]};
						endcase
					end
                37'h4000000 : mem_write <= rs2_input[31:0];													//sw
            endcase
			if(j_signal==1)j_signal<=0;
        end
        7'b1100011 :begin                                                                           //branch instruction set                                                                           
			case(out_signal)
				37'h8000000 :begin
					if(rs1_input == rs2_input) begin 
						jump <= pc_input + {{20{imm[12]}},imm[12:1],1'b0};                                                     //beq
                    	j_signal <= 2'b1;   
            		end 
						else begin
						j_signal <= 2'b0;
					end
						if(wr_en==1) wr_en<=0;
                end																				    //activate jump signal
				37'h10000000 :begin
					if(rs1_input != rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //bne
						j_signal <= 2'b1;   
					end	
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																		            //activate jump signal					 
                37'h20000000 :begin
                    if(rs1_input < rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                    //blt
						j_signal <= 2'b1;   
					end
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																		            //activate jump signal
				37'h40000000 :begin
					if(rs1_input >= rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //bge
						j_signal <= 2'b1;   
					end
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																		            //activate jump signal 
                37'h80000000 :begin
					if(rs1_input < rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //bltu 
						j_signal <= 2'b1;   
					end
					else begin
						j_signal <= 2'b0;
					end
					if(wr_en==1) wr_en<=0;
				end																			        //activate jump signal
                37'h100000000 :begin
					if(rs1_input >= rs2_input) begin 
						jump <= pc_input +{{20{imm[12]}},imm[12:1],1'b0};                                                     //bgeu
                        j_signal <= 2'b1;   
                     end
					 else begin
						j_signal <= 2'b0;
					end
							if(wr_en==1) wr_en<=0;
                  end																				    //activate jump signal 
			endcase
        end
        7'b1101111 : begin
			if(out_signal == 37'h200000000) begin   						  //jal	 
				jump <= pc_input + imm;
				j_signal <= 2'b1;  
                final_output <= pc_input + 4;
            end 
				if(wr_en==1) wr_en<=0;
        end
        7'b1100111 : begin                                                                          //jalr
			if(out_signal == 37'h400000000) begin			
				jump <= rs1_input + imm;
				j_signal <= 2'b1;  
            final_output <= pc_input + 4; 
            end
				if(wr_en==1) wr_en<=0;
        end
//        7'b0110111 : begin
//			if(j_signal==1)j_signal<=0;
//            if(out_signal == 37'h800000000) begin   
//				final_output <= {imm[31:12],12'b0};                                                          //lui
//            end
//				if(wr_en==1) wr_en<=0;
//        end
//        7'b0010111 : begin
//			if(j_signal==1)j_signal<=0;
//            if(out_signal == 37'h1000000000) begin   
//				final_output <= pc_input +{imm[31:12],12'b0};                                             //auipc 
//            end   
//				if(wr_en==1) wr_en<=0;				
  //      end
    endcase
end
endmodule 