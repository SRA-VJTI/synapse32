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
    output reg rd_valid_out
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
        end
    end
    
endmodule