module IF_ID(
    input wire clk,
    input wire rst,
    input wire [31:0] pc_in,
    input wire [31:0] instruction_in,
    input wire instr_page_fault_in,
    input wire flush,
    input wire stall,                   // Added stall input
    output reg [31:0] pc_out,
    output reg [31:0] instruction_out,
    output reg instruction_valid_out,
    output reg instr_page_fault_out
);
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            pc_out <= 32'b0;
            instruction_out <= 32'h00000013;
            instruction_valid_out <= 1'b0;
            instr_page_fault_out <= 1'b0;
        end else if (flush) begin
            pc_out <= pc_in;
            instruction_out <= 32'h00000013;
            instruction_valid_out <= 1'b0;
            instr_page_fault_out <= 1'b0;
        end else if (stall) begin
            // If stalling, maintain current values
            pc_out <= pc_out;
            instruction_out <= instruction_out;
            instruction_valid_out <= instruction_valid_out;
            instr_page_fault_out <= instr_page_fault_out;
        end else begin
            pc_out <= pc_in;
            instruction_out <= instruction_in;
            instruction_valid_out <= 1'b1;
            instr_page_fault_out <= instr_page_fault_in;
        end
    end
endmodule
