`default_nettype none
// Sv32 MMU: a TLB in front of a walker that reads PTEs over the data memory interface, one level
// at a time. Fetch and data share the walker, data first since its instruction is older; the
// requesting stage waits until its *_ready is high.
module sv32_mmu (
    input wire clk,
    input wire rst,
    input wire flush_tlb,

    input wire [31:0] satp,
    input wire data_sum,
    input wire data_mxr,

    // Instruction side
    input wire instr_translate_enable,
    input wire [31:0] instr_virtual_addr,
    input wire [1:0] instr_priv_mode,
    output wire [31:0] instr_phys_addr,
    output wire instr_ready,
    output wire instr_page_fault,

    // Data side
    input wire data_translate_enable,
    input wire [31:0] data_virtual_addr,
    input wire data_rd_en,
    input wire data_wr_req,
    input wire [1:0] data_priv_mode,
    output wire [31:0] data_phys_addr,
    output wire data_ready,
    output wire data_load_page_fault,
    output wire data_store_page_fault,
    output wire [31:0] data_fault_addr,

    // Walk port on the data memory interface
    output wire walk_req,
    output wire [31:0] walk_addr,
    input wire walk_gnt,
    input wire walk_rvalid,
    input wire [31:0] walk_rdata
);

    localparam [1:0] WALK_IDLE = 2'd0;
    localparam [1:0] WALK_LEVEL1 = 2'd1;
    localparam [1:0] WALK_LEVEL0 = 2'd2;

    localparam SIDE_DATA = 1'b0;
    localparam SIDE_INSTR = 1'b1;

    wire [31:0] root_pt_base = {satp[19:0], 12'b0};

    // TLB lookup
    wire tlb_instr_hit;
    wire [31:0] tlb_instr_pte;
    wire tlb_instr_megapage;
    wire tlb_data_hit;
    wire [31:0] tlb_data_pte;
    wire tlb_data_megapage;

    reg fill_en;
    reg [31:0] fill_vaddr;
    reg [31:0] fill_pte;
    reg fill_megapage;

    sv32_tlb tlb_inst (
        .clk(clk),
        .rst(rst),
        .flush(flush_tlb),
        .instr_vaddr(instr_virtual_addr),
        .instr_hit(tlb_instr_hit),
        .instr_pte(tlb_instr_pte),
        .instr_megapage(tlb_instr_megapage),
        .data_vaddr(data_virtual_addr),
        .data_hit(tlb_data_hit),
        .data_pte(tlb_data_pte),
        .data_megapage(tlb_data_megapage),
        .fill_en(fill_en),
        .fill_vaddr(fill_vaddr),
        .fill_pte(fill_pte),
        .fill_megapage(fill_megapage)
    );

    // Walk faults are held for the faulting address until its requester moves on, never cached.
    reg instr_fault_valid;
    reg [31:0] instr_fault_vaddr;
    reg data_fault_valid;
    reg [31:0] data_fault_vaddr;

    wire instr_fault_match = instr_fault_valid && (instr_fault_vaddr[31:12] == instr_virtual_addr[31:12]);
    wire data_fault_match = data_fault_valid && (data_fault_vaddr[31:12] == data_virtual_addr[31:12]);

    // Permission checks on the leaf PTE
    wire instr_perm_fault;
    wire instr_update_accessed_unused;
    sv32_instr_check instr_perm_check (
        .translate_enable(instr_translate_enable && tlb_instr_hit),
        .addr_valid_in(1'b1),
        .privilege_mode(instr_priv_mode),
        .leaf_pte(tlb_instr_pte),
        .page_fault(instr_perm_fault),
        .update_accessed(instr_update_accessed_unused)
    );

    wire data_perm_load_fault;
    wire data_perm_store_fault;
    wire data_update_accessed_unused;
    wire data_update_dirty_unused;
    sv32_data_check data_perm_check (
        .translate_enable(data_translate_enable && tlb_data_hit),
        .addr_valid_in(1'b1),
        .privilege_mode(data_priv_mode),
        .sum(data_sum),
        .mxr(data_mxr),
        .data_rd_en(data_rd_en),
        .data_wr_req(data_wr_req),
        .leaf_pte(tlb_data_pte),
        .load_page_fault(data_perm_load_fault),
        .store_page_fault(data_perm_store_fault),
        .update_accessed(data_update_accessed_unused),
        .update_dirty(data_update_dirty_unused)
    );

    // Address translation outputs
    function [31:0] translated_addr;
        input [31:0] pte;
        input megapage;
        input [31:0] vaddr;
        begin
            translated_addr = megapage ? {pte[29:20], vaddr[21:12], vaddr[11:0]}
                                       : {pte[29:10], vaddr[11:0]};
        end
    endfunction

    assign instr_phys_addr = !instr_translate_enable ? instr_virtual_addr :
                             translated_addr(tlb_instr_pte, tlb_instr_megapage, instr_virtual_addr);
    assign data_phys_addr = !data_translate_enable ? data_virtual_addr :
                            translated_addr(tlb_data_pte, tlb_data_megapage, data_virtual_addr);
    assign data_fault_addr = data_virtual_addr;

    assign instr_ready = !instr_translate_enable || tlb_instr_hit || instr_fault_match;
    assign data_ready = !data_translate_enable || tlb_data_hit || data_fault_match;

    assign instr_page_fault = instr_translate_enable && (instr_perm_fault || instr_fault_match);
    // A write reports only the store/AMO fault, including an AMO's read half.
    assign data_load_page_fault = data_translate_enable &&
                                  (data_perm_load_fault ||
                                   (data_fault_match && data_rd_en && !data_wr_req));
    assign data_store_page_fault = data_translate_enable &&
                                   (data_perm_store_fault || (data_fault_match && data_wr_req));

    // Walker. While a fill is being written the lookups still miss, so no new walk starts.
    wire data_walk_needed = data_translate_enable && (data_rd_en || data_wr_req) &&
                            !tlb_data_hit && !data_fault_match && !fill_en;
    wire instr_walk_needed = instr_translate_enable && !tlb_instr_hit && !instr_fault_match && !fill_en;

    reg [1:0] walk_state;
    // A flush mid-walk may leave the entry it would fill stale, so the walk is abandoned.
    reg walk_aborted;
    reg walk_side;
    reg [31:0] walk_vaddr;
    reg [31:0] walk_level0_base;
    reg walk_accepted;

    assign walk_req = (walk_state != WALK_IDLE) && !walk_accepted;
    assign walk_addr = (walk_state == WALK_LEVEL1)
                       ? (root_pt_base + {20'b0, walk_vaddr[31:22], 2'b00})
                       : (walk_level0_base + {20'b0, walk_vaddr[21:12], 2'b00});

    // Usable PTE: V set, not W without R, and a PPN that fits 32-bit physical space.
    function pte_usable;
        input [31:0] pte;
        begin
            pte_usable = pte[0] && (pte[31:30] == 2'b00) && !(!pte[1] && pte[2]);
        end
    endfunction

    function pte_is_leaf;
        input [31:0] pte;
        begin
            pte_is_leaf = pte[1] || pte[3];
        end
    endfunction

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            walk_state <= WALK_IDLE;
            walk_side <= SIDE_DATA;
            walk_vaddr <= 32'b0;
            walk_level0_base <= 32'b0;
            walk_accepted <= 1'b0;
            walk_aborted <= 1'b0;
            fill_en <= 1'b0;
            fill_vaddr <= 32'b0;
            fill_pte <= 32'b0;
            fill_megapage <= 1'b0;
            instr_fault_valid <= 1'b0;
            instr_fault_vaddr <= 32'b0;
            data_fault_valid <= 1'b0;
            data_fault_vaddr <= 32'b0;
        end else begin
            fill_en <= 1'b0;
            if (flush_tlb && (walk_state != WALK_IDLE)) begin
                walk_aborted <= 1'b1;
            end

            // A held fault is dropped when its requester moves to another page or software fences.
            if (flush_tlb || !instr_translate_enable ||
                (instr_fault_valid && instr_fault_vaddr[31:12] != instr_virtual_addr[31:12])) begin
                instr_fault_valid <= 1'b0;
            end
            if (flush_tlb || !data_translate_enable ||
                (data_fault_valid && data_fault_vaddr[31:12] != data_virtual_addr[31:12])) begin
                data_fault_valid <= 1'b0;
            end

            case (walk_state)
                WALK_IDLE: begin
                    walk_accepted <= 1'b0;
                    walk_aborted <= 1'b0;
                    if (data_walk_needed) begin
                        walk_side <= SIDE_DATA;
                        walk_vaddr <= data_virtual_addr;
                        walk_state <= WALK_LEVEL1;
                    end else if (instr_walk_needed) begin
                        walk_side <= SIDE_INSTR;
                        walk_vaddr <= instr_virtual_addr;
                        walk_state <= WALK_LEVEL1;
                    end
                end
                WALK_LEVEL1, WALK_LEVEL0: begin
                    if (walk_gnt) begin
                        walk_accepted <= 1'b1;
                    end
                    if (walk_rvalid) begin
                        walk_accepted <= 1'b0;
                        if (walk_aborted || flush_tlb) begin
                            // Software fenced while this walk was in flight: drop the result.
                            walk_state <= WALK_IDLE;
                        end else if (!pte_usable(walk_rdata) ||
                            (pte_is_leaf(walk_rdata) && (walk_state == WALK_LEVEL1) &&
                             (walk_rdata[19:10] != 10'b0)) ||
                            (!pte_is_leaf(walk_rdata) && (walk_state == WALK_LEVEL0))) begin
                            // Invalid entry, misaligned megapage, or a pointer at the last level.
                            if (walk_side == SIDE_INSTR) begin
                                instr_fault_valid <= 1'b1;
                                instr_fault_vaddr <= walk_vaddr;
                            end else begin
                                data_fault_valid <= 1'b1;
                                data_fault_vaddr <= walk_vaddr;
                            end
                            walk_state <= WALK_IDLE;
                        end else if (pte_is_leaf(walk_rdata)) begin
                            fill_en <= 1'b1;
                            fill_vaddr <= walk_vaddr;
                            fill_pte <= walk_rdata;
                            fill_megapage <= (walk_state == WALK_LEVEL1);
                            walk_state <= WALK_IDLE;
                        end else begin
                            walk_level0_base <= {walk_rdata[29:10], 12'b0};
                            walk_state <= WALK_LEVEL0;
                        end
                    end
                end
                default: walk_state <= WALK_IDLE;
            endcase
        end
    end

endmodule
