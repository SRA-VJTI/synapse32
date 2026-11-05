`default_nettype none
`include "memory_map.vh"
`include "instr_defines.vh"
module riscv_cpu #(
    parameter STORE_BUFFER_DEPTH = 4,
    parameter NUM_MSHR = 8,
    parameter [31:0] BOOT_ADDR = `INSTR_MEM_BASE
) (
    input wire clk,
    input wire rst,

    // Fetch port: instruction cache line fills and uncached fetches
    output wire instr_mem_req,
    output wire [31:0] instr_mem_addr,
    input wire instr_mem_gnt,
    input wire instr_mem_rvalid,
    input wire [31:0] instr_mem_rdata,

    // Data port: data cache line transfers, uncached accesses and page-table reads
    output wire data_mem_req,
    output wire [31:0] data_mem_addr,
    output wire data_mem_we,
    output wire [3:0] data_mem_be,
    output wire [31:0] data_mem_wdata,
    output wire [2:0] data_mem_load_type,  // Lines and page-table reads are whole words
    input wire data_mem_gnt,
    input wire data_mem_rvalid,
    input wire [31:0] data_mem_rdata,

    output wire [31:0] module_pc_out,
    output wire [31:0] module_instr_out,

    // Interrupt inputs
    input wire timer_interrupt,                // MTIP
    input wire machine_software_interrupt,     // MSIP
    input wire machine_external_interrupt,     // MEIP
    input wire supervisor_external_interrupt,  // SEIP
    input wire [63:0] mtime_in
);

    // Between the pipeline and the memory system below
    wire [31:0] module_instr_in;
    wire [31:0] module_read_data_in;
    wire [31:0] module_wr_data_out;
    wire module_mem_wr_en;
    wire module_mem_rd_en;
    wire [31:0] module_read_addr;
    wire [31:0] module_write_addr;
    wire [3:0] module_write_byte_enable;  // Write byte enables
    wire [2:0] module_load_type;          // Load type
    wire module_load_page_fault_in;
    wire module_store_page_fault_in;
    wire [31:0] module_page_fault_addr_in;
    wire module_instr_page_fault_in;
    // Memory interface: a request is outstanding until its response arrives.
    wire module_instr_gnt_in;
    wire module_instr_rvalid_in;
    wire module_data_gnt_in;
    wire module_data_rvalid_in;
    wire module_store_buffer_empty_in;  // Store buffer empty once this cycle ends
    // The MMU treats a whole AMO as a write, its read transaction included.
    wire module_data_write_intent_out;
    // SFENCE.VMA or a write to satp: the TLB may hold stale translations.
    wire module_tlb_flush_out;
    // FENCE.I: instruction caches may hold stale lines.
    wire module_instr_cache_flush_out;
    wire [31:0] module_next_pc_out;
    // Address MEM holds after this edge, for the data cache's array read.
    wire [31:0] module_next_data_addr_out;
    // FENCE.I also waits until the data cache has written every dirty line back.
    wire module_data_cache_clean_req_out;
    wire module_data_cache_clean_in;
    wire module_data_mmu_enable_out;
    wire [1:0] module_data_privilege_out;
    wire [31:0] module_satp_out;
    wire module_data_sum_out;
    wire module_data_mxr_out;
    wire module_instr_mmu_enable_out;
    wire [1:0] module_instr_privilege_out;

    // Instantiate PC
    wire [31:0] pc_inst0_out;
    wire pc_inst0_j_signal;
    wire [31:0] pc_inst0_jump;
    wire hazard_stall; // For load-use hazards
    wire pipeline_stall;
    wire fetch_wait;
    wire fetch_response_valid;
    wire mem_wait;
    wire ex_stage_active;
    wire mem_stage_page_fault_taken;
    wire mem_stage_load_page_fault;
    wire mem_stage_store_page_fault;
    wire mem_stage_trap_to_supervisor;
    wire [31:0] mem_stage_jump_addr;
    wire instr_stage_page_fault_taken;
    wire instr_stage_trap_to_supervisor;
    wire [31:0] instr_stage_jump_addr;
    // Priority: MEM page fault > instr page fault > EX branch/trap
    assign pc_inst0_j_signal = mem_stage_page_fault_taken || instr_stage_page_fault_taken || ex_inst0_jump_signal_out;
    assign pc_inst0_jump = mem_stage_page_fault_taken   ? mem_stage_jump_addr :
                           instr_stage_page_fault_taken ? instr_stage_jump_addr :
                           ex_inst0_jump_addr_out;
    pc #(
        .BOOT_ADDR(BOOT_ADDR)
    ) pc_inst0 (
        .clk(clk),
        .rst(rst),
        .j_signal(pc_inst0_j_signal),
        .jump(pc_inst0_jump),
        .stall(pipeline_stall || fetch_wait), // Stall on hazard, WFI sleep or a waiting memory
        .out(pc_inst0_out),
        .next_out(module_next_pc_out)
    );

    // Send out the PC value
    assign module_pc_out = pc_inst0_out;


    // Instantiate IF_ID pipeline register
    wire [31:0] if_id_pc_out;
    wire [31:0] if_id_instr_out;
    wire if_id_instr_valid_out;
    wire if_id_instr_page_fault_out;
    wire execution_flush;
    wire branch_flush;
    wire if_id_flush;
    assign branch_flush = ex_inst0_jump_signal_out; // Flush IF/ID if branch taken
    assign if_id_flush = branch_flush || execution_flush || mem_stage_page_fault_taken || instr_stage_page_fault_taken;
    IF_ID if_id_inst0 (
        .clk(clk),
        .rst(rst),
        .pc_in(pc_inst0_out),
        .instruction_in(module_instr_in),
        .instr_page_fault_in(module_instr_page_fault_in),
        // A fetch still in flight delivers a bubble; while stalled, IF/ID keeps what it holds.
        .flush(if_id_flush || (fetch_wait && !pipeline_stall)),
        // Flush must win over stall, otherwise a stale IF/ID instruction can
        // survive an interrupt/branch redirect and execute one cycle later.
        .stall(pipeline_stall && !if_id_flush),
        .pc_out(if_id_pc_out),
        .instruction_out(if_id_instr_out),
        .instruction_valid_out(if_id_instr_valid_out),
        .instr_page_fault_out(if_id_instr_page_fault_out)
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
    wire [31:0] id_ex_inst0_instr_out;
    wire [31:0] id_ex_inst0_rs1_value_out;
    wire [31:0] id_ex_inst0_rs2_value_out;
    wire id_ex_inst0_instr_valid_out;
    wire id_ex_inst0_instr_page_fault_out;

    // Pipeline flush signals
    wire pipeline_flush;

    // Combine branch flush and execution unit flush
    assign pipeline_flush = branch_flush || execution_flush || mem_stage_page_fault_taken || instr_stage_page_fault_taken;

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
        .instr_in(if_id_instr_out),
        .rs1_value_in(rf_inst0_rs1_value_out),
        .rs2_value_in(rf_inst0_rs2_value_out),
        .rs1_value_resolved_in(ex_inst0_rs1_value_out),
        .rs2_value_resolved_in(ex_inst0_rs2_value_out),
        .instr_valid_in(if_id_instr_valid_out),
        .instr_page_fault_in(if_id_instr_page_fault_out),
        .flush(pipeline_flush),
        .hold(pipeline_hold && !pipeline_flush),
        .stall(hazard_stall && !pipeline_flush),
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
        .instr_out(id_ex_inst0_instr_out),
        .rs1_value_out(id_ex_inst0_rs1_value_out),
        .rs2_value_out(id_ex_inst0_rs2_value_out),
        .instr_valid_out(id_ex_inst0_instr_valid_out),
        .instr_page_fault_out(id_ex_inst0_instr_page_fault_out)
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
    wire [31:0] csr_rmw_data;
    wire [31:0] csr_write_data;
    wire csr_write_enable;
    wire csr_read_enable;
    wire csr_valid;

    // Interrupt controller signals
    wire interrupt_pending;
    wire [31:0] interrupt_cause;
    wire [31:0] interrupt_pc;
    wire interrupt_taken;
    wire interrupt_taken_qualified;
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
    wire [31:0] csr_exception_pc;
    wire csr_trap_to_supervisor;
    wire [31:0] csr_exception_tval;
    wire wfi_instruction;
    wire breakpoint_trigger_exception;
    wire execute_trigger_hit;
    wire [27:0] trigger_control;
    wire [127:0] trigger_tdata2;
    wire instret_increment;
    wire [31:0] exception_pc;
    assign exception_pc = id_ex_inst0_pc_out;
    assign synchronous_exception_taken = ecall_exception || ebreak_exception ||
                                         breakpoint_trigger_exception ||
                                         illegal_instruction_exception ||
                                         instruction_address_misaligned_exception ||
                                         load_address_misaligned_exception ||
                                         store_address_misaligned_exception;
    assign instret_increment = id_ex_inst0_instr_valid_out &&
                               ex_stage_active &&
                               (id_ex_inst0_instr_id_out != INSTR_INVALID) &&
                               !interrupt_taken &&
                               !synchronous_exception_taken &&
                               !mem_stage_page_fault_taken;

    wire [31:0] csr_mstatus;
    wire [31:0] csr_medeleg;
    wire [31:0] csr_mideleg;
    wire [31:0] csr_mie;
    wire [31:0] csr_mip;
    wire [31:0] csr_mtvec;
    wire [31:0] csr_stvec;
    wire [31:0] csr_mepc;
    wire [31:0] csr_sepc;
    wire [31:0] csr_satp;
    wire [31:0] csr_mcounteren;
    wire [31:0] csr_scounteren;
    wire [1:0] csr_privilege_mode;

    localparam PRIV_U = 2'b00;
    localparam PRIV_S = 2'b01;
    localparam PRIV_M = 2'b11;
    wire data_use_mprv = (csr_privilege_mode == PRIV_M) && csr_mstatus[17];
    wire [1:0] data_privilege_mode = data_use_mprv ? csr_mstatus[12:11] : csr_privilege_mode;
    wire data_mmu_enable = (data_privilege_mode != PRIV_M) && csr_satp[31];
    assign module_data_mmu_enable_out = data_mmu_enable;
    assign module_data_privilege_out = data_privilege_mode;
    assign module_satp_out = csr_satp;
    assign module_data_sum_out = csr_mstatus[18];
    assign module_data_mxr_out = csr_mstatus[19];
    assign module_instr_mmu_enable_out = (csr_privilege_mode != PRIV_M) && csr_satp[31];
    assign module_instr_privilege_out = csr_privilege_mode;
    // Sdtrig: a trigger fires only in its selected mode, and not while that mode's interrupts are
    // disabled, or a handler would retrigger on itself (Sdtrig "Native Triggers", no tcontrol).
    function trigger_enabled_in_mode;
        input [6:0] control;
        input [1:0] mode;
        input machine_interrupts_enabled;
        input supervisor_interrupts_enabled;
        begin
            trigger_enabled_in_mode =
                (mode == PRIV_M) ? (control[6] && machine_interrupts_enabled) :
                (mode == PRIV_S) ? (control[4] && supervisor_interrupts_enabled) :
                                   control[3];
        end
    endfunction

    wire breakpoint_delegated = csr_medeleg[3];
    wire [3:0] trigger_enabled = {
        trigger_enabled_in_mode(trigger_control[27:21], csr_privilege_mode,
                                csr_mstatus[3], !breakpoint_delegated || csr_mstatus[1]),
        trigger_enabled_in_mode(trigger_control[20:14], csr_privilege_mode,
                                csr_mstatus[3], !breakpoint_delegated || csr_mstatus[1]),
        trigger_enabled_in_mode(trigger_control[13:7], csr_privilege_mode,
                                csr_mstatus[3], !breakpoint_delegated || csr_mstatus[1]),
        trigger_enabled_in_mode(trigger_control[6:0], csr_privilege_mode,
                                csr_mstatus[3], !breakpoint_delegated || csr_mstatus[1])
    };

    // Trap targets (privileged spec 3.1.7): exceptions at BASE, vectored interrupts at BASE + 4 * cause.
    wire [31:0] mtvec_base = {csr_mtvec[31:2], 2'b00};
    wire [31:0] stvec_base = {csr_stvec[31:2], 2'b00};
    wire interrupt_vectored = interrupt_to_supervisor ? csr_stvec[0] : csr_mtvec[0];
    wire [31:0] interrupt_vector = (interrupt_to_supervisor ? stvec_base : mtvec_base) +
                                   (interrupt_vectored ? {interrupt_cause[29:0], 2'b00} : 32'h0);
    assign interrupt_taken_qualified = interrupt_taken &&
                                       !synchronous_exception_taken &&
                                       !mem_stage_page_fault_taken &&
                                       !instr_stage_page_fault_taken;

    // WFI sleep state: stall fetch/decode until an enabled interrupt becomes
    // pending, even if the corresponding global interrupt-enable bit is clear.
    // Trap delivery still uses interrupt_pending below; this only controls
    // whether WFI can resume.
    reg wfi_active;
    reg fetch_outstanding;
    reg fetch_discard;
    wire wfi_stall;
    wire wfi_resume_pending;
    localparam [31:0] WFI_WAKE_INTERRUPT_MASK = 32'h00000AAA;
    assign wfi_resume_pending =
        |(csr_mip & csr_mie & WFI_WAKE_INTERRUPT_MASK);
    assign wfi_stall = wfi_active && !wfi_resume_pending;

    wire ex_mem_std_store_req;
    wire [31:0] ex_mem_store_addr;
    wire [31:0] ex_mem_store_data;
    wire [3:0] ex_mem_store_be;
    wire ex_mem_read_req;
    wire [31:0] ex_mem_read_addr;
    wire [2:0] ex_mem_read_type;
    wire non_atomic_store_write_enable;
    wire [31:0] non_atomic_store_write_addr;
    reg [31:0] mem_read_data_effective;

    // An AMO is a read then a write, since the value written depends on the value read.
    reg amo_write_phase;
    reg [31:0] amo_read_data;
    wire amo_read_phase;

    // Atomic LSU signals (produced by atomic_lsu module in MEM stage).
    wire is_lr_w;
    wire is_sc_w;
    wire is_amo_w;
    wire atomic_read_enable;
    wire atomic_write_enable;
    wire sc_success;
    wire [31:0] sc_result;
    wire [31:0] atomic_new_word;
    // FENCE and FENCE.I wait for older writes to reach memory, so FENCE.I refetches the new code.
    wire fence_drain_stall = id_ex_inst0_instr_valid_out &&
                             ((!module_store_buffer_empty_in &&
                               ((id_ex_inst0_instr_id_out == INSTR_FENCE) ||
                                (id_ex_inst0_instr_id_out == INSTR_FENCE_I))) ||
                              (!module_data_cache_clean_in && (id_ex_inst0_instr_id_out == INSTR_FENCE_I)));
    // A page-faulting access never reaches memory, so it is not waited for.
    // A fetch accepted before a redirect answers for the old PC, so its response is dropped.
    assign fetch_response_valid = module_instr_rvalid_in && !fetch_discard;
    assign fetch_wait = !fetch_response_valid && !module_instr_page_fault_in;
    // Outstanding until rvalid; an AMO's read response still leaves its write to issue.
    assign mem_wait = (module_mem_rd_en || module_mem_wr_en) &&
                      !(module_data_rvalid_in && !amo_read_phase) &&
                      !mem_stage_page_fault_taken;
    // A divide holds EX until the divider answers, but not an interrupt: a divide has no effect until it retires, so
    // EX takes the interrupt against it and the divide runs again after the handler; the divider drops the division
    // with its request. If an older access faults instead, its trap squashes the divide all the same.
    wire div_in_ex = id_ex_inst0_instr_valid_out && !id_ex_inst0_instr_page_fault_out &&
                     ((id_ex_inst0_instr_id_out == INSTR_DIV) || (id_ex_inst0_instr_id_out == INSTR_DIVU) ||
                      (id_ex_inst0_instr_id_out == INSTR_REM) || (id_ex_inst0_instr_id_out == INSTR_REMU));
    wire div_done;
    wire div_stall = div_in_ex && !div_done && !interrupt_pending;
    assign ex_stage_active = !mem_wait && !fence_drain_stall && !div_stall;
    wire pipeline_hold = wfi_stall || fence_drain_stall || mem_wait || div_stall;
    assign pipeline_stall = hazard_stall || pipeline_hold;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            amo_write_phase <= 1'b0;
            amo_read_data <= 32'b0;
            fetch_outstanding <= 1'b0;
            fetch_discard <= 1'b0;
            wfi_active <= 1'b0;
        end else begin
            if (module_instr_rvalid_in) begin
                fetch_outstanding <= 1'b0;
                fetch_discard <= 1'b0;
            end else if (module_instr_gnt_in) begin
                fetch_outstanding <= 1'b1;
            end
            if (pc_inst0_j_signal && (fetch_outstanding || module_instr_gnt_in) &&
                !module_instr_rvalid_in) begin
                fetch_discard <= 1'b1;
            end

            if (wfi_resume_pending) begin
                wfi_active <= 1'b0;
            end else if (wfi_instruction) begin
                wfi_active <= 1'b1;
            end

            // AMO phase: capture the value read, then let the write go out.
            if (amo_read_phase && module_data_rvalid_in) begin
                amo_read_data <= mem_read_data_effective;
                amo_write_phase <= 1'b1;
            end else if (amo_write_phase && module_data_rvalid_in) begin
                amo_write_phase <= 1'b0;
            end
        end
    end

    // Instantiate interrupt controller
    interrupt_controller int_ctrl_inst (
        .clk(clk),
        .rst(rst),
        .mstatus(csr_mstatus),
        .mie(csr_mie),
        .mip(csr_mip),
        .mideleg(csr_mideleg),
        .privilege_mode(csr_privilege_mode),
        .interrupt_pending(interrupt_pending),
        .interrupt_cause(interrupt_cause),
        .interrupt_to_supervisor(interrupt_to_supervisor),
        .interrupt_taken(interrupt_taken_qualified),
        // Oldest unexecuted instruction: EX, else IF/ID (EX bubble), else fetch PC.
        .current_pc(id_ex_inst0_instr_valid_out ? id_ex_inst0_pc_out :
                    if_id_instr_valid_out      ? if_id_pc_out :
                                                 pc_inst0_out),
        .interrupt_pc(interrupt_pc)
    );

    // Instantiate CSR file at CPU level
    csr_file csr_file_inst (
        .clk(clk),
        .rst(rst),
        .csr_addr(csr_addr),
        .write_data(csr_write_data),
        .write_enable(csr_write_enable && ex_stage_active),
        .read_enable(csr_read_enable),
        .read_data(csr_read_data),
        .csr_valid(csr_valid),
        .interrupt_pending(interrupt_pending),
        .interrupt_cause_in(interrupt_cause),
        .interrupt_pc_in(interrupt_pc),
        .exception_pc_in(csr_exception_pc),
        .interrupt_taken(interrupt_taken_qualified),
        .mret_instruction(mret_instruction),
        .sret_instruction(sret_instruction),
        .interrupt_to_supervisor(interrupt_to_supervisor),
        .trap_to_supervisor(csr_trap_to_supervisor),
        .ecall_exception(ecall_exception),
        .ebreak_exception(ebreak_exception),
        .illegal_instruction_exception(illegal_instruction_exception),
        .instruction_address_misaligned_exception(instruction_address_misaligned_exception),
        .load_address_misaligned_exception(load_address_misaligned_exception),
        .store_address_misaligned_exception(store_address_misaligned_exception),
        .instr_page_fault_exception(instr_stage_page_fault_taken),
        .load_page_fault_exception(mem_stage_load_page_fault),
        .store_page_fault_exception(mem_stage_store_page_fault),
        .breakpoint_trigger_exception(breakpoint_trigger_exception),
        .exception_tval_in(csr_exception_tval),
        .trigger_control(trigger_control),
        .trigger_tdata2(trigger_tdata2),
        .mstatus_out(csr_mstatus),
        .medeleg_out(csr_medeleg),
        .mideleg_out(csr_mideleg),
        .mie_out(csr_mie),
        .mip_out(csr_mip),
        .mtvec_out(csr_mtvec),
        .stvec_out(csr_stvec),
        .mepc_out(csr_mepc),
        .sepc_out(csr_sepc),
        .satp_out(csr_satp),
        .mcounteren_out(csr_mcounteren),
        .scounteren_out(csr_scounteren),
        .privilege_mode_out(csr_privilege_mode),
        .instret_increment(instret_increment),
        .timer_interrupt(timer_interrupt),
        .machine_software_interrupt(machine_software_interrupt),
        .machine_external_interrupt(machine_external_interrupt),
        .supervisor_external_interrupt(supervisor_external_interrupt),
        .mtime_in(mtime_in),
        .rmw_data(csr_rmw_data)
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
        .stage_enable(ex_stage_active),
        .pc_input(id_ex_inst0_pc_out),
        .instr(id_ex_inst0_instr_out),
        .forward_a(forward_a),
        .forward_b(forward_b),
        .ex_mem_result(ex_mem_forward_result),
        .mem_wb_result(wb_inst0_rd_value_out),
        
        // CSR interface connections
        .csr_read_data(csr_read_data),
        .csr_rmw_data(csr_rmw_data),
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
        .interrupt_pending(interrupt_pending &&
                           !mem_stage_page_fault_taken &&
                           !instr_stage_page_fault_taken),
        .interrupt_cause(interrupt_cause),
        .interrupt_to_supervisor(interrupt_to_supervisor),
        .interrupt_vector(interrupt_vector),
        .mtvec(mtvec_base),
        .mepc(csr_mepc),
        .stvec(stvec_base),
        .sepc(csr_sepc),
        .medeleg(csr_medeleg),
        .privilege_mode(csr_privilege_mode),
        .mstatus(csr_mstatus),
        .mcounteren(csr_mcounteren),
        .scounteren(csr_scounteren),
        .trigger_enabled(trigger_enabled),
        .trigger_control(trigger_control),
        .trigger_tdata2(trigger_tdata2),
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
        .wfi_instruction(wfi_instruction),
        .breakpoint_trigger_exception(breakpoint_trigger_exception),
        .execute_trigger_hit(execute_trigger_hit)
    );

    wire [31:0] div_quotient;
    wire [31:0] div_remainder;

    divider divider_inst (
        .clk(clk),
        .rst(rst),
        .req(div_in_ex),
        // Forwarded operands are valid once MEM is not waiting.
        .start(!mem_wait),
        .ack(!pipeline_hold),
        .is_signed((id_ex_inst0_instr_id_out == INSTR_DIV) || (id_ex_inst0_instr_id_out == INSTR_REM)),
        .dividend(ex_inst0_rs1_value_out),
        .divisor(ex_inst0_rs2_value_out),
        .done(div_done),
        .quotient(div_quotient),
        .remainder(div_remainder)
    );

    wire [31:0] ex_result = !div_in_ex ? ex_inst0_exec_output_out :
                            ((id_ex_inst0_instr_id_out == INSTR_REM) || (id_ex_inst0_instr_id_out == INSTR_REMU)) ?
                            div_remainder : div_quotient;

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
        .hold(mem_wait),
        // No partial quotient reaches WB while the divider runs.
        .flush(mem_stage_page_fault_taken ||
               instr_stage_page_fault_taken ||
               synchronous_exception_taken ||
               interrupt_taken_qualified ||
               (div_stall && !mem_wait)),
        .rs1_addr_in(id_ex_inst0_rs1_addr_out),
        .rs2_addr_in(id_ex_inst0_rs2_addr_out),
        .rd_addr_in(id_ex_inst0_rd_addr_out),
        .rs1_value_in(ex_inst0_rs1_value_out),
        .rs2_value_in(ex_inst0_rs2_value_out),
        .pc_in(id_ex_inst0_pc_out),
        .mem_addr_in(ex_inst0_mem_addr_out),
        .exec_output_in(ex_result),
        .jump_signal_in(ex_inst0_jump_signal_out),
        .jump_addr_in(ex_inst0_jump_addr_out),
        .instr_id_in(id_ex_inst0_instr_id_out),
        .rd_valid_in(id_ex_inst0_rd_valid_out),
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
        // In the write phase the new word is computed from the value the read returned.
        .mem_read_data(amo_write_phase ? amo_read_data : mem_read_data_effective),
        .mem_hold(mem_wait),
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

    // SB/SH/SW leave EX/MEM directly; the store buffer outside the core queues them.
    assign ex_mem_std_store_req = mem_unit_inst0_wr_enable_out &&
                                  (mem_unit_inst0_write_byte_enable_out != 4'b0000);
    assign ex_mem_store_addr = mem_unit_inst0_wr_addr_out;
    assign ex_mem_store_data = mem_unit_inst0_wr_data_out;
    assign ex_mem_store_be = mem_unit_inst0_write_byte_enable_out;

    // Read request for loads/LR/AMO.
    assign amo_read_phase = is_amo_w && !amo_write_phase;
    assign ex_mem_read_req = mem_unit_inst0_read_enable_out ||
                             (atomic_read_enable && !(is_amo_w && amo_write_phase));
    assign ex_mem_read_addr = atomic_read_enable ? ex_mem_inst0_mem_addr_out : mem_unit_inst0_read_addr_out;
    assign ex_mem_read_type = (is_lr_w || is_amo_w) ? 3'b010 : mem_unit_inst0_load_type_out;

    always @(*) begin
        mem_read_data_effective = module_read_data_in;
        if (ex_mem_read_req) begin
            case (ex_mem_read_type)
                3'b000: mem_read_data_effective = {{24{module_read_data_in[7]}}, module_read_data_in[7:0]};   // LB
                3'b100: mem_read_data_effective = {24'h0, module_read_data_in[7:0]};                          // LBU
                3'b001: mem_read_data_effective = {{16{module_read_data_in[15]}}, module_read_data_in[15:0]}; // LH
                3'b101: mem_read_data_effective = {16'h0, module_read_data_in[15:0]};                         // LHU
                default: mem_read_data_effective = module_read_data_in;                                       // LW, LR, AMO
            endcase
        end
    end

    // A standard store to the reserved word breaks an LR reservation.
    assign non_atomic_store_write_enable = ex_mem_std_store_req;
    assign non_atomic_store_write_addr = ex_mem_store_addr;

    // AMO/SC writes are whole words; standard stores carry their byte enables.
    assign module_mem_wr_en = (atomic_write_enable && (!is_amo_w || amo_write_phase)) || ex_mem_std_store_req;
    assign module_mem_rd_en = ex_mem_read_req;
    assign module_write_addr = atomic_write_enable ? ex_mem_inst0_mem_addr_out : ex_mem_store_addr;
    assign module_read_addr = ex_mem_read_addr;
    assign module_wr_data_out = atomic_write_enable ?
                                (is_amo_w ? atomic_new_word : ex_mem_inst0_rs2_value_out) :
                                ex_mem_store_data;
    assign module_write_byte_enable = atomic_write_enable ? 4'b1111 : ex_mem_store_be;
    assign module_load_type = ex_mem_read_type;
    assign module_data_write_intent_out = module_mem_wr_en || is_amo_w;
    assign module_tlb_flush_out =
        ex_stage_active && id_ex_inst0_instr_valid_out &&
        ((id_ex_inst0_instr_id_out == INSTR_SFENCE_VMA) ||
         (csr_write_enable && (csr_addr == 12'h180)));
    assign module_next_data_addr_out = mem_wait ? ex_mem_inst0_mem_addr_out : ex_inst0_mem_addr_out;
    assign module_data_cache_clean_req_out =
        id_ex_inst0_instr_valid_out && (id_ex_inst0_instr_id_out == INSTR_FENCE_I);
    assign module_instr_cache_flush_out =
        ex_stage_active && id_ex_inst0_instr_valid_out && (id_ex_inst0_instr_id_out == INSTR_FENCE_I);
    assign mem_stage_load_page_fault = module_load_page_fault_in && ex_mem_read_req;
    // An AMO's read half takes its store/AMO page fault, or MEM would wait on a blocked write.
    assign mem_stage_store_page_fault = module_store_page_fault_in && module_data_write_intent_out;
    assign mem_stage_page_fault_taken = mem_stage_load_page_fault || mem_stage_store_page_fault;
    assign mem_stage_trap_to_supervisor =
        (csr_privilege_mode != PRIV_M) &&
        ((mem_stage_load_page_fault && csr_medeleg[13]) ||
         (mem_stage_store_page_fault && csr_medeleg[15]));
    assign mem_stage_jump_addr = mem_stage_trap_to_supervisor ? stvec_base : mtvec_base;

    // An execute trigger is higher priority than the fetch page fault of the same instruction.
    // Like every EX exception, it waits while an older access is outstanding in MEM.
    assign instr_stage_page_fault_taken = id_ex_inst0_instr_page_fault_out &&
                                          id_ex_inst0_instr_valid_out &&
                                          ex_stage_active &&
                                          !execute_trigger_hit;
    assign instr_stage_trap_to_supervisor =
        (csr_privilege_mode != PRIV_M) && csr_medeleg[12];
    assign instr_stage_jump_addr = instr_stage_trap_to_supervisor ? stvec_base : mtvec_base;

    assign csr_exception_pc = mem_stage_page_fault_taken   ? ex_mem_inst0_pc_out :
                              instr_stage_page_fault_taken ? id_ex_inst0_pc_out :
                              exception_pc;
    assign csr_trap_to_supervisor = mem_stage_page_fault_taken   ? mem_stage_trap_to_supervisor :
                                    instr_stage_page_fault_taken ? instr_stage_trap_to_supervisor :
                                    trap_to_supervisor;
    assign csr_exception_tval = mem_stage_page_fault_taken   ? ex_mem_inst0_mem_addr_out :
                                instr_stage_page_fault_taken ? id_ex_inst0_pc_out :
                                exception_tval;

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
        // While MEM waits, WB takes a bubble: the access has not completed.
        .flush(mem_wait),
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
        .instr_id_in(mem_stage_page_fault_taken ? 7'b0000000 : ex_mem_inst0_instr_id_out),
        .rd_valid_in(mem_stage_page_fault_taken ? 1'b0 : ex_mem_inst0_rd_valid_out),
        // An AMO writes back the value it read, not what memory holds after its write.
        .mem_data_in(amo_write_phase ? amo_read_data : mem_read_data_effective),

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

    // Memory system: MMU, store buffer, caches and the data-port arbitration
    wire [31:0] data_virtual_addr;
    wire translated_data_access;
    wire [31:0] phys_data_addr;   // physical address after MMU walk (or virtual if MMU off)
    wire [31:0] phys_instr_addr;
    wire mmu_instr_ready;
    wire mmu_data_ready;
    wire mmu_walk_req;
    wire [31:0] mmu_walk_addr;
    wire mmu_walk_gnt;
    wire mmu_walk_rvalid;
    wire data_bus_walk_sel;
    wire data_bus_walk_owns;
    reg data_bus_walk_owner_q;
    wire dcache_gnt;
    wire dcache_rvalid;
    wire cpu_data_bus_req;
    wire cpu_data_req;
    wire [31:0] cpu_data_rdata;
    wire cpu_ram_access;
    wire cpu_device_access;
    wire cpu_load_go;
    wire store_buf_push_req;
    wire store_buf_push;
    wire store_buf_pop;
    wire store_buf_empty;
    wire store_buf_full;
    wire store_buf_match;
    wire store_buf_forward;
    wire [31:0] store_buf_forward_data;
    wire store_buf_forward_go;
    reg store_buf_forward_pending_q;
    reg [31:0] store_buf_forward_data_q;
    wire [31:0] store_buf_head_addr;
    wire [3:0] store_buf_head_be;
    wire [31:0] store_buf_head_data;
    wire drain_req;
    wire data_bus_drain_sel;
    wire data_bus_drain_owns;
    reg data_bus_drain_owner_q;
    wire drain_done;
    wire [31:0] drain_addr;
    wire [3:0] drain_be;
    wire [31:0] drain_data;
    wire dcache_clean;
    wire dcache_mem_line;

    assign translated_data_access = module_data_mmu_enable_out && (module_mem_wr_en || module_mem_rd_en);
    // Outside RAM is a device: uncached, never forwarded, and its loads wait for earlier writes.
    assign cpu_ram_access = `IS_DATA_MEM(phys_data_addr) || `IS_INSTR_MEM(phys_data_addr);
    assign cpu_device_access = !cpu_ram_access;
    // Select the appropriate address for memory access
    assign data_virtual_addr = module_mem_wr_en ? module_write_addr : module_read_addr;

    // A faulting access is never accepted, or it would commit after the trap.
    assign cpu_data_req = (module_mem_rd_en || module_mem_wr_en) &&
                          !module_load_page_fault_in && !module_store_page_fault_in;
    // The core may only go to memory once its translation is available.
    assign cpu_data_bus_req = cpu_data_req && mmu_data_ready;
    // A load waits for buffered writes to its word; a device load waits for all of them.
    assign store_buf_push_req = cpu_data_bus_req && module_mem_wr_en && !store_buf_full;
    assign cpu_load_go = cpu_data_bus_req && !module_mem_wr_en && !store_buf_match &&
                         !(cpu_device_access && !store_buf_empty) && !store_buf_forward_pending_q;
    // A load fully covered by the last buffered write to its word takes its bytes from the buffer,
    // registered: the next cycle, so the translation and the buffer compare do not reach the core.
    assign store_buf_forward_go = cpu_data_bus_req && !module_mem_wr_en && store_buf_forward &&
                                  !store_buf_forward_pending_q;
    // An empty buffer issues the entering write at once.
    assign drain_req = !store_buf_empty || store_buf_push_req;
    assign drain_addr = store_buf_empty ? phys_data_addr : store_buf_head_addr;
    assign drain_be = store_buf_empty ? module_write_byte_enable : store_buf_head_be;
    assign drain_data = store_buf_empty ? module_wr_data_out : store_buf_head_data;
    assign drain_done = dcache_rvalid && data_bus_drain_owns;
    assign store_buf_push = store_buf_push_req && !(store_buf_empty && drain_done);
    assign store_buf_pop = drain_done && !store_buf_empty;

    // One master at a time: the core's load, then the buffer, then the walker, which waits for an
    // empty buffer so it reads updated page-table entries.
    assign data_bus_drain_sel = drain_req && !cpu_load_go;
    assign data_bus_walk_sel = mmu_walk_req && !cpu_load_go && !drain_req;
    assign data_bus_walk_owns = data_bus_walk_owner_q || (data_bus_walk_sel && dcache_gnt);
    assign data_bus_drain_owns = data_bus_drain_owner_q || (data_bus_drain_sel && dcache_gnt);
    assign mmu_walk_gnt = dcache_gnt && data_bus_walk_sel;
    assign mmu_walk_rvalid = dcache_rvalid && data_bus_walk_owns;
    assign module_data_gnt_in = module_mem_wr_en ? store_buf_push_req :
                                ((dcache_gnt && cpu_load_go) || store_buf_forward_go);
    assign module_data_rvalid_in = module_mem_wr_en ? store_buf_push_req :
                                   ((dcache_rvalid && !data_bus_walk_owns && !data_bus_drain_owns) ||
                                    store_buf_forward_pending_q);
    assign module_read_data_in = store_buf_forward_pending_q ? store_buf_forward_data_q : cpu_data_rdata;
    // Also no write entering the cache this cycle.
    assign module_data_cache_clean_in = dcache_clean && !drain_req;
    // Line transfers and walks read whole words; the core's load type applies to its own accesses.
    assign data_mem_load_type = (dcache_mem_line || data_bus_walk_owns) ? 3'b010 : module_load_type;
    assign module_instr_out = module_instr_in;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            store_buf_forward_pending_q <= 1'b0;
            store_buf_forward_data_q <= 32'b0;
        end else begin
            store_buf_forward_pending_q <= store_buf_forward_go;
            if (store_buf_forward_go) begin
                store_buf_forward_data_q <= store_buf_forward_data;
            end
        end
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            data_bus_walk_owner_q <= 1'b0;
            data_bus_drain_owner_q <= 1'b0;
        end else if (dcache_rvalid) begin
            data_bus_walk_owner_q <= 1'b0;
            data_bus_drain_owner_q <= 1'b0;
        end else if (dcache_gnt) begin
            data_bus_walk_owner_q <= data_bus_walk_sel;
            data_bus_drain_owner_q <= data_bus_drain_sel;
        end
    end

    store_buffer #(.DEPTH(STORE_BUFFER_DEPTH)) store_buffer_inst (
        .clk(clk),
        .rst(rst),
        .push(store_buf_push),
        .push_addr(phys_data_addr),
        .push_be(module_write_byte_enable),
        .push_data(module_wr_data_out),
        .push_ram(cpu_ram_access),
        .pop(store_buf_pop),
        .empty(store_buf_empty),
        .full(store_buf_full),
        .drained(module_store_buffer_empty_in),
        .head_addr(store_buf_head_addr),
        .head_be(store_buf_head_be),
        .head_data(store_buf_head_data),
        .head_ram(),
        .match_addr(phys_data_addr),
        .match_type(module_load_type),
        .match(store_buf_match),
        .forward(store_buf_forward),
        .forward_data(store_buf_forward_data)
    );

    icache icache_inst (
        .clk(clk),
        .rst(rst),
        .flush(module_instr_cache_flush_out),
        .next_pc(module_next_pc_out),
        // A fetch goes to memory only once translated; a fetch that faults never does.
        .req(mmu_instr_ready && !module_instr_page_fault_in),
        .addr(phys_instr_addr),
        .gnt(module_instr_gnt_in),
        .rvalid(module_instr_rvalid_in),
        .rdata(module_instr_in),
        .mem_req(instr_mem_req),
        .mem_addr(instr_mem_addr),
        .mem_gnt(instr_mem_gnt),
        .mem_rvalid(instr_mem_rvalid),
        .mem_rdata(instr_mem_rdata)
    );

    dcache #(.NUM_MSHR(NUM_MSHR)) dcache_inst (
        .clk(clk),
        .rst(rst),
        .next_addr(module_next_data_addr_out),
        .clean_req(module_data_cache_clean_req_out),
        .clean(dcache_clean),
        .req(data_bus_walk_sel || data_bus_drain_sel || cpu_load_go),
        .addr(data_bus_walk_sel ? mmu_walk_addr : data_bus_drain_sel ? drain_addr : phys_data_addr),
        .we(data_bus_drain_sel),
        .be(data_bus_walk_sel ? 4'b1111 : data_bus_drain_sel ? drain_be : module_write_byte_enable),
        .wdata(data_bus_drain_sel ? drain_data : 32'b0),
        .load_type(data_bus_walk_sel ? 3'b010 : module_load_type),
        .gnt(dcache_gnt),
        .rvalid(dcache_rvalid),
        .rdata(cpu_data_rdata),
        .mem_req(data_mem_req),
        .mem_addr(data_mem_addr),
        .mem_we(data_mem_we),
        .mem_be(data_mem_be),
        .mem_wdata(data_mem_wdata),
        .mem_line(dcache_mem_line),
        .mem_gnt(data_mem_gnt),
        .mem_rvalid(data_mem_rvalid),
        .mem_rdata(data_mem_rdata)
    );

    sv32_mmu mmu_inst (
        .clk(clk),
        .rst(rst),
        .flush_tlb(module_tlb_flush_out),
        .satp(module_satp_out),
        .data_sum(module_data_sum_out),
        .data_mxr(module_data_mxr_out),
        .instr_translate_enable(module_instr_mmu_enable_out),
        .instr_virtual_addr(module_pc_out),
        .instr_priv_mode(module_instr_privilege_out),
        .instr_phys_addr(phys_instr_addr),
        .instr_ready(mmu_instr_ready),
        .instr_page_fault(module_instr_page_fault_in),
        .data_translate_enable(translated_data_access),
        .data_virtual_addr(data_virtual_addr),
        .data_rd_en(module_mem_rd_en),
        .data_wr_req(module_data_write_intent_out),
        .data_priv_mode(module_data_privilege_out),
        .data_phys_addr(phys_data_addr),
        .data_ready(mmu_data_ready),
        .data_load_page_fault(module_load_page_fault_in),
        .data_store_page_fault(module_store_page_fault_in),
        .data_fault_addr(module_page_fault_addr_in),
        .walk_req(mmu_walk_req),
        .walk_addr(mmu_walk_addr),
        .walk_gnt(mmu_walk_gnt),
        .walk_rvalid(mmu_walk_rvalid),
        .walk_rdata(cpu_data_rdata)
    );

endmodule
