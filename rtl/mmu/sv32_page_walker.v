`default_nettype none

module sv32_page_walker (
    input  wire        translate_enable,
    input  wire [31:0] virtual_addr,
    input  wire [31:0] satp,
    input  wire [31:0] l1_pte_addr,
    input  wire [31:0] l1_pte_value,
    input  wire        l1_pte_backed,
    input  wire [31:0] l0_pte_addr,
    input  wire [31:0] l0_pte_value,
    input  wire        l0_pte_backed,
    output reg  [31:0] phys_addr,
    output reg         addr_valid,
    output reg  [31:0] leaf_pte_addr,
    output reg  [31:0] leaf_pte_value
);

    wire [9:0] vpn0 = virtual_addr[21:12];

    always @(*) begin
        phys_addr     = virtual_addr;
        addr_valid    = 1'b1;
        leaf_pte_addr = 32'b0;
        leaf_pte_value = 32'b0;

        if (translate_enable) begin
            addr_valid = 1'b0;

            if (l1_pte_backed && l1_pte_value[0] &&
                (l1_pte_value[31:30] == 2'b00) &&
                !(!l1_pte_value[1] && l1_pte_value[2])) begin
                if (l1_pte_value[1] || l1_pte_value[3]) begin
                    if (l1_pte_value[19:10] == 10'b0) begin
                        addr_valid = 1'b1;
                        phys_addr = {l1_pte_value[29:20], vpn0, virtual_addr[11:0]};
                        leaf_pte_addr = l1_pte_addr;
                        leaf_pte_value = l1_pte_value;
                    end
                    end else if (l0_pte_backed && l0_pte_value[0] &&
                             (l0_pte_value[31:30] == 2'b00) &&
                             !(!l0_pte_value[1] && l0_pte_value[2]) &&
                             (l0_pte_value[1] || l0_pte_value[3])) begin
                    addr_valid = 1'b1;
                    phys_addr = {l0_pte_value[29:10], virtual_addr[11:0]};
                    leaf_pte_addr = l0_pte_addr;
                    leaf_pte_value = l0_pte_value;
                end
            end
        end
    end

endmodule
