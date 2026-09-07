`default_nettype none
`include "instr_defines.vh"
module execution_unit(
    input wire [31:0] rs1,
    input wire [31:0] rs2,
    input wire [31:0] imm,
    input wire [4:0] rs1_addr,
    input wire [4:0] rs2_addr,
    input wire [6:0] opcode,
    input wire [6:0] instr_id,
    input wire rs1_valid,
    input wire rs2_valid,
    input wire [31:0] pc_input,
    
    // Data forwarding inputs
    input wire [1:0] forward_a,
    input wire [1:0] forward_b,
    input wire [31:0] ex_mem_result,
    input wire [31:0] mem_wb_result,
    
    // CSR interface inputs
    input wire [31:0] csr_read_data,
    input wire csr_valid,
    
    // CSR interface outputs
    output wire [11:0] csr_addr,
    output wire csr_read_enable,
    output wire [31:0] csr_write_data,
    output wire csr_write_enable,
    
    output reg [31:0] exec_output,
    output reg jump_signal,
    output reg [31:0] jump_addr,
    output reg [31:0] mem_addr,
    output reg [31:0] rs1_value_out,
    output reg [31:0] rs2_value_out,
    output reg flush_pipeline,
    
    // Add interrupt/exception inputs
    input wire interrupt_pending,
    input wire [31:0] interrupt_cause,
    input wire [31:0] mtvec,
    input wire [31:0] mepc,
    
    // Add interrupt/exception outputs
    output reg interrupt_taken,
    output reg mret_instruction,
    output reg ecall_exception,
    output reg ebreak_exception,
    output reg wfi_instruction,
    output reg misaligned_exception,
    output reg [31:0] misaligned_cause
);

// Internal signals for forwarded values
reg [31:0] rs1_value;
reg [31:0] rs2_value;

assign rs1_value_out = rs1_value;
assign rs2_value_out = rs2_value;

// Forwarding control values (must match forwarding_unit.v)
localparam NO_FORWARDING = 2'b00;
localparam FORWARD_FROM_MEM = 2'b01;
localparam FORWARD_FROM_WB = 2'b10;

// CSR-related signals
assign csr_addr = imm[11:0];  // Extract CSR address from immediate field

// CSR read enable for all CSR instructions
assign csr_read_enable = (instr_id == INSTR_CSRRW) || (instr_id == INSTR_CSRRS) || 
                        (instr_id == INSTR_CSRRC) || (instr_id == INSTR_CSRRWI) || 
                        (instr_id == INSTR_CSRRSI) || (instr_id == INSTR_CSRRCI);

// CSR execution unit for handling CSR operations
wire [31:0] csr_rd_value;
csr_exec csr_exec_inst (
    .instr_id(instr_id),
    .rs1_value(rs1_value),
    .rs1_addr(rs1_addr),
    .csr_read_data(csr_read_data),
    .csr_write_data(csr_write_data),
    .csr_write_enable(csr_write_enable),
    .rd_value(csr_rd_value)
);

// Select forwarded values if needed
always @(*) begin
    // Forward logic for rs1
    case (forward_a)
        NO_FORWARDING: rs1_value = rs1;
        FORWARD_FROM_MEM: rs1_value = ex_mem_result;
        FORWARD_FROM_WB: rs1_value = mem_wb_result;
        default: rs1_value = rs1;
    endcase
    
    // Forward logic for rs2
    case (forward_b)
        NO_FORWARDING: rs2_value = rs2;
        FORWARD_FROM_MEM: rs2_value = ex_mem_result;
        FORWARD_FROM_WB: rs2_value = mem_wb_result;
        default: rs2_value = rs2;
    endcase
end

