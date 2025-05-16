`default_nettype none
module riscv_cpu (
    input wire clk,
    input wire rst,
    input wire [31:0] module_instr_in,
    output wire [31:0] module_pc_out
);

    // Instantiate the PC

    wire pc_inst0_jsignal_in;
    wire [31:0] pc_inst0_jump_in;
    wire [31:0] pc_inst0_out;

    pc pc_inst0 (
        .clk(clk),
        .reset(rst),
        .j_signal(pc_inst0_jsignal_in),
        .jump(pc_inst0_jump_in),
        .out(pc_inst0_out)
    );

    // Instantiate the IF_ID pipeline register
    wire [31:0] if_id_inst0_pc_in;
    wire [31:0] if_id_inst0_instruction_in;
    wire [31:0] if_id_inst0_pc_out;
    wire [31:0] if_id_inst0_instruction_out;
    IF_ID if_id_inst0 (
        .clk(clk),
        .rst(rst),
        .pc_in(if_id_inst0_pc_in),
        .instruction_in(if_id_inst0_instruction_in),
        .pc_out(if_id_inst0_pc_out),
        .instruction_out(if_id_inst0_instruction_out)
    );

    // PC - IF_ID pipeline register connections
    // Connect PC output to IF_ID input and module output
    assign if_id_inst0_pc_in = pc_inst0_out;
    assign if_id_inst0_instruction_in = module_instr_in;
    assign module_pc_out = pc_inst0_out;

    // Instantiate Decoder
    wire [31:0] decoder_inst0_instruction_in;
    wire [4:0] decoder_inst0_rs2_out;
    wire [4:0] decoder_inst0_rs1_out;
    wire [31:0] decoder_inst0_imm_out;
    wire [4:0] decoder_inst0_rd_out;
    wire decoder_inst0_rs1_valid_out;
    wire decoder_inst0_rs2_valid_out;
    wire [6:0] decoder_inst0_opcode_out;
    wire [5:0] decoder_inst0_instr_id_out;
    decoder decoder_inst0 (
        .instr(decoder_inst0_instruction_in),
        .rs2(decoder_inst0_rs2_out),
        .rs1(decoder_inst0_rs1_out),
        .imm(decoder_inst0_imm_out),
        .rd(decoder_inst0_rd_out),
        .rs1_valid(decoder_inst0_rs1_valid_out),
        .rs2_valid(decoder_inst0_rs2_valid_out),
        .opcode(decoder_inst0_opcode_out),
        .instr_id(decoder_inst0_instr_id_out)
    );

    // Decoder connections
    assign decoder_inst0_instruction_in = if_id_inst0_instruction_out;

    // Instantiate Register File

    wire [4:0] registerfile_inst0_rs1_addr_in;
    wire [4:0] registerfile_inst0_rs2_addr_in;
    wire [4:0] registerfile_inst0_rd_addr_in;
    wire registerfile_inst0_rs1_valid_in;
    wire registerfile_inst0_rs2_valid_in;
    wire [31:0] registerfile_inst0_rd_value_in;
    wire registerfile_inst0_wr_en_in;
    wire [31:0] registerfile_inst0_rs1_value_out;
    wire [31:0] registerfile_inst0_rs2_value_out;

    registerfile registerfile_inst0 (
        .clk(clk),
        .rs1(registerfile_inst0_rs1_addr_in),
        .rs2(registerfile_inst0_rs2_addr_in),
        .rs1_valid(registerfile_inst0_rs1_valid_in),
        .rs2_valid(registerfile_inst0_rs2_valid_in),
        .rd(registerfile_inst0_rd_addr_in),
        .wr_en(registerfile_inst0_wr_en_in),
        .rd_value(registerfile_inst0_rd_value_in),
        .rs1_value(registerfile_inst0_rs1_value_out),
        .rs2_value(registerfile_inst0_rs2_value_out)
    );

    // Instantiate ID_EX pipeline register
    wire id_ex_inst0_rs1_valid_in;
    wire id_ex_inst0_rs2_valid_in;
    wire [31:0] id_ex_inst0_imm_in;
    wire [4:0] id_ex_inst0_rs1_addr_in;
    wire [4:0] id_ex_inst0_rs2_addr_in;
    wire [4:0] id_ex_inst0_rd_addr_in;
    wire [6:0] id_ex_inst0_opcode_in;
    wire [5:0] id_ex_inst0_instr_id_in;
    wire id_ex_inst0_rs1_valid_out;
    wire id_ex_inst0_rs2_valid_out;
    wire [31:0] id_ex_inst0_imm_out;
    wire [4:0] id_ex_inst0_rs1_addr_out;
    wire [4:0] id_ex_inst0_rs2_addr_out;
    wire [4:0] id_ex_inst0_rd_addr_out;
    wire [6:0] id_ex_inst0_opcode_out;
    wire [5:0] id_ex_inst0_instr_id_out;

    // Connect Decoder outputs to ID_EX inputs
    assign id_ex_inst0_rs1_valid_in = decoder_inst0_rs1_valid_out;
    assign id_ex_inst0_rs2_valid_in = decoder_inst0_rs2_valid_out;
    assign id_ex_inst0_imm_in = decoder_inst0_imm_out;
    assign id_ex_inst0_rs1_addr_in = decoder_inst0_rs1_out;
    assign id_ex_inst0_rs2_addr_in = decoder_inst0_rs2_out;
    assign id_ex_inst0_rd_addr_in = decoder_inst0_rd_out;
    assign id_ex_inst0_opcode_in = decoder_inst0_opcode_out;
    assign id_ex_inst0_instr_id_in = decoder_inst0_instr_id_out;

    ID_EX id_ex_inst0 (
        .clk(clk),
        .rst(rst),
        .rs1_valid_in(id_ex_inst0_rs1_valid_in),
        .rs2_valid_in(id_ex_inst0_rs2_valid_in),
        .imm_in(id_ex_inst0_imm_in),
        .rs1_addr_in(id_ex_inst0_rs1_addr_in),
        .rs2_addr_in(id_ex_inst0_rs2_addr_in),
        .rd_addr_in(id_ex_inst0_rd_addr_in),
        .opcode_in(id_ex_inst0_opcode_in),
        .instr_id_in(id_ex_inst0_instr_id_in),
        .rs1_valid_out(id_ex_inst0_rs1_valid_out),
        .rs2_valid_out(id_ex_inst0_rs2_valid_out),
        .imm_out(id_ex_inst0_imm_out),
        .rs1_addr_out(id_ex_inst0_rs1_addr_out),
        .rs2_addr_out(id_ex_inst0_rs2_addr_out),
        .rd_addr_out(id_ex_inst0_rd_addr_out),
        .opcode_out(id_ex_inst0_opcode_out),
        .instr_id_out(id_ex_inst0_instr_id_out)
    );

    // Instantiate ALU


endmodule
