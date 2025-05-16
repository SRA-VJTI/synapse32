`default_nettype none
module execution_unit(
    input wire [31:0] rs1,
    input wire [31:0] rs2,
    input wire [31:0] imm,
    input wire [4:0] rs1_addr,
    input wire [4:0] rs2_addr,
    input wire [4:0] rd_addr,
    input wire [6:0] opcode,
    input wire [5:0] instr_id,
    input wire rs1_valid,
    input wire rs2_valid,
    input wire [31:0] pc_input,
    output reg [31:0] exec_output,
    output reg jump_signal,
    output reg [31:0] jump_addr,
    output reg [31:0] mem_addr
);

alu alu_inst(
    .rs1(rs1),
    .rs2(rs2),
    .imm(imm),
    .instr_id(instr_id),
    .pc_input(jump_addr),
    .ALUoutput()
);

// For all R-type instructions, the exec_output is the output of the ALU
// For all I-type instructions, the exec_output is the output of the ALU
// For all the Load instructions, calculate the address
// For all the Store instructions, calculate the address
// For all the Branch instructions, verify the condition and calculate the address
// For all the Jump instructions, calculate the address
// For all U-type instructions, the exec_output is the output of the ALU
// For NOP, do nothing
always @(*) begin
    case (opcode)
        7'b0110011: begin // R-type instructions
            exec_output = alu_inst.ALUoutput;
            jump_signal = 0;
            jump_addr = 0;
            mem_addr = 0;
        end
        7'b0010011: begin // I-type instructions
            exec_output = alu_inst.ALUoutput;
            jump_signal = 0;
            jump_addr = 0;
            mem_addr = 0;
        end
        7'b0000011: begin // Load instructions
            mem_addr = rs1 + imm;
            exec_output = 0;
            jump_signal = 0;
            jump_addr = 0;
        end
        7'b0100011: begin // Store instructions
            mem_addr = rs1 + imm;
            exec_output = 0;
            jump_signal = 0;
            jump_addr = 0;
        end
        7'b1100011: begin // Branch instructions
            case (instr_id)
                6'h1C: begin // BEQ
                    if (rs1 == rs2) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                    end else begin
                        jump_signal = 0;
                        jump_addr = 0;
                    end
                end
                6'h1D: begin // BNE
                    if (rs1 != rs2) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                    end else begin
                        jump_signal = 0;
                        jump_addr = 0;
                    end
                end
                6'h1E: begin // BLT
                    if ($signed(rs1) < $signed(rs2)) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                    end else begin
                        jump_signal = 0;
                        jump_addr = 0;
                    end
                end
                6'h1F: begin // BGE
                    if ($signed(rs1) >= $signed(rs2)) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                    end else begin
                        jump_signal = 0;
                        jump_addr = 0;
                    end
                end
                6'h20: begin // BLTU
                    if (rs1 < rs2) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                    end else begin
                        jump_signal = 0;
                        jump_addr = 0;
                    end
                end
                6'h21: begin // BGEU
                    if (rs1 >= rs2) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                    end else begin
                        jump_signal = 0;
                        jump_addr = 0;
                    end
                end
                default: begin
                    jump_signal = 0;
                    jump_addr = 0;
                end
            endcase
            exec_output = 0;
            mem_addr = 0;
        end
        7'b1101111: begin // JAL
            jump_signal = 1;
            jump_addr = pc_input + imm;
            exec_output = pc_input + 4;
            mem_addr = 0;
        end
        7'b1100111: begin // JALR
            jump_signal = 1;
            jump_addr = (rs1 + imm) & 32'hFFFFFFFE;
            exec_output = pc_input + 4;
            mem_addr = 0;
        end
        7'b0110111: begin // LUI
            exec_output = imm << 12;
            jump_signal = 0;
            jump_addr = 0;
            mem_addr = 0;
        end
        default: begin
            exec_output = 0;
            jump_addr = 0;
            jump_signal = 0;
            mem_addr = 0;
        end
    endcase
end

endmodule