alu alu_inst(
    .rs1(rs1_value),
    .rs2(rs2_value),
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
    // Default values
    exec_output = 0;
    jump_signal = 0;
    jump_addr = 0;
    mem_addr = 0;
    flush_pipeline = 0;
    interrupt_taken = 0;
    mret_instruction = 0;
    ecall_exception = 0;
    ebreak_exception = 0;
    wfi_instruction = 0;
    misaligned_exception = 0;
    misaligned_cause = 32'b0;
    
    // Handle interrupts first (highest priority)
    if (interrupt_pending) begin
        jump_signal = 1;
        jump_addr = mtvec;  // Jump to interrupt handler
        flush_pipeline = 1;
        interrupt_taken = 1;
    end else begin
        case (opcode)
            7'b0110011: begin // R-type instructions
            exec_output = alu_inst.ALUoutput;
            end
            7'b0010011: begin // I-type instructions
            exec_output = alu_inst.ALUoutput;
            end
            7'b0000011: begin // Load instructions
            mem_addr = rs1_value + imm;
            end
            7'b0100011: begin // Store instructions
            mem_addr = rs1_value + imm;
            end
            7'b0101111: begin // AMO/LR/SC instructions
            mem_addr = rs1_value;
            if ((instr_id == INSTR_LR_W || instr_id == INSTR_SC_W) &&
                (rs1_value[1:0] != 2'b00)) begin
                jump_signal = 1;
                jump_addr = mtvec;
                flush_pipeline = 1;
                misaligned_exception = 1;
                misaligned_cause = (instr_id == INSTR_LR_W) ? 32'd4 : 32'd6;
            end
            end
            7'b1100011: begin // Branch instructions
            case (instr_id)
                INSTR_BEQ: begin
                    if (rs1_value == rs2_value) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                        flush_pipeline = 1;
                    end
                end
                INSTR_BNE: begin
                    if (rs1_value != rs2_value) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                        flush_pipeline = 1;
                    end
                end
                INSTR_BLT: begin
                    if ($signed(rs1_value) < $signed(rs2_value)) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                        flush_pipeline = 1;
                    end
                end
                INSTR_BGE: begin
                    if ($signed(rs1_value) >= $signed(rs2_value)) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                        flush_pipeline = 1;
                    end
                end
                INSTR_BLTU: begin
                    if (rs1_value < rs2_value) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                        flush_pipeline = 1;
                    end
                end
                INSTR_BGEU: begin
                    if (rs1_value >= rs2_value) begin
                        jump_signal = 1;
                        jump_addr = pc_input + imm;
                        flush_pipeline = 1;
                    end
                end
                default: begin
                end
            endcase
            end
            7'b1101111: begin // JAL
            jump_signal = 1;
            jump_addr = pc_input + imm;
            exec_output = pc_input + 4;
            flush_pipeline = 1;
            end
            7'b1100111: begin // JALR
            jump_signal = 1;
            jump_addr = (rs1_value + imm) & 32'hFFFFFFFE;
            exec_output = pc_input + 4;
            flush_pipeline = 1;
            end
            7'b0110111: begin // LUI
            exec_output = imm;
            end
            7'b0010111: begin // AUIPC
            exec_output = pc_input + imm;
            end
            7'b1110011: begin // System instructions
            case (instr_id)
                INSTR_MRET: begin
                    jump_signal = 1;
                    jump_addr = mepc;  // Return from interrupt
                    flush_pipeline = 1;
                    mret_instruction = 1;
                end
                INSTR_ECALL: begin
                    jump_signal = 1;
                    jump_addr = mtvec;  // Jump to trap handler
                    flush_pipeline = 1;
                    ecall_exception = 1;
                end
                INSTR_EBREAK: begin
                    jump_signal = 1;
                    jump_addr = mtvec;  // Jump to trap handler
                    flush_pipeline = 1;
                    ebreak_exception = 1;
                end
                INSTR_WFI: begin
                    // Enter sleep after retiring WFI and stay stalled in CPU
                    // until an interrupt becomes pending.
                    jump_signal = 1;
                    jump_addr = pc_input + 4;
                    flush_pipeline = 1;
                    wfi_instruction = 1;
                end
                default: begin
                    exec_output = csr_rd_value;  // CSR instructions
                end
            endcase
            end
            7'b0001111: begin // MISC-MEM (fence instructions)
            if (instr_id == INSTR_FENCE_I) begin
                flush_pipeline = 1;
            end
            end
            default: begin
            end
        endcase
    end
end

endmodule
