`default_nettype none

module sv32_instr_check (
    input  wire        translate_enable,
    input  wire        addr_valid_in,
    input  wire [1:0]  privilege_mode,
    input  wire [31:0] leaf_pte,
    output reg         page_fault,
    output reg         update_accessed
);

    localparam PRIV_U = 2'b00;
    localparam PRIV_S = 2'b01;

    always @(*) begin
        page_fault = 1'b0;
        update_accessed = 1'b0;

        if (translate_enable) begin
            if (!addr_valid_in ||
                !leaf_pte[3] ||
                ((privilege_mode == PRIV_U) && !leaf_pte[4]) ||
                ((privilege_mode == PRIV_S) && leaf_pte[4])) begin
                page_fault = 1'b1;
            end else if (!leaf_pte[6]) begin
                update_accessed = 1'b1;
            end
        end
    end

endmodule
