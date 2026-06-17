`default_nettype none

module sv32_data_check (
    input  wire        translate_enable,
    input  wire        addr_valid_in,
    input  wire [1:0]  privilege_mode,
    input  wire        sum,
    input  wire        mxr,
    input  wire        data_rd_en,
    input  wire        data_wr_req,
    input  wire [31:0] leaf_pte,
    output reg         load_page_fault,
    output reg         store_page_fault,
    output reg         update_accessed,
    output reg         update_dirty
);

    localparam PRIV_U = 2'b00;
    localparam PRIV_S = 2'b01;

    reg effective_read_ok;
    reg permission_fault;

    always @(*) begin
        load_page_fault = 1'b0;
        store_page_fault = 1'b0;
        update_accessed = 1'b0;
        update_dirty = 1'b0;
        effective_read_ok = 1'b0;
        permission_fault = 1'b0;

        if (translate_enable) begin
            if (!addr_valid_in) begin
                load_page_fault = data_rd_en;
                store_page_fault = data_wr_req;
            end else begin
                effective_read_ok = leaf_pte[1] || (mxr && leaf_pte[3]);
                permission_fault = !leaf_pte[0] ||
                                   ((privilege_mode == PRIV_U) && !leaf_pte[4]) ||
                                   ((privilege_mode == PRIV_S) && leaf_pte[4] && !sum) ||
                                   ((data_rd_en && !data_wr_req) && !effective_read_ok) ||
                                   (data_wr_req && !leaf_pte[2]);
                if (permission_fault) begin
                    load_page_fault = data_rd_en;
                    store_page_fault = data_wr_req;
                end else begin
                    update_accessed = (data_rd_en || data_wr_req) && !leaf_pte[6];
                    update_dirty = data_wr_req && !leaf_pte[7];
                end
            end
        end
    end

endmodule
