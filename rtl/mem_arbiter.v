`default_nettype none
// With MEM_PORTS 1, fetch and data share one memory port, one access at a time; a side keeps the port from request to
// response, and when both wait the side not served last goes first.
module mem_arbiter (
    input wire clk,
    input wire rst,

    // Fetch side (icache or its pass-through)
    input wire fetch_req,
    input wire [31:0] fetch_addr,
    output wire fetch_gnt,
    output wire fetch_rvalid,

    // Data side (dcache or its pass-through)
    input wire data_req,
    input wire [31:0] data_addr,
    input wire data_we,
    input wire [3:0] data_be,
    input wire [31:0] data_wdata,
    input wire [2:0] data_load_type,
    output wire data_gnt,
    output wire data_rvalid,

    // Memory port
    output wire mem_req,
    output wire [31:0] mem_addr,
    output wire mem_we,
    output wire [3:0] mem_be,
    output wire [31:0] mem_wdata,
    output wire [2:0] mem_load_type,
    output wire mem_instr,
    input wire mem_gnt,
    input wire mem_rvalid
);

    localparam [2:0] LOAD_WORD = 3'b010;

    reg waiting_q;      // presented, not yet granted
    reg pending_q;      // granted, response not yet back
    reg owner_data_q;   // the side presented last: 1 data, 0 fetch

    wire select_data = (waiting_q || pending_q) ? owner_data_q : data_req && (!fetch_req || !owner_data_q);
    wire grant = mem_req && mem_gnt;

    assign mem_req = (select_data ? data_req : fetch_req) && !pending_q;
    assign mem_addr = select_data ? data_addr : fetch_addr;
    assign mem_we = select_data && data_we;
    assign mem_be = select_data ? data_be : 4'b0;
    assign mem_wdata = select_data ? data_wdata : 32'b0;
    assign mem_load_type = select_data ? data_load_type : LOAD_WORD;
    assign mem_instr = !select_data;

    assign fetch_gnt = grant && !select_data;
    assign data_gnt = grant && select_data;
    // At latency 0 the response comes in the grant cycle, to the side selected then.
    assign fetch_rvalid = mem_rvalid && !select_data;
    assign data_rvalid = mem_rvalid && select_data;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            waiting_q <= 1'b0;
            pending_q <= 1'b0;
            owner_data_q <= 1'b0;
        end else begin
            if (mem_req) begin
                owner_data_q <= select_data;
            end
            waiting_q <= mem_req && !mem_gnt;
            if (grant && !mem_rvalid) begin
                pending_q <= 1'b1;
            end else if (mem_rvalid) begin
                pending_q <= 1'b0;
            end
        end
    end

endmodule
