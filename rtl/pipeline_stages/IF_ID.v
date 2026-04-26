module IF_ID(
    input wire clk,
    input wire rst,
    input wire [31:0] pc_in,
    input wire [31:0] instruction_in,
    input wire stall,                   // Added stall input
    output reg [31:0] pc_out,
    output reg [31:0] instruction_out,
    output reg instruction_valid_out
);
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            pc_out <= 32'b0;
            instruction_out <= 32'h00000013;
            instruction_valid_out <= 1'b0;
        end else if (stall) begin
            // If stalling, maintain current values
            pc_out <= pc_out;
            instruction_out <= instruction_out;
            instruction_valid_out <= instruction_valid_out;
        end else begin
            pc_out <= pc_in;
            instruction_out <= instruction_in;
            instruction_valid_out <= 1'b1;
        end
    end
endmodule
