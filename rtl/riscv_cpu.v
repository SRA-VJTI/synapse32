`default_nettype none
`include "memory_map.vh"
module riscv_cpu (
    input wire clk,
    input wire rst,
    input wire [31:0] module_instr_in,
    input wire [31:0] module_read_data_in,
    output wire [31:0] module_pc_out,
    output wire [31:0] module_wr_data_out,
    output wire module_mem_wr_en,
    output wire module_mem_rd_en,
    output wire [31:0] module_read_addr,
    output wire [31:0] module_write_addr,
    output wire [3:0] module_write_byte_enable,  // Write byte enables
    output wire [2:0] module_load_type,          // Load type

    // Interrupt inputs
    input wire timer_interrupt,
    input wire software_interrupt,
    input wire external_interrupt
);

    // Instantiate PC
    wire [31:0] pc_inst0_out;
    wire pc_inst0_j_signal;
    wire [31:0] pc_inst0_jump;
    wire hazard_stall; // For load-use hazards
    wire pipeline_stall;
    // Branch handling: use EX stage jump signal/address
    assign pc_inst0_j_signal = ex_inst0_jump_signal_out;
    assign pc_inst0_jump = ex_inst0_jump_addr_out;
    pc pc_inst0 (
        .clk(clk),
        .rst(rst),
        .j_signal(pc_inst0_j_signal),
        .jump(pc_inst0_jump),
        .stall(pipeline_stall), // Stall on hazard or WFI sleep
        .out(pc_inst0_out)
    );

    // Send out the PC value
    assign module_pc_out = pc_inst0_out;


    // Instantiate IF_ID pipeline register
    wire [31:0] if_id_pc_out;
    wire [31:0] if_id_instr_out;
    wire if_id_instr_valid_out;
    wire execution_flush;
    wire branch_flush;
    wire if_id_flush;
    assign branch_flush = ex_inst0_jump_signal_out; // Flush IF/ID if branch taken
    assign if_id_flush = branch_flush || execution_flush;
    // If branch taken, flush IF/ID by setting instruction to 0 (NOP)
    IF_ID if_id_inst0 (
        .clk(clk),
        .rst(rst),
        .pc_in(pc_inst0_out),
        .instruction_in(if_id_flush ? 32'h13 : module_instr_in),
        // Flush must win over stall, otherwise a stale IF/ID instruction can
        // survive an interrupt/branch redirect and execute one cycle later.
        .stall(pipeline_stall && !if_id_flush),
        .pc_out(if_id_pc_out),
        .instruction_out(if_id_instr_out),
        .instruction_valid_out(if_id_instr_valid_out)
    );

    // Instantiate Decoder
    wire [4:0] decoder_inst0_rs1_out;
    wire [4:0] decoder_inst0_rs2_out;
    wire [4:0] decoder_inst0_rd_out;
    wire [31:0] decoder_inst0_imm_out;
    wire decoder_inst0_rs1_valid_out;
    wire decoder_inst0_rs2_valid_out;
    wire decoder_inst0_rd_valid_out;
    wire [6:0] decoder_inst0_opcode_out;
    wire [6:0] decoder_inst0_instr_id_out;

    decoder decoder_inst0 (
        .instr(if_id_instr_out),
        .rs2(decoder_inst0_rs2_out),
        .rs1(decoder_inst0_rs1_out),
        .imm(decoder_inst0_imm_out),
        .rd(decoder_inst0_rd_out),
        .rs1_valid(decoder_inst0_rs1_valid_out),
        .rs2_valid(decoder_inst0_rs2_valid_out),
        .rd_valid(decoder_inst0_rd_valid_out),
        .opcode(decoder_inst0_opcode_out),
        .instr_id(decoder_inst0_instr_id_out)
    );
    
    // Instantiate Load-Use Hazard Detector
    load_use_detector load_use_detector_inst0 (
        .rs1_id(decoder_inst0_rs1_out),
        .rs2_id(decoder_inst0_rs2_out),
        .rs1_valid_id(decoder_inst0_rs1_valid_out),
        .rs2_valid_id(decoder_inst0_rs2_valid_out),
        .instr_id_ex(id_ex_inst0_instr_id_out),
        .rd_ex(id_ex_inst0_rd_addr_out),
        .rd_valid_ex(id_ex_inst0_rd_valid_out),
        .stall_pipeline(hazard_stall)
    );

    // Instantiate Register File
    wire [31:0] rf_inst0_rs1_value_out;
    wire [31:0] rf_inst0_rs2_value_out;
    // RD control signals will be later handled by WB stage
    wire [4:0] rf_inst0_rd_in;
    wire rf_inst0_wr_en;
    wire [31:0] rf_inst0_rd_value_in;


    registerfile rf_inst0 (
        .clk(clk),
        .rst(rst),
        .rs1(decoder_inst0_rs1_out),
        .rs2(decoder_inst0_rs2_out),
        .rs1_valid(decoder_inst0_rs1_valid_out),
        .rs2_valid(decoder_inst0_rs2_valid_out),
        .rd(rf_inst0_rd_in),
        .wr_en(rf_inst0_wr_en),
        .rd_value(rf_inst0_rd_value_in),
        .rs1_value(rf_inst0_rs1_value_out),
        .rs2_value(rf_inst0_rs2_value_out)
    );

    // Instantiate ID_EX pipeline register
    wire id_ex_inst0_rs1_valid_out;
    wire id_ex_inst0_rs2_valid_out;
    wire id_ex_inst0_rd_valid_out;
    wire [31:0] id_ex_inst0_imm_out;
    wire [4:0] id_ex_inst0_rs1_addr_out;
    wire [4:0] id_ex_inst0_rs2_addr_out;
    wire [4:0] id_ex_inst0_rd_addr_out;
    wire [6:0] id_ex_inst0_opcode_out;
    wire [6:0] id_ex_inst0_instr_id_out;
    wire [31:0] id_ex_inst0_pc_out;
    wire [31:0] id_ex_inst0_rs1_value_out;
    wire [31:0] id_ex_inst0_rs2_value_out;
    wire id_ex_inst0_instr_valid_out;

    // Pipeline flush signals
    wire pipeline_flush;
    
    // Combine branch flush and execution unit flush
    assign pipeline_flush = branch_flush || execution_flush;

    ID_EX id_ex_inst0 (
        .clk(clk),
        .rst(rst),
        .rs1_valid_in(decoder_inst0_rs1_valid_out),
        .rs2_valid_in(decoder_inst0_rs2_valid_out),
        .rd_valid_in(decoder_inst0_rd_valid_out),
        .imm_in(decoder_inst0_imm_out),
        .rs1_addr_in(decoder_inst0_rs1_out),
        .rs2_addr_in(decoder_inst0_rs2_out),
        .rd_addr_in(decoder_inst0_rd_out),
        .opcode_in(decoder_inst0_opcode_out),
        .instr_id_in(decoder_inst0_instr_id_out),
        .pc_in(if_id_pc_out),
        .rs1_value_in(rf_inst0_rs1_value_out),
        .rs2_value_in(rf_inst0_rs2_value_out),
        .instr_valid_in(if_id_instr_valid_out),
        .stall(pipeline_flush || pipeline_stall), // Use combined flush and stalls
        .rs1_valid_out(id_ex_inst0_rs1_valid_out),
        .rs2_valid_out(id_ex_inst0_rs2_valid_out),
        .rd_valid_out(id_ex_inst0_rd_valid_out),
        .imm_out(id_ex_inst0_imm_out),
        .rs1_addr_out(id_ex_inst0_rs1_addr_out),
        .rs2_addr_out(id_ex_inst0_rs2_addr_out),
        .rd_addr_out(id_ex_inst0_rd_addr_out),
        .opcode_out(id_ex_inst0_opcode_out),
        .instr_id_out(id_ex_inst0_instr_id_out),
        .pc_out(id_ex_inst0_pc_out),
        .rs1_value_out(id_ex_inst0_rs1_value_out),
        .rs2_value_out(id_ex_inst0_rs2_value_out),
        .instr_valid_out(id_ex_inst0_instr_valid_out)
    );

    // Instantiate Execution Unit
    wire [31:0] ex_inst0_exec_output_out;
    wire ex_inst0_jump_signal_out;
    wire [31:0] ex_inst0_jump_addr_out;
    wire [31:0] ex_inst0_mem_addr_out;
    wire [31:0] ex_inst0_rs1_value_out;
    wire [31:0] ex_inst0_rs2_value_out;
    
    // Forwarding unit signals
    wire [1:0] forward_a;
    wire [1:0] forward_b;
    
    // Instantiate forwarding unit
    forwarding_unit forwarding_unit_inst0 (
        .rs1_addr_ex(id_ex_inst0_rs1_addr_out),
        .rs2_addr_ex(id_ex_inst0_rs2_addr_out),
        .rs1_valid_ex(id_ex_inst0_rs1_valid_out),
        .rs2_valid_ex(id_ex_inst0_rs2_valid_out),
        .rd_addr_mem(ex_mem_inst0_rd_addr_out),
        .rd_valid_mem(ex_mem_inst0_rd_valid_out),
        .instr_id_mem(ex_mem_inst0_instr_id_out),
        .rd_addr_wb(mem_wb_inst0_rd_addr_out),
        .rd_valid_wb(mem_wb_inst0_rd_valid_out),
        .wr_en_wb(wb_inst0_wr_en_out),
        .forward_a(forward_a),
        .forward_b(forward_b)
    );

    // CSR file signals
    wire [11:0] csr_addr;
    wire [31:0] csr_read_data;
    wire [31:0] csr_write_data;
    wire csr_write_enable;
    wire csr_read_enable;
    wire csr_valid;

    // Interrupt controller signals
    wire interrupt_pending;
    wire [31:0] interrupt_cause;
    wire [31:0] interrupt_pc;
    wire interrupt_taken;
    wire interrupt_to_supervisor;
    wire mret_instruction;
    wire sret_instruction;
    wire trap_to_supervisor;
    wire ecall_exception;
    wire ebreak_exception;
    wire illegal_instruction_exception;
    wire instruction_address_misaligned_exception;
    wire load_address_misaligned_exception;
    wire store_address_misaligned_exception;
    wire [31:0] exception_tval;
    wire synchronous_exception_taken;
    wire wfi_instruction;
    wire [31:0] exception_pc;
    assign exception_pc = id_ex_inst0_pc_out - 32'd4;
    assign synchronous_exception_taken = ecall_exception || ebreak_exception ||
                                         illegal_instruction_exception ||
                                         instruction_address_misaligned_exception ||
                                         load_address_misaligned_exception ||
                                         store_address_misaligned_exception;

    // WFI sleep state: stall fetch/decode until an interrupt becomes pending.
    reg wfi_active;
    wire wfi_stall;
    assign wfi_stall = wfi_active && !interrupt_pending;

    // One-entry store buffer (for future decoupled memory interfaces).
    reg store_buf_valid;
    reg [31:0] store_buf_addr;
    reg [31:0] store_buf_data;
    reg [3:0] store_buf_be;
    wire ex_mem_std_store_raw_req;
    wire ex_mem_std_store_req;
    wire ex_mem_std_store_direct_req;
    wire [31:0] ex_mem_store_addr;
    wire [31:0] ex_mem_store_data;
    wire [3:0] ex_mem_store_be;
    wire ex_mem_read_req;
    wire [31:0] ex_mem_read_addr;
    wire [2:0] ex_mem_read_type;
    wire non_atomic_store_write_enable;
    wire [31:0] non_atomic_store_write_addr;
    reg [31:0] mem_read_data_effective;
    wire load_all_bytes_covered;
    wire read_needs_memory;
    wire store_buf_commit_fire;
    wire atomic_clobbers_store_buf;

    // Atomic LSU signals (produced by atomic_lsu module in MEM stage).
    wire is_lr_w;
    wire is_sc_w;
    wire is_amo_w;
    wire atomic_read_enable;
    wire atomic_write_enable;
    wire sc_success;
    wire [31:0] sc_result;
    wire [31:0] atomic_new_word;
    assign pipeline_stall = hazard_stall || wfi_stall;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            wfi_active <= 1'b0;
            store_buf_valid <= 1'b0;
            store_buf_addr <= 32'b0;
            store_buf_data <= 32'b0;
            store_buf_be <= 4'b0;
        end else begin
            if (interrupt_pending) begin
                wfi_active <= 1'b0;
            end else if (wfi_active) begin
                wfi_active <= 1'b0;
            end else if (wfi_instruction) begin
                wfi_active <= 1'b1;
            end

            // One-entry store buffer update.
            // If a store is committed and no new store is entering, clear valid.
            // If a new store enters, capture it (and replace any just-committed entry).
            if (ex_mem_std_store_req) begin
                store_buf_valid <= 1'b1;
                store_buf_addr <= ex_mem_store_addr;
                store_buf_data <= ex_mem_store_data;
                store_buf_be <= ex_mem_store_be;
            end else if (atomic_clobbers_store_buf) begin
                // Older store to the same word is architecturally consumed by the
                // AMO/SC full-word write and must not commit afterward.
                store_buf_valid <= 1'b0;
            end else if (store_buf_commit_fire) begin
                store_buf_valid <= 1'b0;
            end
        end
    end

    // Instantiate interrupt controller
    interrupt_controller int_ctrl_inst (
        .clk(clk),
        .rst(rst),
        .timer_interrupt(timer_interrupt),
        .software_interrupt(software_interrupt),
        .external_interrupt(external_interrupt),
        .mstatus(csr_file_inst.mstatus),
        .mie(csr_file_inst.mie),
        .mip(csr_file_inst.mip),
        .mideleg(csr_file_inst.mideleg),
        .privilege_mode(csr_file_inst.privilege_mode),
        .interrupt_pending(interrupt_pending),
        .interrupt_cause(interrupt_cause),
        .interrupt_to_supervisor(interrupt_to_supervisor),
        .interrupt_taken(interrupt_taken),
        .current_pc(pc_inst0_out),
        .interrupt_pc(interrupt_pc)
    );

    // Instantiate CSR file at CPU level
    csr_file csr_file_inst (
        .clk(clk),
        .rst(rst),
        .csr_addr(csr_addr),
        .write_data(csr_write_data),
        .write_enable(csr_write_enable),
        .read_enable(csr_read_enable),
        .read_data(csr_read_data),
        .csr_valid(csr_valid),
        .interrupt_pending(interrupt_pending),
        .interrupt_cause_in(interrupt_cause),
        .interrupt_pc_in(interrupt_pc),
        .exception_pc_in(exception_pc),
        .interrupt_taken(interrupt_taken),
        .mret_instruction(mret_instruction),
        .sret_instruction(sret_instruction),
        .interrupt_to_supervisor(interrupt_to_supervisor),
        .trap_to_supervisor(trap_to_supervisor),
        .ecall_exception(ecall_exception),
        .ebreak_exception(ebreak_exception),
        .illegal_instruction_exception(illegal_instruction_exception),
        .instruction_address_misaligned_exception(instruction_address_misaligned_exception),
        .load_address_misaligned_exception(load_address_misaligned_exception),
        .store_address_misaligned_exception(store_address_misaligned_exception),
        .exception_tval_in(exception_tval),
        .timer_interrupt(timer_interrupt),
        .software_interrupt(software_interrupt),
        .external_interrupt(external_interrupt)
    );

    // Value available for EX-stage forwarding from MEM stage.
    // SC computes its architectural result in MEM, so forward that instead of
    // the raw EX result for dependent instructions.
    wire [31:0] ex_mem_forward_result = is_sc_w ? sc_result : ex_mem_inst0_exec_output_out;

    execution_unit ex_unit_inst0 (
        .rs1(id_ex_inst0_rs1_value_out),
        .rs2(id_ex_inst0_rs2_value_out),
        .imm(id_ex_inst0_imm_out),
        .rs1_addr(id_ex_inst0_rs1_addr_out),
        .rs2_addr(id_ex_inst0_rs2_addr_out),
        .opcode(id_ex_inst0_opcode_out),
        .instr_id(id_ex_inst0_instr_id_out),
        .rs1_valid(id_ex_inst0_rs1_valid_out),
        .rs2_valid(id_ex_inst0_rs2_valid_out),
        .instr_valid(id_ex_inst0_instr_valid_out),
        .pc_input(id_ex_inst0_pc_out),
        .forward_a(forward_a),
        .forward_b(forward_b),
        .ex_mem_result(ex_mem_forward_result),
        .mem_wb_result(wb_inst0_rd_value_out),
        
        // CSR interface connections
        .csr_read_data(csr_read_data),
        .csr_valid(csr_valid),
        .csr_addr(csr_addr),
        .csr_read_enable(csr_read_enable),
        .csr_write_data(csr_write_data),
        .csr_write_enable(csr_write_enable),
        
        .exec_output(ex_inst0_exec_output_out),
        .jump_signal(ex_inst0_jump_signal_out),
        .jump_addr(ex_inst0_jump_addr_out),
        .mem_addr(ex_inst0_mem_addr_out),
        .rs1_value_out(ex_inst0_rs1_value_out),
        .rs2_value_out(ex_inst0_rs2_value_out),
        .flush_pipeline(execution_flush),

        // Interrupt connections
        .interrupt_pending(interrupt_pending),
        .interrupt_cause(interrupt_cause),
        .interrupt_to_supervisor(interrupt_to_supervisor),
        .mtvec(csr_file_inst.mtvec),
        .mepc(csr_file_inst.mepc),
        .stvec(csr_file_inst.stvec),
        .sepc(csr_file_inst.sepc),
        .medeleg(csr_file_inst.medeleg),
        .privilege_mode(csr_file_inst.privilege_mode),
        .interrupt_taken(interrupt_taken),
        .mret_instruction(mret_instruction),
        .sret_instruction(sret_instruction),
        .trap_to_supervisor(trap_to_supervisor),
        .ecall_exception(ecall_exception),
        .ebreak_exception(ebreak_exception),
        .illegal_instruction_exception(illegal_instruction_exception),
        .instruction_address_misaligned_exception(instruction_address_misaligned_exception),
        .load_address_misaligned_exception(load_address_misaligned_exception),
        .store_address_misaligned_exception(store_address_misaligned_exception),
        .exception_tval(exception_tval),
        .wfi_instruction(wfi_instruction)
    );

    // Memory Stage

    // Instantiate EX_MEM pipeline register
    wire [4:0] ex_mem_inst0_rs1_addr_out;
    wire [4:0] ex_mem_inst0_rs2_addr_out;
    wire [4:0] ex_mem_inst0_rd_addr_out;
    wire [31:0] ex_mem_inst0_rs1_value_out;
    wire [31:0] ex_mem_inst0_rs2_value_out;
    wire [31:0] ex_mem_inst0_pc_out;
    wire [31:0] ex_mem_inst0_mem_addr_out;
    wire [31:0] ex_mem_inst0_exec_output_out;
    wire ex_mem_inst0_jump_signal_out;
    wire [31:0] ex_mem_inst0_jump_addr_out;
    wire [6:0] ex_mem_inst0_instr_id_out;
    wire ex_mem_inst0_rd_valid_out;

    EX_MEM ex_mem_inst0 (
        .clk(clk),
        .rst(rst),
        .rs1_addr_in(id_ex_inst0_rs1_addr_out),
        .rs2_addr_in(id_ex_inst0_rs2_addr_out),
        .rd_addr_in(id_ex_inst0_rd_addr_out),
        .rs1_value_in(ex_inst0_rs1_value_out),
        .rs2_value_in(ex_inst0_rs2_value_out),
        .pc_in(id_ex_inst0_pc_out),
        .mem_addr_in(ex_inst0_mem_addr_out),
        .exec_output_in(ex_inst0_exec_output_out),
        .jump_signal_in(ex_inst0_jump_signal_out),
        .jump_addr_in(ex_inst0_jump_addr_out),
        .instr_id_in(synchronous_exception_taken ? 7'b0000000 : id_ex_inst0_instr_id_out),
        .rd_valid_in(synchronous_exception_taken ? 1'b0 : id_ex_inst0_rd_valid_out),
        .rs1_addr_out(ex_mem_inst0_rs1_addr_out),
        .rs2_addr_out(ex_mem_inst0_rs2_addr_out),
        .rd_addr_out(ex_mem_inst0_rd_addr_out),
        .rs1_value_out(ex_mem_inst0_rs1_value_out),
        .rs2_value_out(ex_mem_inst0_rs2_value_out),
        .pc_out(ex_mem_inst0_pc_out),
        .mem_addr_out(ex_mem_inst0_mem_addr_out),
        .exec_output_out(ex_mem_inst0_exec_output_out),
        .jump_signal_out(ex_mem_inst0_jump_signal_out),
        .jump_addr_out(ex_mem_inst0_jump_addr_out),
        .instr_id_out(ex_mem_inst0_instr_id_out),
        .rd_valid_out(ex_mem_inst0_rd_valid_out)
    );

    // Instantiate Memory Unit
    wire mem_unit_inst0_wr_enable_out;
    wire mem_unit_inst0_read_enable_out;
    wire [31:0] mem_unit_inst0_wr_data_out;
    wire [31:0] mem_unit_inst0_read_addr_out;
    wire [31:0] mem_unit_inst0_wr_addr_out;
    wire [3:0] mem_unit_inst0_write_byte_enable_out;  // Write byte enables
    wire [2:0] mem_unit_inst0_load_type_out;          // Load type

    memory_unit mem_unit_inst0 (
        .instr_id(ex_mem_inst0_instr_id_out),
        .rs2_value(ex_mem_inst0_rs2_value_out),
        .mem_addr(ex_mem_inst0_mem_addr_out),
        .wr_enable(mem_unit_inst0_wr_enable_out),
        .read_enable(mem_unit_inst0_read_enable_out),
        .wr_data(mem_unit_inst0_wr_data_out),
        .read_addr(mem_unit_inst0_read_addr_out),
        .wr_addr(mem_unit_inst0_wr_addr_out),
        .write_byte_enable(mem_unit_inst0_write_byte_enable_out),
        .load_type(mem_unit_inst0_load_type_out)
    );

    atomic_lsu atomic_lsu_inst0 (
        .clk(clk),
        .rst(rst),
        .instr_id_mem(ex_mem_inst0_instr_id_out),
        .mem_addr_mem(ex_mem_inst0_mem_addr_out),
        .rs2_value_mem(ex_mem_inst0_rs2_value_out),
        .mem_read_data(mem_read_data_effective),
        .non_atomic_store_write_enable(non_atomic_store_write_enable),
        .non_atomic_store_write_addr(non_atomic_store_write_addr),
        .is_lr_w(is_lr_w),
        .is_sc_w(is_sc_w),
        .is_amo_w(is_amo_w),
        .atomic_read_enable(atomic_read_enable),
        .atomic_write_enable(atomic_write_enable),
        .sc_success(sc_success),
        .sc_result(sc_result),
        .atomic_new_word(atomic_new_word)
    );

    // Store request generated in EX/MEM for SB/SH/SW.
    // Only data-memory stores are buffered. Instruction-memory stores stay
    // direct so self-modifying code + fence.i sees promptly visible writes.
    assign ex_mem_std_store_raw_req = mem_unit_inst0_wr_enable_out &&
                                      (mem_unit_inst0_write_byte_enable_out != 4'b0000);
    assign ex_mem_store_addr = mem_unit_inst0_wr_addr_out;
    assign ex_mem_store_data = mem_unit_inst0_wr_data_out;
    assign ex_mem_store_be = mem_unit_inst0_write_byte_enable_out;
    assign ex_mem_std_store_req = ex_mem_std_store_raw_req &&
                                  `IS_DATA_MEM(ex_mem_store_addr);
    assign ex_mem_std_store_direct_req = ex_mem_std_store_raw_req && !ex_mem_std_store_req;

    // Read request for loads/LR/AMO.
    assign ex_mem_read_req = mem_unit_inst0_read_enable_out || atomic_read_enable;
    assign ex_mem_read_addr = atomic_read_enable ? ex_mem_inst0_mem_addr_out : mem_unit_inst0_read_addr_out;
    assign ex_mem_read_type = (is_lr_w || is_amo_w) ? 3'b010 : mem_unit_inst0_load_type_out;

    // Lookup a pending store-buffer byte by absolute byte address.
    function [8:0] store_buf_lookup_byte;
        input [31:0] addr;
        begin
            store_buf_lookup_byte = 9'h000;
            if (store_buf_valid && store_buf_be[0] && (store_buf_addr == addr)) begin
                store_buf_lookup_byte = {1'b1, store_buf_data[7:0]};
            end else if (store_buf_valid && store_buf_be[1] && ((store_buf_addr + 32'd1) == addr)) begin
                store_buf_lookup_byte = {1'b1, store_buf_data[15:8]};
            end else if (store_buf_valid && store_buf_be[2] && ((store_buf_addr + 32'd2) == addr)) begin
                store_buf_lookup_byte = {1'b1, store_buf_data[23:16]};
            end else if (store_buf_valid && store_buf_be[3] && ((store_buf_addr + 32'd3) == addr)) begin
                store_buf_lookup_byte = {1'b1, store_buf_data[31:24]};
            end
        end
    endfunction

    reg [8:0] load_byte0_lookup;
    reg [8:0] load_byte1_lookup;
    reg [8:0] load_byte2_lookup;
    reg [8:0] load_byte3_lookup;
    reg [7:0] load_byte0;
    reg [7:0] load_byte1;
    reg [7:0] load_byte2;
    reg [7:0] load_byte3;

    // Coverage check used to decide whether memory read is required.
    wire [8:0] cover_byte0_lookup = store_buf_lookup_byte(ex_mem_read_addr);
    wire [8:0] cover_byte1_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd1);
    wire [8:0] cover_byte2_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd2);
    wire [8:0] cover_byte3_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd3);
    wire cover_byte0 = cover_byte0_lookup[8];
    wire cover_byte1 = cover_byte1_lookup[8];
    wire cover_byte2 = cover_byte2_lookup[8];
    wire cover_byte3 = cover_byte3_lookup[8];

    assign load_all_bytes_covered = !ex_mem_read_req ? 1'b0 :
                                    ((ex_mem_read_type == 3'b000) || (ex_mem_read_type == 3'b100)) ? cover_byte0 :
                                    ((ex_mem_read_type == 3'b001) || (ex_mem_read_type == 3'b101)) ? (cover_byte0 && cover_byte1) :
                                    (ex_mem_read_type == 3'b010) ? (cover_byte0 && cover_byte1 && cover_byte2 && cover_byte3) :
                                    1'b0;

    // Merge pending store-buffer bytes onto memory read data.
    always @(*) begin
        load_byte0_lookup = 9'h000;
        load_byte1_lookup = 9'h000;
        load_byte2_lookup = 9'h000;
        load_byte3_lookup = 9'h000;
        load_byte0 = module_read_data_in[7:0];
        load_byte1 = module_read_data_in[15:8];
        load_byte2 = module_read_data_in[23:16];
        load_byte3 = module_read_data_in[31:24];
        mem_read_data_effective = module_read_data_in;

        if (ex_mem_read_req) begin
            load_byte0_lookup = store_buf_lookup_byte(ex_mem_read_addr);
            if (load_byte0_lookup[8]) begin
                load_byte0 = load_byte0_lookup[7:0];
            end

            case (ex_mem_read_type)
                3'b000: begin // LB
                    mem_read_data_effective = {{24{load_byte0[7]}}, load_byte0};
                end
                3'b100: begin // LBU
                    mem_read_data_effective = {24'h0, load_byte0};
                end
                3'b001: begin // LH
                    load_byte1_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd1);
                    if (load_byte1_lookup[8]) begin
                        load_byte1 = load_byte1_lookup[7:0];
                    end
                    mem_read_data_effective = {{16{load_byte1[7]}}, load_byte1, load_byte0};
                end
                3'b101: begin // LHU
                    load_byte1_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd1);
                    if (load_byte1_lookup[8]) begin
                        load_byte1 = load_byte1_lookup[7:0];
                    end
                    mem_read_data_effective = {16'h0, load_byte1, load_byte0};
                end
                3'b010: begin // LW (also LR/AMO read path)
                    load_byte1_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd1);
                    load_byte2_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd2);
                    load_byte3_lookup = store_buf_lookup_byte(ex_mem_read_addr + 32'd3);
                    if (load_byte1_lookup[8]) begin
                        load_byte1 = load_byte1_lookup[7:0];
                    end
                    if (load_byte2_lookup[8]) begin
                        load_byte2 = load_byte2_lookup[7:0];
                    end
                    if (load_byte3_lookup[8]) begin
                        load_byte3 = load_byte3_lookup[7:0];
                    end
                    mem_read_data_effective = {load_byte3, load_byte2, load_byte1, load_byte0};
                end
                default: begin
                    mem_read_data_effective = module_read_data_in;
                end
            endcase
        end
    end

    // Use memory when the load/atomic read is not fully covered by the store buffer.
    assign read_needs_memory = ex_mem_read_req && !load_all_bytes_covered;

    // Commit buffered store only when memory read/write port is free this cycle.
    assign store_buf_commit_fire = store_buf_valid && !read_needs_memory &&
                                   !atomic_write_enable && !ex_mem_std_store_direct_req;
    assign non_atomic_store_write_enable = ex_mem_std_store_direct_req || store_buf_commit_fire;
    assign non_atomic_store_write_addr = ex_mem_std_store_direct_req ? ex_mem_store_addr : store_buf_addr;
    assign atomic_clobbers_store_buf = store_buf_valid && atomic_write_enable &&
                                       (store_buf_addr[31:2] == ex_mem_inst0_mem_addr_out[31:2]);

    // External memory interface arbitration:
    // - Standard stores are buffered then committed from store_buf.
    // - AMO/SC writes are driven directly.
    // - Loads/LR/AMO reads use memory only when needed; otherwise bypass from store_buf.
    assign module_mem_wr_en = atomic_write_enable || ex_mem_std_store_direct_req || store_buf_commit_fire;
    assign module_mem_rd_en = read_needs_memory;
    assign module_write_addr = atomic_write_enable ? ex_mem_inst0_mem_addr_out :
                               (ex_mem_std_store_direct_req ? ex_mem_store_addr : store_buf_addr);
    assign module_read_addr = ex_mem_read_addr;
    assign module_wr_data_out = atomic_write_enable ?
                                (is_amo_w ? atomic_new_word : ex_mem_inst0_rs2_value_out) :
                                (ex_mem_std_store_direct_req ? ex_mem_store_data : store_buf_data);
    assign module_write_byte_enable = atomic_write_enable ? 4'b1111 :
                                      (ex_mem_std_store_direct_req ? ex_mem_store_be : store_buf_be);
    assign module_load_type = ex_mem_read_type;

    // Instantiate MEM_WB pipeline register
    wire [4:0] mem_wb_inst0_rs1_addr_out;
    wire [4:0] mem_wb_inst0_rs2_addr_out;
    wire [4:0] mem_wb_inst0_rd_addr_out;
    wire [31:0] mem_wb_inst0_rs1_value_out;
    wire [31:0] mem_wb_inst0_rs2_value_out;
    wire [31:0] mem_wb_inst0_pc_out;
    wire [31:0] mem_wb_inst0_mem_addr_out;
    wire [31:0] mem_wb_inst0_exec_output_out;
    wire mem_wb_inst0_jump_signal_out;
    wire [31:0] mem_wb_inst0_jump_addr_out;
    wire [6:0] mem_wb_inst0_instr_id_out;
    wire mem_wb_inst0_rd_valid_out;
    wire [31:0] mem_wb_inst0_mem_data_out;

    wire [31:0] ex_mem_exec_output_to_mem_wb = is_sc_w ? sc_result : ex_mem_inst0_exec_output_out;

    MEM_WB mem_wb_inst0 (
        .clk(clk),
        .rst(rst),
        .rs1_addr_in(ex_mem_inst0_rs1_addr_out),
        .rs2_addr_in(ex_mem_inst0_rs2_addr_out),
        .rd_addr_in(ex_mem_inst0_rd_addr_out),
        .rs1_value_in(ex_mem_inst0_rs1_value_out),
        .rs2_value_in(ex_mem_inst0_rs2_value_out),
        .pc_in(ex_mem_inst0_pc_out),
        .mem_addr_in(ex_mem_inst0_mem_addr_out),
        .exec_output_in(ex_mem_exec_output_to_mem_wb),
        .jump_signal_in(ex_mem_inst0_jump_signal_out),
        .jump_addr_in(ex_mem_inst0_jump_addr_out),
        .instr_id_in(ex_mem_inst0_instr_id_out),
        .rd_valid_in(ex_mem_inst0_rd_valid_out),
        .mem_data_in(mem_read_data_effective),  // Memory data with store-buffer merge

        // Outputs
        .rs1_addr_out(mem_wb_inst0_rs1_addr_out),
        .rs2_addr_out(mem_wb_inst0_rs2_addr_out),
        .rd_addr_out(mem_wb_inst0_rd_addr_out),
        .rs1_value_out(mem_wb_inst0_rs1_value_out),
        .rs2_value_out(mem_wb_inst0_rs2_value_out),
        .pc_out(mem_wb_inst0_pc_out),
        .mem_addr_out(mem_wb_inst0_mem_addr_out),
        .exec_output_out(mem_wb_inst0_exec_output_out),
        .jump_signal_out(mem_wb_inst0_jump_signal_out),
        .jump_addr_out(mem_wb_inst0_jump_addr_out),
        .instr_id_out(mem_wb_inst0_instr_id_out),
        .rd_valid_out(mem_wb_inst0_rd_valid_out),
        .mem_data_out(mem_wb_inst0_mem_data_out)  // Output to WB stage
    );

    // Instantiate Write Back Stage
    wire wb_inst0_wr_en_out;
    wire [4:0] wb_inst0_rd_addr_out;
    wire [31:0] wb_inst0_rd_value_out;

    assign rf_inst0_rd_in = wb_inst0_rd_addr_out;
    assign rf_inst0_wr_en = wb_inst0_wr_en_out;
    assign rf_inst0_rd_value_in = wb_inst0_rd_value_out;

    writeback wb_inst0 (
        .rd_valid_in(mem_wb_inst0_rd_valid_out),
        .rd_addr_in(mem_wb_inst0_rd_addr_out),
        .rd_value_in(mem_wb_inst0_exec_output_out),
        .mem_data_in(mem_wb_inst0_mem_data_out),  // Use pipelined data
        .instr_id_in(mem_wb_inst0_instr_id_out),
        .rd_addr_out(wb_inst0_rd_addr_out),
        .rd_value_out(wb_inst0_rd_value_out),
        .wr_en_out(wb_inst0_wr_en_out)
    );

    // Write Back Stage

endmodule
