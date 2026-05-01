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
    input wire instr_valid,
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
    input wire interrupt_to_supervisor,
    input wire [31:0] mtvec,
    input wire [31:0] mepc,
    input wire [31:0] stvec,
    input wire [31:0] sepc,
    input wire [31:0] medeleg,
    input wire [1:0] privilege_mode,
    input wire [31:0] mstatus,
    input wire [31:0] mcounteren,
    input wire [31:0] scounteren,
    
    // Add interrupt/exception outputs
    output reg interrupt_taken,
    output reg mret_instruction,
    output reg sret_instruction,
    output reg trap_to_supervisor,
    output reg ecall_exception,
    output reg ebreak_exception,
    output reg illegal_instruction_exception,
    output reg instruction_address_misaligned_exception,
    output reg load_address_misaligned_exception,
    output reg store_address_misaligned_exception,
    output reg [31:0] exception_tval,
    output reg wfi_instruction
);

// Internal signals for forwarded values
reg [31:0] rs1_value;
reg [31:0] rs2_value;
reg [31:0] effective_addr;
reg [31:0] target_addr;

assign rs1_value_out = rs1_value;
assign rs2_value_out = rs2_value;

// Forwarding control values (must match forwarding_unit.v)
localparam NO_FORWARDING = 2'b00;
localparam FORWARD_FROM_MEM = 2'b01;
localparam FORWARD_FROM_WB = 2'b10;
localparam PRIV_U = 2'b00;
localparam PRIV_S = 2'b01;
localparam PRIV_M = 2'b11;
localparam CSR_SATP = 12'h180;
localparam CSR_CYCLE = 12'hC00;
localparam CSR_TIME = 12'hC01;
localparam CSR_INSTRET = 12'hC02;
localparam CSR_CYCLEH = 12'hC80;
localparam CSR_TIMEH = 12'hC81;
localparam CSR_INSTRETH = 12'hC82;

function is_counter_shadow_csr;
    input [11:0] csr_addr_in;
    begin
        is_counter_shadow_csr = (csr_addr_in == CSR_CYCLE) ||
                                (csr_addr_in == CSR_TIME) ||
                                (csr_addr_in == CSR_INSTRET) ||
                                (csr_addr_in == CSR_CYCLEH) ||
                                (csr_addr_in == CSR_TIMEH) ||
                                (csr_addr_in == CSR_INSTRETH);
    end
endfunction

