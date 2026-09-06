`default_nettype none

module sv32_mmu (
    input  wire        instr_translate_enable,
    input  wire [31:0] instr_virtual_addr,
    input  wire [1:0]  instr_priv_mode,
    input  wire        data_translate_enable,
    input  wire [31:0] data_virtual_addr,
    input  wire        data_wr_req,
    input  wire        data_rd_en,
    input  wire [1:0]  data_priv_mode,
    input  wire [31:0] satp,
    input  wire        data_sum,
    input  wire        data_mxr,
    input  wire [31:0] instr_l1_pte_value,
    input  wire        instr_l1_pte_backed,
    input  wire [31:0] instr_l0_pte_value,
    input  wire        instr_l0_pte_backed,
    input  wire [31:0] data_l1_pte_value,
    input  wire        data_l1_pte_backed,
    input  wire [31:0] data_l0_pte_value,
    input  wire        data_l0_pte_backed,
    output wire [31:0] instr_l1_pte_addr,
    output wire [31:0] instr_l0_pte_addr,
    output wire [31:0] data_l1_pte_addr,
    output wire [31:0] data_l0_pte_addr,
    output wire [31:0] instr_phys_addr,
    output wire        instr_page_fault,
    output wire [31:0] data_phys_addr,
    output wire        data_load_page_fault,
    output wire        data_store_page_fault,
    output wire [31:0] data_fault_addr,
    output wire        instr_pte_update_req,
    output wire [31:0] instr_pte_update_addr,
    output wire [31:0] instr_pte_update_value,
    output wire        data_pte_update_req,
    output wire [31:0] data_pte_update_addr,
    output wire [31:0] data_pte_update_value
);

    wire [31:0] root_pt_base = {satp[19:0], 12'b0};

    assign instr_l1_pte_addr = root_pt_base + {20'b0, instr_virtual_addr[31:22], 2'b00};
    assign instr_l0_pte_addr = {instr_l1_pte_value[29:10], 12'b0} + {20'b0, instr_virtual_addr[21:12], 2'b00};
    assign data_l1_pte_addr = root_pt_base + {20'b0, data_virtual_addr[31:22], 2'b00};
    assign data_l0_pte_addr = {data_l1_pte_value[29:10], 12'b0} + {20'b0, data_virtual_addr[21:12], 2'b00};
    assign data_fault_addr = data_virtual_addr;

    wire        instr_addr_valid;
    wire [31:0] instr_leaf_pte_addr;
    wire [31:0] instr_leaf_pte_value;
    wire        instr_update_accessed;
    wire        data_addr_valid;
    wire [31:0] data_leaf_pte_addr;
    wire [31:0] data_leaf_pte_value;
    wire        data_update_accessed;
    wire        data_update_dirty;

    sv32_page_walker instr_page_walker (
        .translate_enable(instr_translate_enable),
        .virtual_addr(instr_virtual_addr),
        .satp(satp),
        .l1_pte_addr(instr_l1_pte_addr),
        .l1_pte_value(instr_l1_pte_value),
        .l1_pte_backed(instr_l1_pte_backed),
        .l0_pte_addr(instr_l0_pte_addr),
        .l0_pte_value(instr_l0_pte_value),
        .l0_pte_backed(instr_l0_pte_backed),
        .phys_addr(instr_phys_addr),
        .addr_valid(instr_addr_valid),
        .leaf_pte_addr(instr_leaf_pte_addr),
        .leaf_pte_value(instr_leaf_pte_value)
    );

    sv32_instr_check instr_perm_check (
        .translate_enable(instr_translate_enable),
        .addr_valid_in(instr_addr_valid),
        .privilege_mode(instr_priv_mode),
        .leaf_pte(instr_leaf_pte_value),
        .page_fault(instr_page_fault),
        .update_accessed(instr_update_accessed)
    );

    sv32_page_walker data_page_walker (
        .translate_enable(data_translate_enable),
        .virtual_addr(data_virtual_addr),
        .satp(satp),
        .l1_pte_addr(data_l1_pte_addr),
        .l1_pte_value(data_l1_pte_value),
        .l1_pte_backed(data_l1_pte_backed),
        .l0_pte_addr(data_l0_pte_addr),
        .l0_pte_value(data_l0_pte_value),
        .l0_pte_backed(data_l0_pte_backed),
        .phys_addr(data_phys_addr),
        .addr_valid(data_addr_valid),
        .leaf_pte_addr(data_leaf_pte_addr),
        .leaf_pte_value(data_leaf_pte_value)
    );

    sv32_data_check data_perm_check (
        .translate_enable(data_translate_enable),
        .addr_valid_in(data_addr_valid),
        .privilege_mode(data_priv_mode),
        .sum(data_sum),
        .mxr(data_mxr),
        .data_rd_en(data_rd_en),
        .data_wr_req(data_wr_req),
        .leaf_pte(data_leaf_pte_value),
        .load_page_fault(data_load_page_fault),
        .store_page_fault(data_store_page_fault),
        .update_accessed(data_update_accessed),
        .update_dirty(data_update_dirty)
    );

    assign instr_pte_update_req = instr_update_accessed;
    assign instr_pte_update_addr = instr_leaf_pte_addr;
    assign instr_pte_update_value = instr_leaf_pte_value | 32'h00000040;

    assign data_pte_update_req = data_update_accessed || data_update_dirty;
    assign data_pte_update_addr = data_leaf_pte_addr;
    assign data_pte_update_value = data_leaf_pte_value |
                                   (data_update_accessed ? 32'h00000040 : 32'h00000000) |
                                   (data_update_dirty ? 32'h00000080 : 32'h00000000);

endmodule
