module EX_MEM (
    input wire clk,
    input wire rst,
    input wire [4:0] rs1_addr_in,
    input wire [4:0] rs2_addr_in,
    input wire [4:0] rd_addr_in,
    input wire [31:0] rs1_value_in,
    input wire [31:0] rs2_value_in,
    input wire [31:0] pc_in,
    input wire [31:0] mem_addr_in,
    input wire [31:0] exec_output_in,
    input wire jump_signal_in,
    input wire [31:0] jump_addr_in,
    input wire [5:0] instr_id_in,
    input wire rd_valid_in,
    input wire [31:0] instruction_in,
    input wire [11:0] csr_addr_in,
    input wire csr_read_enable_in,
    input wire csr_write_enable_in,
    input wire [31:0] csr_write_data_in,
    input wire [31:0] csr_read_data_in,
    input wire interrupt_taken_in,
    input wire mret_instruction_in,
    input wire ecall_exception_in,
    input wire ebreak_exception_in,
    output reg [4:0] rs1_addr_out,
    output reg [4:0] rs2_addr_out,
    output reg [4:0] rd_addr_out,
    output reg [31:0] rs1_value_out,
    output reg [31:0] rs2_value_out,
    output reg [31:0] pc_out,
    output reg [31:0] mem_addr_out,
    output reg [31:0] exec_output_out,
    output reg jump_signal_out,
    output reg [31:0] jump_addr_out,
    output reg [5:0] instr_id_out,
    output reg rd_valid_out,
    output reg [31:0] instruction_out,
    output reg [11:0] csr_addr_out,
    output reg csr_read_enable_out,
    output reg csr_write_enable_out,
    output reg [31:0] csr_write_data_out,
    output reg [31:0] csr_read_data_out,
    output reg interrupt_taken_out,
    output reg mret_instruction_out,
    output reg ecall_exception_out,
    output reg ebreak_exception_out
);

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            rs1_addr_out <= 5'b0;
            rs2_addr_out <= 5'b0;
            rd_addr_out <= 5'b0;
            rs1_value_out <= 32'b0;
            rs2_value_out <= 32'b0;
            pc_out <= 32'b0;
            mem_addr_out <= 32'b0;
            exec_output_out <= 32'b0;
            jump_signal_out <= 1'b0;
            jump_addr_out <= 32'b0;
            instr_id_out <= 6'b0;
            rd_valid_out <= 1'b0;
            instruction_out <= 32'b0;
            csr_addr_out <= 12'b0;
            csr_read_enable_out <= 1'b0;
            csr_write_enable_out <= 1'b0;
            csr_write_data_out <= 32'b0;
            csr_read_data_out <= 32'b0;
            interrupt_taken_out <= 1'b0;
            mret_instruction_out <= 1'b0;
            ecall_exception_out <= 1'b0;
            ebreak_exception_out <= 1'b0;
        end else begin
            rs1_addr_out <= rs1_addr_in;
            rs2_addr_out <= rs2_addr_in;
            rd_addr_out <= rd_addr_in;
            rs1_value_out <= rs1_value_in;
            rs2_value_out <= rs2_value_in;
            pc_out <= pc_in;
            mem_addr_out <= mem_addr_in;
            exec_output_out <= exec_output_in;
            jump_signal_out <= jump_signal_in;
            jump_addr_out <= jump_addr_in;
            instr_id_out <= instr_id_in;    
            rd_valid_out <= rd_valid_in;
            instruction_out <= instruction_in;
            csr_addr_out <= csr_addr_in;
            csr_read_enable_out <= csr_read_enable_in;
            csr_write_enable_out <= csr_write_enable_in;
            csr_write_data_out <= csr_write_data_in;
            csr_read_data_out <= csr_read_data_in;
            interrupt_taken_out <= interrupt_taken_in;
            mret_instruction_out <= mret_instruction_in;
            ecall_exception_out <= ecall_exception_in;
            ebreak_exception_out <= ebreak_exception_in;
        end
    end
    
endmodule
