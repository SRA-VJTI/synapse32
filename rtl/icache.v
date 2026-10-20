`default_nettype none
`include "memory_map.vh"
// Set-associative instruction cache in front of the fetch adapter, physically tagged. The arrays are
// read at the clock edge with the next PC, so a hit answers in the request's cycle; the set index lies
// within the 4 KB page offset, so the virtual next PC gives the physical index.
module icache #(
    parameter NUM_WAYS = 4,
    parameter SET_INDEX_BITS = 6,
    parameter WORD_OFFSET_BITS = 2
) (
    input wire clk,
    input wire rst,
    input wire flush,           // FENCE.I
    input wire [31:0] next_pc,  // Address the PC loads at this edge

    // Core side
    input wire req,
    input wire [31:0] addr,
    output wire gnt,
    output wire rvalid,
    output wire [31:0] rdata,

    // Memory side
    output wire mem_req,
    output wire [31:0] mem_addr,
    input wire mem_gnt,
    input wire mem_rvalid,
    input wire [31:0] mem_rdata
);
    localparam SETS = 1 << SET_INDEX_BITS;
    localparam WORD_INDEX_BITS = SET_INDEX_BITS + WORD_OFFSET_BITS;
    localparam WAY_WORDS = 1 << WORD_INDEX_BITS;
    localparam TAG_BITS = 30 - WORD_INDEX_BITS;
    localparam LINE_ADDR_BITS = 30 - WORD_OFFSET_BITS;
    localparam WAY_BITS = (NUM_WAYS < 3) ? 1 :
                          (NUM_WAYS < 5) ? 2 :
                          (NUM_WAYS < 9) ? 3 : 4;
    localparam [31:0] LAST_WAY_FULL = NUM_WAYS - 1;
    localparam [WAY_BITS-1:0] LAST_WAY = LAST_WAY_FULL[WAY_BITS-1:0];

    localparam IDLE = 2'd0;
    localparam FILL = 2'd1;
    localparam REFILL = 2'd2;
    localparam BYPASS = 2'd3;

    // Multi-word lines, at least two sets, set index and word offset within the 4 KB page offset,
    // at most 16 ways.
    generate
        if ((WORD_OFFSET_BITS < 1) || (SET_INDEX_BITS < 1) || (WORD_INDEX_BITS > 10) || (NUM_WAYS < 1) ||
            (NUM_WAYS > 16)) begin : g_invalid_parameters
            icache_parameters_out_of_range invalid_parameters ();
        end
    endgenerate

    reg [NUM_WAYS*32-1:0] data_mem [0:WAY_WORDS-1];
    reg [NUM_WAYS*TAG_BITS-1:0] tag_mem [0:SETS-1];
    reg [NUM_WAYS*32-1:0] data_rd_q;
    reg [NUM_WAYS*TAG_BITS-1:0] tag_rd_q;
    reg [NUM_WAYS*SETS-1:0] valid_q;
    reg [NUM_WAYS-1:0] valid_rd_q;
    reg [WAY_BITS*SETS-1:0] victim_q;

    reg [1:0] state;
    reg [LINE_ADDR_BITS-1:0] fill_line;
    reg [WORD_OFFSET_BITS-1:0] fill_word;
    reg [WAY_BITS-1:0] fill_way;
    reg fill_dead;

    wire [WORD_INDEX_BITS-1:0] next_index = next_pc[WORD_INDEX_BITS+1:2];
    wire [SET_INDEX_BITS-1:0] next_set = next_pc[WORD_INDEX_BITS+1:WORD_OFFSET_BITS+2];
    wire [SET_INDEX_BITS-1:0] set = addr[WORD_INDEX_BITS+1:WORD_OFFSET_BITS+2];
    wire [TAG_BITS-1:0] tag = addr[31:WORD_INDEX_BITS+2];
    wire [SET_INDEX_BITS-1:0] fill_set = fill_line[SET_INDEX_BITS-1:0];
    wire [TAG_BITS-1:0] fill_tag = fill_line[LINE_ADDR_BITS-1:SET_INDEX_BITS];
    wire cacheable = `IS_INSTR_MEM(addr) || `IS_DATA_MEM(addr);

    reg [NUM_WAYS-1:0] way_hit;
    reg [31:0] hit_data;
    reg [WAY_BITS-1:0] victim;
    reg victim_found;
    integer i, j, k, m;

    // The arrays were read with this address as the next PC.
    wire lookup = req && cacheable && (state == IDLE);
    wire hit = lookup && |way_hit;
    wire miss = lookup && !(|way_hit);
    wire bypass_req = req && !cacheable && (state == IDLE);
    wire fill_write = (state == FILL) && mem_rvalid;
    wire fill_last = fill_write && (fill_word == {WORD_OFFSET_BITS{1'b1}});

    assign gnt = hit || (bypass_req && mem_gnt);
    assign rvalid = hit || (mem_rvalid && (bypass_req || (state == BYPASS)));
    assign rdata = hit ? hit_data : mem_rdata;
    assign mem_req = (state == FILL) || bypass_req;
    assign mem_addr = (state == FILL) ? {fill_line, fill_word, 2'b00} : addr;

    // Block RAM: one row holds every way, read whole; a fill writes its way's slice. No reset.
    always @(posedge clk) begin
        for (m = 0; m < NUM_WAYS; m = m + 1) begin
            if (fill_write && (fill_way == m[WAY_BITS-1:0])) begin
                data_mem[{fill_set, fill_word}][m*32 +: 32] <= mem_rdata;
            end
            if (fill_last && (fill_way == m[WAY_BITS-1:0])) begin
                tag_mem[fill_set][m*TAG_BITS +: TAG_BITS] <= fill_tag;
            end
        end
        data_rd_q <= data_mem[next_index];
        tag_rd_q <= tag_mem[next_set];
    end

    always @(*) begin
        hit_data = 32'b0;
        for (i = 0; i < NUM_WAYS; i = i + 1) begin
            way_hit[i] = valid_rd_q[i] && (tag_rd_q[i*TAG_BITS +: TAG_BITS] == tag);
            if (way_hit[i]) begin
                hit_data = data_rd_q[i*32 +: 32];
            end
        end
    end

    // An invalid way first, else the set's round-robin pointer.
    always @(*) begin
        victim = victim_q[set*WAY_BITS +: WAY_BITS];
        victim_found = 1'b0;
        for (j = 0; j < NUM_WAYS; j = j + 1) begin
            if (!valid_rd_q[j] && !victim_found) begin
                victim = j[WAY_BITS-1:0];
                victim_found = 1'b1;
            end
        end
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            valid_q <= {(NUM_WAYS*SETS){1'b0}};
            valid_rd_q <= {NUM_WAYS{1'b0}};
            victim_q <= {(WAY_BITS*SETS){1'b0}};
            state <= IDLE;
            fill_line <= {LINE_ADDR_BITS{1'b0}};
            fill_word <= {WORD_OFFSET_BITS{1'b0}};
            fill_way <= {WAY_BITS{1'b0}};
            fill_dead <= 1'b0;
        end else begin
            // Read with the arrays, so a line set valid at this edge reads valid only with its data.
            for (k = 0; k < NUM_WAYS; k = k + 1) begin
                valid_rd_q[k] <= !flush && valid_q[k*SETS + {{(32-SET_INDEX_BITS){1'b0}}, next_set}];
            end
            if (fill_last) begin
                victim_q[fill_set*WAY_BITS +: WAY_BITS] <=
                    (victim_q[fill_set*WAY_BITS +: WAY_BITS] == LAST_WAY) ? {WAY_BITS{1'b0}} :
                    victim_q[fill_set*WAY_BITS +: WAY_BITS] + 1'b1;
                if (!fill_dead && !flush) begin
                    valid_q[fill_way*SETS + fill_set] <= 1'b1;
                end
            end
            if (flush) begin
                valid_q <= {(NUM_WAYS*SETS){1'b0}};
            end
            case (state)
                IDLE: begin
                    if (miss) begin
                        state <= FILL;
                        fill_line <= addr[31:WORD_OFFSET_BITS+2];
                        fill_word <= {WORD_OFFSET_BITS{1'b0}};
                        fill_way <= victim;
                        fill_dead <= 1'b0;
                    end else if (bypass_req && mem_gnt && !mem_rvalid) begin
                        state <= BYPASS;
                    end
                end
                FILL: begin
                    // A fill that began before FENCE.I may hold words from before the writes it waited for.
                    if (flush) begin
                        fill_dead <= 1'b1;
                    end
                    if (fill_write) begin
                        fill_word <= fill_word + 1'b1;
                        if (fill_last) begin
                            state <= REFILL;
                        end
                    end
                end
                REFILL: begin
                    state <= IDLE;
                end
                BYPASS: begin
                    if (mem_rvalid) begin
                        state <= IDLE;
                    end
                end
            endcase
        end
    end
endmodule