function load_address_misaligned;
    input [6:0] load_instr_id;
    input [31:0] addr;
    begin
        case (load_instr_id)
            INSTR_LH, INSTR_LHU: load_address_misaligned = addr[0];
            INSTR_LW, INSTR_LR_W: load_address_misaligned = (addr[1:0] != 2'b00);
            default: load_address_misaligned = 1'b0;
        endcase
    end
endfunction

function store_address_misaligned;
    input [6:0] store_instr_id;
    input [31:0] addr;
    begin
        case (store_instr_id)
            INSTR_SH: store_address_misaligned = addr[0];
            INSTR_SW, INSTR_SC_W, INSTR_AMOSWAP_W, INSTR_AMOADD_W,
            INSTR_AMOAND_W, INSTR_AMOOR_W, INSTR_AMOXOR_W,
            INSTR_AMOMAX_W, INSTR_AMOMIN_W, INSTR_AMOMAXU_W,
            INSTR_AMOMINU_W: store_address_misaligned = (addr[1:0] != 2'b00);
            default: store_address_misaligned = 1'b0;
        endcase
    end
endfunction

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

wire csr_read_only_violation = (csr_addr[11:10] == 2'b11) && csr_write_enable;
wire csr_privilege_violation = (privilege_mode < csr_addr[9:8]);
wire csr_satp_tvm_violation = (csr_addr == CSR_SATP) && (privilege_mode == PRIV_S) && mstatus[20];
wire sret_tsr_violation = (privilege_mode == PRIV_S) && mstatus[22];
wire wfi_tw_violation = (privilege_mode != PRIV_M) && mstatus[21];
wire csr_is_counter_shadow = is_counter_shadow_csr(csr_addr);
wire csr_is_cycle_shadow = (csr_addr == CSR_CYCLE) || (csr_addr == CSR_CYCLEH);
wire csr_is_time_shadow = (csr_addr == CSR_TIME) || (csr_addr == CSR_TIMEH);
wire mcounteren_allows_counter = csr_is_cycle_shadow ? mcounteren[0] :
                                 csr_is_time_shadow ? mcounteren[1] :
                                                      mcounteren[2];
wire scounteren_allows_counter = csr_is_cycle_shadow ? scounteren[0] :
                                 csr_is_time_shadow ? scounteren[1] :
                                                      scounteren[2];
wire csr_counter_access_violation =
    csr_is_counter_shadow &&
    ((privilege_mode == PRIV_S && !mcounteren_allows_counter) ||
     (privilege_mode == PRIV_U &&
      (!mcounteren_allows_counter || !scounteren_allows_counter)));
wire delegate_instr_addr_misaligned = (privilege_mode != PRIV_M) && medeleg[0];
wire delegate_illegal_instruction = (privilege_mode != PRIV_M) && medeleg[2];
wire delegate_breakpoint = (privilege_mode != PRIV_M) && medeleg[3];
wire delegate_load_addr_misaligned = (privilege_mode != PRIV_M) && medeleg[4];
wire delegate_store_addr_misaligned = (privilege_mode != PRIV_M) && medeleg[6];
wire delegate_ecall = ((privilege_mode == PRIV_U) && medeleg[8]) ||
                      ((privilege_mode == PRIV_S) && medeleg[9]);

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
    sret_instruction = 0;
    trap_to_supervisor = 0;
    ecall_exception = 0;
    ebreak_exception = 0;
    illegal_instruction_exception = 0;
    instruction_address_misaligned_exception = 0;
    load_address_misaligned_exception = 0;
    store_address_misaligned_exception = 0;
    exception_tval = 0;
    wfi_instruction = 0;
    effective_addr = 0;
    target_addr = 0;
    
    // Handle interrupts first (highest priority)
    if (interrupt_pending) begin
        jump_signal = 1;
        trap_to_supervisor = interrupt_to_supervisor;
        jump_addr = interrupt_to_supervisor ? stvec : mtvec;  // Jump to interrupt handler
        flush_pipeline = 1;
        interrupt_taken = 1;
    end else if (instr_valid && instr_id == INSTR_INVALID) begin
        jump_signal = 1;
        trap_to_supervisor = delegate_illegal_instruction;
        jump_addr = trap_to_supervisor ? stvec : mtvec;
        flush_pipeline = 1;
        illegal_instruction_exception = 1;
    end else begin
        case (opcode)
            7'b0110011: begin // R-type instructions
            exec_output = alu_inst.ALUoutput;
            end
            7'b0010011: begin // I-type instructions
            exec_output = alu_inst.ALUoutput;
            end
            7'b0000011: begin // Load instructions
            effective_addr = rs1_value + imm;
            mem_addr = effective_addr;
            if (load_address_misaligned(instr_id, effective_addr)) begin
                jump_signal = 1;
                trap_to_supervisor = delegate_load_addr_misaligned;
                jump_addr = trap_to_supervisor ? stvec : mtvec;
                flush_pipeline = 1;
                load_address_misaligned_exception = 1;
                exception_tval = effective_addr;
            end
            end
            7'b0100011: begin // Store instructions
            effective_addr = rs1_value + imm;
            mem_addr = effective_addr;
            if (store_address_misaligned(instr_id, effective_addr)) begin
                jump_signal = 1;
                trap_to_supervisor = delegate_store_addr_misaligned;
                jump_addr = trap_to_supervisor ? stvec : mtvec;
                flush_pipeline = 1;
                store_address_misaligned_exception = 1;
                exception_tval = effective_addr;
            end
            end
            7'b0101111: begin // AMO/LR/SC instructions
            effective_addr = rs1_value;
            mem_addr = effective_addr;
            if (load_address_misaligned(instr_id, effective_addr)) begin
                jump_signal = 1;
                trap_to_supervisor = delegate_load_addr_misaligned;
                jump_addr = trap_to_supervisor ? stvec : mtvec;
                flush_pipeline = 1;
                load_address_misaligned_exception = 1;
                exception_tval = effective_addr;
            end else if (store_address_misaligned(instr_id, effective_addr)) begin
                jump_signal = 1;
                trap_to_supervisor = delegate_store_addr_misaligned;
                jump_addr = trap_to_supervisor ? stvec : mtvec;
                flush_pipeline = 1;
                store_address_misaligned_exception = 1;
                exception_tval = effective_addr;
            end
            end
            7'b1100011: begin // Branch instructions
            case (instr_id)
                INSTR_BEQ: begin
                    if (rs1_value == rs2_value) begin
                        target_addr = pc_input + imm;
                        jump_signal = 1;
                        jump_addr = (target_addr[1:0] != 2'b00) ? mtvec : target_addr;
                        flush_pipeline = 1;
                        if (target_addr[1:0] != 2'b00) begin
                            trap_to_supervisor = delegate_instr_addr_misaligned;
                            jump_addr = trap_to_supervisor ? stvec : mtvec;
                            instruction_address_misaligned_exception = 1;
                            exception_tval = target_addr;
                        end
                    end
                end
                INSTR_BNE: begin
                    if (rs1_value != rs2_value) begin
                        target_addr = pc_input + imm;
                        jump_signal = 1;
                        jump_addr = target_addr;
                        flush_pipeline = 1;
                        if (target_addr[1:0] != 2'b00) begin
                            trap_to_supervisor = delegate_instr_addr_misaligned;
                            jump_addr = trap_to_supervisor ? stvec : mtvec;
                            instruction_address_misaligned_exception = 1;
                            exception_tval = target_addr;
                        end
                    end
                end
                INSTR_BLT: begin
                    if ($signed(rs1_value) < $signed(rs2_value)) begin
                        target_addr = pc_input + imm;
                        jump_signal = 1;
                        jump_addr = target_addr;
                        flush_pipeline = 1;
                        if (target_addr[1:0] != 2'b00) begin
                            trap_to_supervisor = delegate_instr_addr_misaligned;
                            jump_addr = trap_to_supervisor ? stvec : mtvec;
                            instruction_address_misaligned_exception = 1;
                            exception_tval = target_addr;
                        end
                    end
                end
                INSTR_BGE: begin
                    if ($signed(rs1_value) >= $signed(rs2_value)) begin
                        target_addr = pc_input + imm;
                        jump_signal = 1;
                        jump_addr = target_addr;
                        flush_pipeline = 1;
                        if (target_addr[1:0] != 2'b00) begin
                            trap_to_supervisor = delegate_instr_addr_misaligned;
                            jump_addr = trap_to_supervisor ? stvec : mtvec;
                            instruction_address_misaligned_exception = 1;
                            exception_tval = target_addr;
                        end
                    end
                end
                INSTR_BLTU: begin
                    if (rs1_value < rs2_value) begin
                        target_addr = pc_input + imm;
                        jump_signal = 1;
                        jump_addr = target_addr;
                        flush_pipeline = 1;
                        if (target_addr[1:0] != 2'b00) begin
                            trap_to_supervisor = delegate_instr_addr_misaligned;
                            jump_addr = trap_to_supervisor ? stvec : mtvec;
                            instruction_address_misaligned_exception = 1;
                            exception_tval = target_addr;
                        end
                    end
                end
                INSTR_BGEU: begin
                    if (rs1_value >= rs2_value) begin
                        target_addr = pc_input + imm;
                        jump_signal = 1;
                        jump_addr = target_addr;
                        flush_pipeline = 1;
                        if (target_addr[1:0] != 2'b00) begin
                            trap_to_supervisor = delegate_instr_addr_misaligned;
                            jump_addr = trap_to_supervisor ? stvec : mtvec;
                            instruction_address_misaligned_exception = 1;
                            exception_tval = target_addr;
                        end
                    end
                end
                default: begin
                end
            endcase
            end
            7'b1101111: begin // JAL
            target_addr = pc_input + imm;
            jump_signal = 1;
            jump_addr = target_addr;
            exec_output = pc_input + 4;
            flush_pipeline = 1;
            if (target_addr[1:0] != 2'b00) begin
                trap_to_supervisor = delegate_instr_addr_misaligned;
                jump_addr = trap_to_supervisor ? stvec : mtvec;
                instruction_address_misaligned_exception = 1;
                exception_tval = target_addr;
            end
            end
            7'b1100111: begin // JALR
            target_addr = (rs1_value + imm) & 32'hFFFFFFFE;
            jump_signal = 1;
            jump_addr = target_addr;
            exec_output = pc_input + 4;
            flush_pipeline = 1;
            if (target_addr[1:0] != 2'b00) begin
                trap_to_supervisor = delegate_instr_addr_misaligned;
                jump_addr = trap_to_supervisor ? stvec : mtvec;
                instruction_address_misaligned_exception = 1;
                exception_tval = target_addr;
            end
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
                    if (privilege_mode != PRIV_M) begin
                        jump_signal = 1;
                        trap_to_supervisor = delegate_illegal_instruction;
                        jump_addr = trap_to_supervisor ? stvec : mtvec;
                        flush_pipeline = 1;
                        illegal_instruction_exception = 1;
                    end else begin
                        jump_signal = 1;
                        jump_addr = mepc;  // Return from interrupt
                        flush_pipeline = 1;
                        mret_instruction = 1;
                    end
                end
                INSTR_SRET: begin
                    if ((privilege_mode != PRIV_S) || sret_tsr_violation) begin
                        jump_signal = 1;
                        trap_to_supervisor = delegate_illegal_instruction;
                        jump_addr = trap_to_supervisor ? stvec : mtvec;
                        flush_pipeline = 1;
                        illegal_instruction_exception = 1;
                    end else begin
                        jump_signal = 1;
                        jump_addr = sepc;  // Return from supervisor trap
                        flush_pipeline = 1;
                        sret_instruction = 1;
                    end
                end
                INSTR_ECALL: begin
                    jump_signal = 1;
                    trap_to_supervisor = delegate_ecall;
                    jump_addr = trap_to_supervisor ? stvec : mtvec;  // Jump to trap handler
                    flush_pipeline = 1;
                    ecall_exception = 1;
                end
                INSTR_EBREAK: begin
                    jump_signal = 1;
                    trap_to_supervisor = delegate_breakpoint;
                    jump_addr = trap_to_supervisor ? stvec : mtvec;  // Jump to trap handler
                    flush_pipeline = 1;
                    ebreak_exception = 1;
                end
                INSTR_WFI: begin
                    if (wfi_tw_violation) begin
                        jump_signal = 1;
                        trap_to_supervisor = delegate_illegal_instruction;
                        jump_addr = trap_to_supervisor ? stvec : mtvec;
                        flush_pipeline = 1;
                        illegal_instruction_exception = 1;
                    end else begin
                        // WFI may resume for any reason. The CPU models it as a
                        // short sleep so pending interrupts still win over the
                        // post-WFI path without risking an indefinite ISA-test hang.
                        jump_signal = 1;
                        jump_addr = pc_input + 4;
                        flush_pipeline = 1;
                        wfi_instruction = 1;
                    end
                end
                INSTR_SFENCE_VMA: begin
                    if ((privilege_mode == PRIV_U) || ((privilege_mode == PRIV_S) && mstatus[20])) begin
                        jump_signal = 1;
                        trap_to_supervisor = delegate_illegal_instruction;
                        jump_addr = trap_to_supervisor ? stvec : mtvec;
                        flush_pipeline = 1;
                        illegal_instruction_exception = 1;
                    end
                end
                default: begin
                    if (csr_valid && (csr_read_only_violation ||
                         csr_privilege_violation || csr_satp_tvm_violation ||
                         csr_counter_access_violation)) begin
                        jump_signal = 1;
                        trap_to_supervisor = delegate_illegal_instruction;
                        jump_addr = trap_to_supervisor ? stvec : mtvec;
                        flush_pipeline = 1;
                        illegal_instruction_exception = 1;
                    end else begin
                        exec_output = csr_rd_value;
                        if (csr_write_enable) begin
                            jump_signal = 1;
                            jump_addr = pc_input + 4;
                            flush_pipeline = 1;
                        end
                    end
                end
            endcase
            end
            7'b0001111: begin // MISC-MEM (fence instructions)
            if (instr_id == INSTR_FENCE_I) begin
                // Serialize instruction stream: squash younger instructions and
                // refetch from the next sequential PC.
                jump_signal = 1;
                jump_addr = pc_input + 4;
                flush_pipeline = 1;
            end
            end
            default: begin
            end
        endcase
    end
end

endmodule
