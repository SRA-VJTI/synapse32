`default_nettype none
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
    output wire [31:0] module_write_addr
);

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
        .exec_output(ex_inst0_exec_output_out),
        .jump_signal(ex_inst0_jump_signal_out),
        .jump_addr(ex_inst0_jump_addr_out),
        .mem_addr(ex_inst0_mem_addr_out),
        .rs1_value_out(ex_inst0_rs1_value_out),
        .rs2_value_out(ex_inst0_rs2_value_out),
        .flush_pipeline(execution_flush)  // Connect the flush signal
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
    // Sets read and write enable signals based on instruction ID
    wire mem_unit_inst0_wr_enable_out;
    wire mem_unit_inst0_read_enable_out;
    wire [31:0] mem_unit_inst0_wr_data_out;
    wire [31:0] mem_unit_inst0_read_addr_out;
    wire [31:0] mem_unit_inst0_wr_addr_out;

    assign module_mem_wr_en = mem_unit_inst0_wr_enable_out;
    assign module_mem_rd_en = mem_unit_inst0_read_enable_out;
    assign module_write_addr = mem_unit_inst0_wr_addr_out;
    assign module_read_addr = mem_unit_inst0_read_addr_out;
    assign module_wr_data_out = mem_unit_inst0_wr_data_out;

    memory_unit mem_unit_inst0 (
        .instr_id(ex_mem_inst0_instr_id_out),
        .rs2_value(ex_mem_inst0_rs2_value_out),
        .mem_addr(ex_mem_inst0_mem_addr_out),
        .wr_enable(mem_unit_inst0_wr_enable_out),
        .read_enable(mem_unit_inst0_read_enable_out),
        .wr_data(mem_unit_inst0_wr_data_out),
        .read_addr(mem_unit_inst0_read_addr_out),
        .wr_addr(mem_unit_inst0_wr_addr_out)
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


`ifdef COCOTB_SIM
    // Add parameter to control FST file path
    reg [1023:0] dumpfile_path = "riscv_cpu.fst"; // Default path
    
    initial begin
        // Check for custom dump file name from plusargs
        if (!$value$plusargs("dumpfile=%s", dumpfile_path)) begin
            // Use default if not specified
            dumpfile_path = "riscv_cpu.fst";
        end
        
        // Set up wave dumping
        $dumpfile(dumpfile_path);
        $dumpvars(0, riscv_cpu);
        $display("FST dump file: %s", dumpfile_path);
    end
`endif

endmodule
