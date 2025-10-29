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
    input wire external_interrupt,

    // RVFI interface outputs for formal verification
    output wire        rvfi_valid,
    output wire [63:0] rvfi_order,
    output wire [31:0] rvfi_insn,
    output wire        rvfi_trap,
    output wire        rvfi_halt,
    output wire        rvfi_intr,
    output wire [1:0]  rvfi_mode,
    output wire [1:0]  rvfi_ixl,
    output wire [4:0]  rvfi_rs1_addr,
    output wire [4:0]  rvfi_rs2_addr,
    output wire [31:0] rvfi_rs1_rdata,
    output wire [31:0] rvfi_rs2_rdata,
    output wire [4:0]  rvfi_rd_addr,
    output wire [31:0] rvfi_rd_wdata,
    output wire [31:0] rvfi_pc_rdata,
    output wire [31:0] rvfi_pc_wdata,
    output wire [31:0] rvfi_mem_addr,
    output wire [3:0]  rvfi_mem_rmask,
    output wire [31:0] rvfi_mem_rdata,
    output wire [31:0] rvfi_mem_wdata,
    output wire [3:0]  rvfi_mem_wmask,

    // CSR RVFI channels
    output wire [31:0] rvfi_csr_mstatus_rmask,
    output wire [31:0] rvfi_csr_mstatus_wmask,
    output wire [31:0] rvfi_csr_mstatus_rdata,
    output wire [31:0] rvfi_csr_mstatus_wdata,
    output wire [31:0] rvfi_csr_misa_rmask,
    output wire [31:0] rvfi_csr_misa_wmask,
    output wire [31:0] rvfi_csr_misa_rdata,
    output wire [31:0] rvfi_csr_misa_wdata,
    output wire [31:0] rvfi_csr_mie_rmask,
    output wire [31:0] rvfi_csr_mie_wmask,
    output wire [31:0] rvfi_csr_mie_rdata,
    output wire [31:0] rvfi_csr_mie_wdata,
    output wire [31:0] rvfi_csr_mtvec_rmask,
    output wire [31:0] rvfi_csr_mtvec_wmask,
    output wire [31:0] rvfi_csr_mtvec_rdata,
    output wire [31:0] rvfi_csr_mtvec_wdata,
    output wire [31:0] rvfi_csr_mscratch_rmask,
    output wire [31:0] rvfi_csr_mscratch_wmask,
    output wire [31:0] rvfi_csr_mscratch_rdata,
    output wire [31:0] rvfi_csr_mscratch_wdata,
    output wire [31:0] rvfi_csr_mepc_rmask,
    output wire [31:0] rvfi_csr_mepc_wmask,
    output wire [31:0] rvfi_csr_mepc_rdata,
    output wire [31:0] rvfi_csr_mepc_wdata,
    output wire [31:0] rvfi_csr_mcause_rmask,
    output wire [31:0] rvfi_csr_mcause_wmask,
    output wire [31:0] rvfi_csr_mcause_rdata,
    output wire [31:0] rvfi_csr_mcause_wdata,
    output wire [31:0] rvfi_csr_mtval_rmask,
    output wire [31:0] rvfi_csr_mtval_wmask,
    output wire [31:0] rvfi_csr_mtval_rdata,
    output wire [31:0] rvfi_csr_mtval_wdata,
    output wire [31:0] rvfi_csr_mip_rmask,
    output wire [31:0] rvfi_csr_mip_wmask,
    output wire [31:0] rvfi_csr_mip_rdata,
    output wire [31:0] rvfi_csr_mip_wdata
);

    // Instruction and CSR identifiers used for RVFI bookkeeping
    localparam [5:0] INSTR_INVALID = 6'h00;

    localparam [11:0] CSR_MSTATUS  = 12'h300;
    localparam [11:0] CSR_MISA     = 12'h301;
    localparam [11:0] CSR_MIE      = 12'h304;
    localparam [11:0] CSR_MTVEC    = 12'h305;
    localparam [11:0] CSR_MSCRATCH = 12'h340;
    localparam [11:0] CSR_MEPC     = 12'h341;
    localparam [11:0] CSR_MCAUSE   = 12'h342;
    localparam [11:0] CSR_MTVAL    = 12'h343;
    localparam [11:0] CSR_MIP      = 12'h344;

    // Instantiate PC
    wire [31:0] pc_inst0_out;
    wire pc_inst0_j_signal;
    wire [31:0] pc_inst0_jump;
    wire stall_pipeline; // For load-use hazards
    // Branch handling: use EX stage jump signal/address
    assign pc_inst0_j_signal = ex_inst0_jump_signal_out;
    assign pc_inst0_jump = ex_inst0_jump_addr_out;
    pc pc_inst0 (
        .clk(clk),
        .rst(rst),
        .j_signal(pc_inst0_j_signal),
        .jump(pc_inst0_jump),
        .stall(stall_pipeline), // Stall on load-use hazard
        .out(pc_inst0_out)
    );

    // Send out the PC value
    assign module_pc_out = pc_inst0_out;


    // Instantiate IF_ID pipeline register
    wire [31:0] if_id_pc_out;
    wire [31:0] if_id_instr_out;
    wire branch_flush;
    assign branch_flush = ex_inst0_jump_signal_out; // Flush IF/ID if branch taken
    // If branch taken, flush IF/ID by setting instruction to 0 (NOP)
    IF_ID if_id_inst0 (
        .clk(clk),
        .rst(rst),
        .pc_in(pc_inst0_out),
        .instruction_in(branch_flush ? 32'h13 : module_instr_in),
        .stall(stall_pipeline), // Stall on load-use hazard
        .pc_out(if_id_pc_out),
        .instruction_out(if_id_instr_out)
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
    wire [5:0] decoder_inst0_instr_id_out;

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
        .stall_pipeline(stall_pipeline)
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
    wire [5:0] id_ex_inst0_instr_id_out;
    wire [31:0] id_ex_inst0_pc_out;
    wire [31:0] id_ex_inst0_instruction_out;
    wire [31:0] id_ex_inst0_rs1_value_out;
    wire [31:0] id_ex_inst0_rs2_value_out;

    // Pipeline flush signals
    wire execution_flush;
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
        .instruction_in(if_id_instr_out),
        .pc_in(if_id_pc_out),
        .rs1_value_in(rf_inst0_rs1_value_out),
        .rs2_value_in(rf_inst0_rs2_value_out),
        .stall(pipeline_flush || stall_pipeline), // Use combined flush
        .rs1_valid_out(id_ex_inst0_rs1_valid_out),
        .rs2_valid_out(id_ex_inst0_rs2_valid_out),
        .rd_valid_out(id_ex_inst0_rd_valid_out),
        .imm_out(id_ex_inst0_imm_out),
        .rs1_addr_out(id_ex_inst0_rs1_addr_out),
        .rs2_addr_out(id_ex_inst0_rs2_addr_out),
        .rd_addr_out(id_ex_inst0_rd_addr_out),
        .opcode_out(id_ex_inst0_opcode_out),
        .instr_id_out(id_ex_inst0_instr_id_out),
        .instruction_out(id_ex_inst0_instruction_out),
        .pc_out(id_ex_inst0_pc_out),
        .rs1_value_out(id_ex_inst0_rs1_value_out),
        .rs2_value_out(id_ex_inst0_rs2_value_out)
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
    wire mret_instruction;
    wire ecall_exception;
    wire ebreak_exception;

    // CSR outputs
    wire [31:0] csr_mstatus;
    wire [31:0] csr_mie;
    wire [31:0] csr_mip;
    wire [31:0] csr_mtvec;
    wire [31:0] csr_mepc;

    // Instantiate interrupt controller
    interrupt_controller int_ctrl_inst (
        .clk(clk),
        .rst(rst),
        .timer_interrupt(timer_interrupt),
        .software_interrupt(software_interrupt),
        .external_interrupt(external_interrupt),
        .mstatus(csr_mstatus),
        .mie(csr_mie),
        .mip(csr_mip),
        .interrupt_pending(interrupt_pending),
        .interrupt_cause(interrupt_cause),
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
        .interrupt_taken(interrupt_taken),
        .mret_instruction(mret_instruction),
        .ecall_exception(ecall_exception),
        .ebreak_exception(ebreak_exception),
        .timer_interrupt(timer_interrupt),
        .software_interrupt(software_interrupt),
        .external_interrupt(external_interrupt),
        .mstatus(csr_mstatus),
        .mie(csr_mie),
        .mip(csr_mip),
        .mtvec(csr_mtvec),
        .mepc(csr_mepc)
    );

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
        .pc_input(id_ex_inst0_pc_out),
        .forward_a(forward_a),
        .forward_b(forward_b),
        .ex_mem_result(ex_mem_inst0_exec_output_out),
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
    .mtvec(csr_mtvec),
    .mepc(csr_mepc),
        .interrupt_taken(interrupt_taken),
        .mret_instruction(mret_instruction),
        .ecall_exception(ecall_exception),
        .ebreak_exception(ebreak_exception)
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
    wire [5:0] ex_mem_inst0_instr_id_out;
    wire ex_mem_inst0_rd_valid_out;
    wire [31:0] ex_mem_inst0_instruction_out;
    wire [11:0] ex_mem_inst0_csr_addr_out;
    wire ex_mem_inst0_csr_read_enable_out;
    wire ex_mem_inst0_csr_write_enable_out;
    wire [31:0] ex_mem_inst0_csr_write_data_out;
    wire [31:0] ex_mem_inst0_csr_read_data_out;
    wire ex_mem_inst0_interrupt_taken_out;
    wire ex_mem_inst0_mret_instruction_out;
    wire ex_mem_inst0_ecall_exception_out;
    wire ex_mem_inst0_ebreak_exception_out;

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
        .instr_id_in(id_ex_inst0_instr_id_out),
        .rd_valid_in(id_ex_inst0_rd_valid_out),
        .instruction_in(id_ex_inst0_instruction_out),
        .csr_addr_in(csr_addr),
        .csr_read_enable_in(csr_read_enable),
        .csr_write_enable_in(csr_write_enable),
        .csr_write_data_in(csr_write_data),
        .csr_read_data_in(csr_read_data),
        .interrupt_taken_in(interrupt_taken),
        .mret_instruction_in(mret_instruction),
        .ecall_exception_in(ecall_exception),
        .ebreak_exception_in(ebreak_exception),
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
        .rd_valid_out(ex_mem_inst0_rd_valid_out),
        .instruction_out(ex_mem_inst0_instruction_out),
        .csr_addr_out(ex_mem_inst0_csr_addr_out),
        .csr_read_enable_out(ex_mem_inst0_csr_read_enable_out),
        .csr_write_enable_out(ex_mem_inst0_csr_write_enable_out),
        .csr_write_data_out(ex_mem_inst0_csr_write_data_out),
        .csr_read_data_out(ex_mem_inst0_csr_read_data_out),
        .interrupt_taken_out(ex_mem_inst0_interrupt_taken_out),
        .mret_instruction_out(ex_mem_inst0_mret_instruction_out),
        .ecall_exception_out(ex_mem_inst0_ecall_exception_out),
        .ebreak_exception_out(ex_mem_inst0_ebreak_exception_out)
    );

    // Instantiate Memory Unit
    wire mem_unit_inst0_wr_enable_out;
    wire mem_unit_inst0_read_enable_out;
    wire [31:0] mem_unit_inst0_wr_data_out;
    wire [31:0] mem_unit_inst0_read_addr_out;
    wire [31:0] mem_unit_inst0_wr_addr_out;
    wire [3:0] mem_unit_inst0_write_byte_enable_out;  // Write byte enables
    wire [2:0] mem_unit_inst0_load_type_out;          // Load type

    assign module_mem_wr_en = mem_unit_inst0_wr_enable_out;
    assign module_mem_rd_en = mem_unit_inst0_read_enable_out;
    assign module_write_addr = mem_unit_inst0_wr_addr_out;
    assign module_read_addr = mem_unit_inst0_read_addr_out;
    assign module_wr_data_out = mem_unit_inst0_wr_data_out;
    assign module_write_byte_enable = mem_unit_inst0_write_byte_enable_out;
    assign module_load_type = mem_unit_inst0_load_type_out;

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
    wire [5:0] mem_wb_inst0_instr_id_out;
    wire mem_wb_inst0_rd_valid_out;
    wire [31:0] mem_wb_inst0_mem_data_out;
    wire [31:0] mem_wb_inst0_instruction_out;
    wire [11:0] mem_wb_inst0_csr_addr_out;
    wire mem_wb_inst0_csr_read_enable_out;
    wire mem_wb_inst0_csr_write_enable_out;
    wire [31:0] mem_wb_inst0_csr_write_data_out;
    wire [31:0] mem_wb_inst0_csr_read_data_out;
    wire mem_wb_inst0_interrupt_taken_out;
    wire mem_wb_inst0_mret_instruction_out;
    wire mem_wb_inst0_ecall_exception_out;
    wire mem_wb_inst0_ebreak_exception_out;
    wire mem_wb_inst0_mem_read_enable_out;
    wire mem_wb_inst0_mem_write_enable_out;
    wire [3:0] mem_wb_inst0_write_byte_enable_out;
    wire [2:0] mem_wb_inst0_load_type_out;
    wire [31:0] mem_wb_inst0_mem_wr_data_out;

    // Add wires for store-load forwarding
    wire store_load_hazard;
    wire [31:0] forwarded_store_data;

    // Instantiate store-load hazard detector
    store_load_detector store_load_detector_inst0 (
        .load_instr_id(ex_mem_inst0_instr_id_out),
        .load_addr(ex_mem_inst0_mem_addr_out),
        .prev_store_instr_id(mem_wb_inst0_instr_id_out),
        .prev_store_addr(mem_wb_inst0_mem_addr_out),
        .store_load_hazard(store_load_hazard),
        .forwarded_data(forwarded_store_data),
        .rs2_value(ex_mem_inst0_rs2_value_out)  // Forwarded store data
    );

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
        .exec_output_in(ex_mem_inst0_exec_output_out),
        .jump_signal_in(ex_mem_inst0_jump_signal_out),
        .jump_addr_in(ex_mem_inst0_jump_addr_out),
        .instr_id_in(ex_mem_inst0_instr_id_out),
        .rd_valid_in(ex_mem_inst0_rd_valid_out),
        .mem_data_in(module_read_data_in),  // Connect memory data
        .mem_wr_data_in(mem_unit_inst0_wr_data_out),
        .instruction_in(ex_mem_inst0_instruction_out),
        .csr_addr_in(ex_mem_inst0_csr_addr_out),
        .csr_read_enable_in(ex_mem_inst0_csr_read_enable_out),
        .csr_write_enable_in(ex_mem_inst0_csr_write_enable_out),
        .csr_write_data_in(ex_mem_inst0_csr_write_data_out),
        .csr_read_data_in(ex_mem_inst0_csr_read_data_out),
        .interrupt_taken_in(ex_mem_inst0_interrupt_taken_out),
        .mret_instruction_in(ex_mem_inst0_mret_instruction_out),
        .ecall_exception_in(ex_mem_inst0_ecall_exception_out),
        .ebreak_exception_in(ex_mem_inst0_ebreak_exception_out),
        .mem_read_enable_in(mem_unit_inst0_read_enable_out),
        .mem_write_enable_in(mem_unit_inst0_wr_enable_out),
        .write_byte_enable_in(mem_unit_inst0_write_byte_enable_out),
        .load_type_in(mem_unit_inst0_load_type_out),

        // Store-load forwarding connections
        .store_load_hazard(store_load_hazard),
        .store_data(forwarded_store_data),

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
        .mem_data_out(mem_wb_inst0_mem_data_out),  // Output to WB stage
        .mem_wr_data_out(mem_wb_inst0_mem_wr_data_out),
        .instruction_out(mem_wb_inst0_instruction_out),
        .csr_addr_out(mem_wb_inst0_csr_addr_out),
        .csr_read_enable_out(mem_wb_inst0_csr_read_enable_out),
        .csr_write_enable_out(mem_wb_inst0_csr_write_enable_out),
        .csr_write_data_out(mem_wb_inst0_csr_write_data_out),
        .csr_read_data_out(mem_wb_inst0_csr_read_data_out),
        .interrupt_taken_out(mem_wb_inst0_interrupt_taken_out),
        .mret_instruction_out(mem_wb_inst0_mret_instruction_out),
        .ecall_exception_out(mem_wb_inst0_ecall_exception_out),
        .ebreak_exception_out(mem_wb_inst0_ebreak_exception_out),
        .mem_read_enable_out(mem_wb_inst0_mem_read_enable_out),
        .mem_write_enable_out(mem_wb_inst0_mem_write_enable_out),
        .write_byte_enable_out(mem_wb_inst0_write_byte_enable_out),
        .load_type_out(mem_wb_inst0_load_type_out)
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

    // RVFI (RISC-V Formal Interface) implementation for formal verification
    reg [63:0] rvfi_order_reg;

    wire rvfi_commit_valid = (mem_wb_inst0_instr_id_out != INSTR_INVALID);

    // Update order counter on valid instructions
    always @(posedge clk) begin
        if (rst) begin
            rvfi_order_reg <= 64'b0;
        end else if (rvfi_commit_valid) begin
            rvfi_order_reg <= rvfi_order_reg + 1;
        end
    end

    // RVFI base channel outputs
    assign rvfi_valid = rvfi_commit_valid;
    assign rvfi_order = rvfi_order_reg;
    assign rvfi_insn  = mem_wb_inst0_instruction_out;
    assign rvfi_trap  = mem_wb_inst0_ecall_exception_out || mem_wb_inst0_ebreak_exception_out;
    assign rvfi_halt  = 1'b0;
    assign rvfi_intr  = mem_wb_inst0_interrupt_taken_out;

    assign rvfi_mode = 2'b11; // Machine mode
    assign rvfi_ixl  = 2'b01; // RV32

    assign rvfi_rs1_addr  = mem_wb_inst0_rs1_addr_out;
    assign rvfi_rs2_addr  = mem_wb_inst0_rs2_addr_out;
    assign rvfi_rs1_rdata = mem_wb_inst0_rs1_value_out;
    assign rvfi_rs2_rdata = mem_wb_inst0_rs2_value_out;
    assign rvfi_rd_addr   = wb_inst0_rd_addr_out;
    assign rvfi_rd_wdata  = wb_inst0_wr_en_out ? wb_inst0_rd_value_out : 32'b0;

    assign rvfi_pc_rdata = mem_wb_inst0_pc_out;
    assign rvfi_pc_wdata = mem_wb_inst0_jump_signal_out ? mem_wb_inst0_jump_addr_out
                                                        : mem_wb_inst0_pc_out + 32'd4;

    wire rvfi_mem_is_load  = rvfi_commit_valid && mem_wb_inst0_mem_read_enable_out;
    wire rvfi_mem_is_store = rvfi_commit_valid && mem_wb_inst0_mem_write_enable_out;

    function automatic [3:0] rvfi_load_mask(input [2:0] load_type, input [1:0] addr);
        begin
            case (load_type)
                3'b000, 3'b100: rvfi_load_mask = 4'b0001 << addr;
                3'b001, 3'b101: rvfi_load_mask = (addr[0] == 1'b0) ? (4'b0011 << addr[1:0]) : 4'b0000;
                3'b010:         rvfi_load_mask = 4'b1111;
                default:        rvfi_load_mask = 4'b0000;
            endcase
        end
    endfunction

    wire [3:0] rvfi_mem_rmask_value = rvfi_load_mask(mem_wb_inst0_load_type_out,
                                                      mem_wb_inst0_mem_addr_out[1:0]);

    assign rvfi_mem_addr  = (rvfi_mem_is_load || rvfi_mem_is_store) ? mem_wb_inst0_mem_addr_out : 32'b0;
    assign rvfi_mem_rmask = rvfi_mem_is_load  ? rvfi_mem_rmask_value : 4'b0000;
    assign rvfi_mem_rdata = rvfi_mem_is_load  ? mem_wb_inst0_mem_data_out : 32'b0;
    assign rvfi_mem_wmask = rvfi_mem_is_store ? mem_wb_inst0_write_byte_enable_out : 4'b0000;
    assign rvfi_mem_wdata = rvfi_mem_is_store ? mem_wb_inst0_mem_wr_data_out : 32'b0;

    // CSR RVFI channels
    wire csr_commit_read  = rvfi_commit_valid && mem_wb_inst0_csr_read_enable_out;
    wire csr_commit_write = rvfi_commit_valid && mem_wb_inst0_csr_write_enable_out;
    wire [11:0] csr_addr_commit = mem_wb_inst0_csr_addr_out;
    wire [31:0] csr_rdata_commit = mem_wb_inst0_csr_read_data_out;
    wire [31:0] csr_wdata_commit = mem_wb_inst0_csr_write_data_out;

    function automatic [31:0] csr_mask;
        input cond;
        begin
            csr_mask = cond ? 32'hFFFF_FFFF : 32'h0000_0000;
        end
    endfunction

    assign rvfi_csr_mstatus_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MSTATUS));
    assign rvfi_csr_mstatus_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MSTATUS)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mstatus_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MSTATUS));
    assign rvfi_csr_mstatus_wdata = (csr_commit_write && (csr_addr_commit == CSR_MSTATUS)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_misa_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MISA));
    assign rvfi_csr_misa_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MISA)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_misa_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MISA));
    assign rvfi_csr_misa_wdata = (csr_commit_write && (csr_addr_commit == CSR_MISA)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_mie_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MIE));
    assign rvfi_csr_mie_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MIE)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mie_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MIE));
    assign rvfi_csr_mie_wdata = (csr_commit_write && (csr_addr_commit == CSR_MIE)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_mtvec_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MTVEC));
    assign rvfi_csr_mtvec_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MTVEC)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mtvec_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MTVEC));
    assign rvfi_csr_mtvec_wdata = (csr_commit_write && (csr_addr_commit == CSR_MTVEC)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_mscratch_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MSCRATCH));
    assign rvfi_csr_mscratch_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MSCRATCH)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mscratch_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MSCRATCH));
    assign rvfi_csr_mscratch_wdata = (csr_commit_write && (csr_addr_commit == CSR_MSCRATCH)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_mepc_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MEPC));
    assign rvfi_csr_mepc_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MEPC)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mepc_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MEPC));
    assign rvfi_csr_mepc_wdata = (csr_commit_write && (csr_addr_commit == CSR_MEPC)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_mcause_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MCAUSE));
    assign rvfi_csr_mcause_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MCAUSE)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mcause_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MCAUSE));
    assign rvfi_csr_mcause_wdata = (csr_commit_write && (csr_addr_commit == CSR_MCAUSE)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_mtval_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MTVAL));
    assign rvfi_csr_mtval_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MTVAL)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mtval_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MTVAL));
    assign rvfi_csr_mtval_wdata = (csr_commit_write && (csr_addr_commit == CSR_MTVAL)) ? csr_wdata_commit : 32'b0;

    assign rvfi_csr_mip_rmask = csr_mask(csr_commit_read  && (csr_addr_commit == CSR_MIP));
    assign rvfi_csr_mip_rdata = (csr_commit_read  && (csr_addr_commit == CSR_MIP)) ? csr_rdata_commit : 32'b0;
    assign rvfi_csr_mip_wmask = csr_mask(csr_commit_write && (csr_addr_commit == CSR_MIP));
    assign rvfi_csr_mip_wdata = (csr_commit_write && (csr_addr_commit == CSR_MIP)) ? csr_wdata_commit : 32'b0;

endmodule
