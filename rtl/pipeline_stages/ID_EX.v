module ID_EX(
    input wire clk,
    input wire rst,
    input wire rs1_valid_in,
    input wire rs2_valid_in,
    input wire [31:0] imm_in,
    input wire [4:0] rs1_addr_in,
    input wire [4:0] rs2_addr_in,
    input wire [4:0] rd_addr_in,
    input wire [6:0] opcode_in,
    input wire [5:0] instr_id_in,
    output reg rs1_valid_out,
    output reg rs2_valid_out,
    output reg [31:0] imm_out,
    output reg [4:0] rs1_addr_out,
    output reg [4:0] rs2_addr_out,
    output reg [4:0] rd_addr_out,
    output reg [6:0] opcode_out,
    output reg [5:0] instr_id_out
);
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            rs1_valid_out <= 1'b0;
            rs2_valid_out <= 1'b0;
            imm_out <= 32'b0;
            rs1_addr_out <= 5'b0;
            rs2_addr_out <= 5'b0;
            rd_addr_out <= 5'b0;
            opcode_out <= 7'b0;
            instr_id_out <= 6'b0;
        end else begin
            rs1_valid_out <= rs1_valid_in;
            rs2_valid_out <= rs2_valid_in;
            imm_out <= imm_in;
            rs1_addr_out <= rs1_addr_in;
            rs2_addr_out <= rs2_addr_in;
            rd_addr_out <= rd_addr_in;
            opcode_out <= opcode_in;
            instr_id_out <= instr_id_in; // Store the instruction ID
        end
    end
endmodule