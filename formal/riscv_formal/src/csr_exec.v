`default_nettype none
`include "instr_defines.vh"
module csr_exec (
    input wire [5:0] instr_id,
    input wire [31:0] rs1_value,
    input wire [4:0] rs1_addr,     // For immediate value
    input wire [31:0] csr_read_data,
    output reg [31:0] csr_write_data,
    output reg csr_write_enable,
    output reg [31:0] rd_value
);

    wire [31:0] uimm = {27'b0, rs1_addr}; // Zero-extended immediate

    always @(*) begin
        // Default values
        csr_write_data = 32'b0;
        csr_write_enable = 1'b0;
        rd_value = csr_read_data; // Always read current CSR value to rd

        case (instr_id)
            INSTR_CSRRW: begin
                csr_write_data = rs1_value;
                csr_write_enable = 1'b1;
            end
            INSTR_CSRRS: begin
                csr_write_data = csr_read_data | rs1_value;
                csr_write_enable = (rs1_addr != 5'b0); // Don't write if rs1=x0
            end
            INSTR_CSRRC: begin
                csr_write_data = csr_read_data & (~rs1_value);
                csr_write_enable = (rs1_addr != 5'b0); // Don't write if rs1=x0
            end
            INSTR_CSRRWI: begin
                csr_write_data = uimm;
                csr_write_enable = 1'b1;
            end
            INSTR_CSRRSI: begin
                csr_write_data = csr_read_data | uimm;
                csr_write_enable = (rs1_addr != 5'b0); // Don't write if uimm=0
            end
            INSTR_CSRRCI: begin
                csr_write_data = csr_read_data & (~uimm);
                csr_write_enable = (rs1_addr != 5'b0); // Don't write if uimm=0
            end
            default: begin
                csr_write_data = 32'b0; // No CSR operation
                csr_write_enable = 1'b0; // No write enable
            end
        endcase
    end

endmodule