`default_nettype none

module registerfile (
    input wire clk,
    input wire [4:0] rs1,
    input wire [4:0] rs2,
    input wire rs1_valid,
    input wire rs2_valid,
    input wire [4:0] rd,
    input wire wr_en,
    input wire [31:0] rd_value,

    output reg [31:0] rs1_value,
    output reg [31:0] rs2_value
);

    reg [31:0] register_file[31:0];
    integer i;

    initial begin
        for (i = 0; i < 32; i = i + 1) begin
            register_file[i] = 0;
        end
    end

    // Combinational read with write-through forwarding
    always @(*) begin
        if (rs1_valid) begin
            if (rs1 == 5'b0) begin
                rs1_value = 32'b0;
            end else if (rs1 == rd && wr_en) begin
                rs1_value = rd_value; // Forwarding if rd is being written
            end else begin
                rs1_value = register_file[rs1];
            end
        end else begin
            rs1_value = 32'b0; // Default value if rs1 is not valid
        end

        if (rs2_valid) begin
            if (rs2 == 5'b0) begin
                rs2_value = 32'b0;
            end else if (rs2 == rd && wr_en) begin
                rs2_value = rd_value; // Forwarding if rd is being written
            end else begin
                rs2_value = register_file[rs2];
            end
        end else begin
            rs2_value = 32'b0; // Default value if rs2 is not valid
        end
    end

    // No reset, so FPGA tools map the array to LUT RAM; x0 is never written and reads as zero by address.
    always @(posedge clk) begin
        if (wr_en && rd != 5'b0) begin
            register_file[rd] <= rd_value;
        end
    end

endmodule
