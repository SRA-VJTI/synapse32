`default_nettype none
`include "memory_map.vh"
// Set-associative write-back, write-allocate data cache, physically tagged. The arrays are read at the clock
// edge with the next MEM address, so a hit answers in its own cycle; misses wait in MSHRs while other lines hit.
module dcache #(
    parameter NUM_WAYS = 4,
    parameter SET_INDEX_BITS = 6,
    parameter WORD_OFFSET_BITS = 2,
    parameter NUM_MSHR = 8
) (
    input wire clk,
    input wire rst,
    input wire [31:0] next_addr,  // Address MEM holds after this edge
    input wire clean_req,         // FENCE.I: write every dirty line back
    output wire clean,            // Nothing dirty or pending

    // Core side: byte enables relative to addr, write data in the low bytes, loads formatted
    input wire req,
    input wire [31:0] addr,
    input wire we,
    input wire [3:0] be,
    input wire [31:0] wdata,
    input wire [2:0] load_type,
    output wire gnt,
    output wire rvalid,
    output wire [31:0] rdata,

    // Memory side
    output wire mem_req,
    output wire [31:0] mem_addr,
    output wire mem_we,
    output wire [3:0] mem_be,
    output wire [31:0] mem_wdata,
    output wire mem_line,  // A line transfer, always to RAM
    input wire mem_gnt,
    input wire mem_rvalid,
    input wire [31:0] mem_rdata
);
    localparam SETS = 1 << SET_INDEX_BITS;
    localparam WORDS = 1 << WORD_OFFSET_BITS;
    localparam WORD_INDEX_BITS = SET_INDEX_BITS + WORD_OFFSET_BITS;
    localparam WAY_WORDS = 1 << WORD_INDEX_BITS;
    localparam TAG_BITS = 30 - WORD_INDEX_BITS;
    localparam LINE_ADDR_BITS = 30 - WORD_OFFSET_BITS;
    localparam WAY_BITS = (NUM_WAYS < 3) ? 1 :
                          (NUM_WAYS < 5) ? 2 : 3;
    localparam PLRU_LEVELS = (NUM_WAYS < 2) ? 0 :
                             (NUM_WAYS < 3) ? 1 :
                             (NUM_WAYS < 5) ? 2 : 3;
    localparam PLRU_BITS = (NUM_WAYS < 2) ? 1 : NUM_WAYS - 1;
    localparam MSHR_BITS = (NUM_MSHR < 3) ? 1 :
                           (NUM_MSHR < 5) ? 2 :
                           (NUM_MSHR < 9) ? 3 : 4;
    localparam COUNT_WIDTH = (NUM_MSHR < 2) ? 1 :
                             (NUM_MSHR < 4) ? 2 :
                             (NUM_MSHR < 8) ? 3 :
                             (NUM_MSHR < 16) ? 4 : 5;
    localparam [31:0] NUM_MSHR_FULL = NUM_MSHR;
    localparam [COUNT_WIDTH-1:0] MSHR_LIMIT = NUM_MSHR_FULL[COUNT_WIDTH-1:0];
    localparam [31:0] WORDS_FULL = WORDS;
    localparam [WORD_OFFSET_BITS:0] WORDS_COUNT = WORDS_FULL[WORD_OFFSET_BITS:0];

    localparam E_IDLE = 3'd0;
    localparam E_TAG = 3'd1;
    localparam E_VICTIM = 3'd2;
    localparam E_EVICT_READ = 3'd3;
    localparam E_EVICT_WRITE = 3'd4;
    localparam E_FILL = 3'd5;
    localparam E_SCAN = 3'd6;
    localparam E_BYPASS = 3'd7;

    // Ways 1, 2, 4 or 8 (PLRU tree), set index and word offset inside the 4 KB page, 1 to 16 MSHRs.
    generate
        if (((NUM_WAYS != 1) && (NUM_WAYS != 2) && (NUM_WAYS != 4) && (NUM_WAYS != 8)) ||
            (WORD_OFFSET_BITS < 1) || (SET_INDEX_BITS < 1) || (WORD_INDEX_BITS > 10) ||
            (NUM_MSHR < 1) || (NUM_MSHR > 16)) begin : g_invalid_parameters
            dcache_parameters_out_of_range invalid_parameters ();
        end
    endgenerate

    reg [NUM_WAYS*32-1:0] data_mem [0:WAY_WORDS-1];
    reg [NUM_WAYS*TAG_BITS-1:0] tag_mem [0:SETS-1];
    reg [NUM_WAYS*32-1:0] data_rd_q;
    reg [NUM_WAYS*TAG_BITS-1:0] tag_rd_q;
    reg [NUM_WAYS-1:0] valid_rd_q;
    reg [WORD_INDEX_BITS-1:0] rd_index_q;
    reg rd_fresh_q;
    reg [NUM_WAYS*SETS-1:0] valid_q;
    reg [NUM_WAYS*SETS-1:0] dirty_q;
    reg [PLRU_BITS*SETS-1:0] plru_q;

    // MSHR i < mshr_count holds a missed line and its store bytes; entry 0 fills first.
    reg [LINE_ADDR_BITS-1:0] mshr_line_q [0:NUM_MSHR-1];
    reg [WORDS*4-1:0] mshr_be_q [0:NUM_MSHR-1];
    reg [WORDS*32-1:0] mshr_data_q [0:NUM_MSHR-1];
    reg [COUNT_WIDTH-1:0] mshr_count;

    reg [2:0] eng_state;
    reg eng_clean;  // Writing a dirty line back for FENCE.I, not filling
    reg [SET_INDEX_BITS-1:0] eng_set;
    reg [WAY_BITS-1:0] eng_way;
    reg [TAG_BITS-1:0] eng_tag;
    reg [WORD_OFFSET_BITS:0] eng_word;
    reg [WORDS*32-1:0] evict_buf;
    reg [SET_INDEX_BITS-1:0] scan_set;

    // Statistics, read by tests and the benchmark harness
    reg [31:0] stat_hits;
    reg [31:0] stat_misses;
    reg [31:0] stat_evictions;
    reg [31:0] stat_mshr_full_cycles;

    wire [WORD_INDEX_BITS-1:0] req_index = addr[WORD_INDEX_BITS+1:2];
    wire [SET_INDEX_BITS-1:0] req_set = addr[WORD_INDEX_BITS+1:WORD_OFFSET_BITS+2];
    wire [WORD_OFFSET_BITS-1:0] req_word = addr[WORD_OFFSET_BITS+1:2];
    wire [TAG_BITS-1:0] req_tag = addr[31:WORD_INDEX_BITS+2];
    wire [LINE_ADDR_BITS-1:0] req_line = addr[31:WORD_OFFSET_BITS+2];
    wire cacheable = `IS_INSTR_MEM(addr) || `IS_DATA_MEM(addr);
    wire [3:0] lane_be = be << addr[1:0];
    wire [31:0] lane_data = wdata << {addr[1:0], 3'b000};

    wire [LINE_ADDR_BITS-1:0] head_line = mshr_line_q[0];
    wire [WORDS*4-1:0] head_be = mshr_be_q[0];
    wire [WORDS*32-1:0] head_data = mshr_data_q[0];
    wire [WORD_OFFSET_BITS-1:0] eng_word_index = eng_word[WORD_OFFSET_BITS-1:0];
    wire mshr_empty = (mshr_count == {COUNT_WIDTH{1'b0}});
    wire mshr_full = (mshr_count == MSHR_LIMIT);

    wire fill_write = (eng_state == E_FILL) && mem_rvalid;
    wire fill_last = fill_write && (eng_word_index == {WORD_OFFSET_BITS{1'b1}});
    // Victim choice reads the flops, and the fill port owns the data array while a word lands.
    wire lookup_block = (eng_state == E_VICTIM) || (eng_state == E_BYPASS) || fill_write;
    wire lookup = req && cacheable && !lookup_block && rd_fresh_q && (rd_index_q == req_index);

    reg [NUM_WAYS-1:0] way_hit;
    reg [WAY_BITS-1:0] hit_way;
    reg [31:0] hit_word;
    reg [NUM_MSHR-1:0] mshr_match;
    reg [MSHR_BITS-1:0] match_index;
    integer i, j, k, n, m, b, c, d, w, x;

    always @(*) begin
        hit_way = {WAY_BITS{1'b0}};
        hit_word = 32'b0;
        for (i = 0; i < NUM_WAYS; i = i + 1) begin
            way_hit[i] = valid_rd_q[i] && (tag_rd_q[i*TAG_BITS +: TAG_BITS] == req_tag);
            if (way_hit[i]) begin
                hit_way = i[WAY_BITS-1:0];
                hit_word = data_rd_q[i*32 +: 32];
            end
        end
    end

    always @(*) begin
        match_index = {MSHR_BITS{1'b0}};
        for (j = 0; j < NUM_MSHR; j = j + 1) begin
            mshr_match[j] = ({{(32-COUNT_WIDTH){1'b0}}, mshr_count} > j) && (mshr_line_q[j] == req_line);
            if (mshr_match[j]) begin
                match_index = j[MSHR_BITS-1:0];
            end
        end
    end

    wire hit_any = |way_hit;
    wire match_any = |mshr_match;
    // Entry 0 takes no more bytes once its words are being written.
    wire match_filling = match_any && (match_index == {MSHR_BITS{1'b0}}) && (eng_state == E_FILL);
    wire store_hit = lookup && we && hit_any;
    wire store_merge = lookup && we && !hit_any && match_any && !match_filling;
    wire store_alloc = lookup && we && !hit_any && !match_any && !mshr_full;
    wire load_hit = lookup && !we && hit_any;
    wire load_alloc = lookup && !we && !hit_any && !match_any && !mshr_full;
    wire served = store_hit || store_merge || store_alloc || load_hit;
    wire alloc = store_alloc || load_alloc;
    // Uncached accesses use the port only while no line transfer is queued or running.
    wire bypass_go = req && !cacheable && (eng_state == E_IDLE) && mshr_empty;

    assign gnt = served || (bypass_go && mem_gnt);
    assign rvalid = served || (mem_rvalid && (bypass_go || (eng_state == E_BYPASS)));
    assign rdata = load_hit ? format_load(hit_word, addr[1:0], load_type) : mem_rdata;
    assign clean = !(|dirty_q) && mshr_empty && (eng_state == E_IDLE);

    assign mem_line = (eng_state == E_EVICT_WRITE) || (eng_state == E_FILL);
    assign mem_req = mem_line || bypass_go;
    assign mem_addr = (eng_state == E_EVICT_WRITE) ? {eng_tag, eng_set, eng_word_index, 2'b00} :
                      (eng_state == E_FILL) ? {head_line, eng_word_index, 2'b00} : addr;
    assign mem_we = (eng_state == E_EVICT_WRITE) || (!mem_line && we);
    assign mem_be = mem_line ? 4'b1111 : be;
    assign mem_wdata = (eng_state == E_EVICT_WRITE) ? evict_buf[eng_word_index*32 +: 32] :
                       mem_line ? 32'b0 : wdata;

    // As the backing memory formats them: the addressed byte or halfword, extended.
    function [31:0] format_load;
        input [31:0] word;
        input [1:0] offset;
        input [2:0] kind;
        reg [31:0] shifted;
        begin
            shifted = word >> {offset, 3'b000};
            case (kind)
                3'b000: format_load = {{24{shifted[7]}}, shifted[7:0]};
                3'b100: format_load = {24'b0, shifted[7:0]};
                3'b001: format_load = {{16{shifted[15]}}, shifted[15:0]};
                3'b101: format_load = {16'b0, shifted[15:0]};
                3'b010: format_load = word;
                default: format_load = 32'b0;
            endcase
        end
    endfunction

    // Tree pseudo-LRU, nodes in heap order: a node bit of 0 points the replacement left.
    function [WAY_BITS-1:0] plru_victim;
        input [PLRU_BITS-1:0] bits;
        integer level;
        reg [7:0] tree;
        reg [2:0] node;
        reg [2:0] path;
        begin
            tree = 8'b0;
            tree[PLRU_BITS-1:0] = bits;
            node = 3'd0;
            path = 3'd0;
            for (level = 0; level < PLRU_LEVELS; level = level + 1) begin
                path = {path[1:0], tree[node]};
                node = {node[1:0], 1'b0} + 3'd1 + {2'b00, tree[node]};
            end
            plru_victim = path[WAY_BITS-1:0];
        end
    endfunction

    // Point every node on the way's path away from it.
    function [PLRU_BITS-1:0] plru_touch;
        input [PLRU_BITS-1:0] bits;
        input [WAY_BITS-1:0] way;
        integer level;
        reg [7:0] tree;
        reg [2:0] node;
        reg [2:0] path;
        reg branch;
        begin
            tree = 8'b0;
            tree[PLRU_BITS-1:0] = bits;
            path = 3'd0;
            path[WAY_BITS-1:0] = way;
            node = 3'd0;
            for (level = 0; level < PLRU_LEVELS; level = level + 1) begin
                branch = path[PLRU_LEVELS-1-level];
                tree[node] = !branch;
                node = {node[1:0], 1'b0} + 3'd1 + {2'b00, branch};
            end
            plru_touch = tree[PLRU_BITS-1:0];
        end
    endfunction

    // Array read: the engine's line, else a waiting request, else the next MEM address.
    wire [WORD_OFFSET_BITS-1:0] evict_word = eng_word_index - 1'b1;
    wire claim_tag = (eng_state == E_TAG);
    wire claim_evict = (eng_state == E_EVICT_READ) && (eng_word != WORDS_COUNT);
    wire [WORD_INDEX_BITS-1:0] next_index = next_addr[WORD_INDEX_BITS+1:2];
    wire [WORD_INDEX_BITS-1:0] read_index =
        claim_tag ? {eng_set, {WORD_OFFSET_BITS{1'b0}}} :
        claim_evict ? {eng_set, eng_word_index} :
        (req && cacheable && !lookup) ? req_index : next_index;
    wire [SET_INDEX_BITS-1:0] read_set = read_index[WORD_INDEX_BITS-1:WORD_OFFSET_BITS];

    // One data write per cycle: a fill word, else a store hit.
    wire data_write = fill_write || store_hit;
    wire [WORD_INDEX_BITS-1:0] write_index = fill_write ? {eng_set, eng_word_index} : req_index;
    wire [WAY_BITS-1:0] write_way = fill_write ? eng_way : hit_way;
    reg [3:0] write_be;
    reg [31:0] write_data;
    always @(*) begin
        write_be = lane_be;
        write_data = lane_data;
        if (fill_write) begin
            write_be = 4'b1111;
            for (c = 0; c < 4; c = c + 1) begin
                write_data[c*8 +: 8] = head_be[eng_word_index*4 + c] ? head_data[eng_word_index*32 + c*8 +: 8] :
                                       mem_rdata[c*8 +: 8];
            end
        end
    end

    // Victim: an invalid way, else the PLRU way; for FENCE.I the first dirty way.
    reg [WAY_BITS-1:0] victim;
    reg victim_found;
    always @(*) begin
        victim = plru_victim(plru_q[eng_set*PLRU_BITS +: PLRU_BITS]);
        victim_found = 1'b0;
        for (k = 0; k < NUM_WAYS; k = k + 1) begin
            if (!victim_found && (eng_clean ? dirty_q[k*SETS + {{(32-SET_INDEX_BITS){1'b0}}, eng_set}] :
                                              !valid_q[k*SETS + {{(32-SET_INDEX_BITS){1'b0}}, eng_set}])) begin
                victim = k[WAY_BITS-1:0];
                victim_found = 1'b1;
            end
        end
    end
    wire victim_dirty = dirty_q[victim*SETS + {{(32-SET_INDEX_BITS){1'b0}}, eng_set}];

    wire [PLRU_BITS-1:0] hit_plru = plru_touch(plru_q[req_set*PLRU_BITS +: PLRU_BITS], hit_way);
    wire [PLRU_BITS-1:0] fill_plru = plru_touch(plru_q[eng_set*PLRU_BITS +: PLRU_BITS], eng_way);

    reg scan_dirty;
    always @(*) begin
        scan_dirty = 1'b0;
        for (n = 0; n < NUM_WAYS; n = n + 1) begin
            if (dirty_q[n*SETS + {{(32-SET_INDEX_BITS){1'b0}}, scan_set}]) begin
                scan_dirty = 1'b1;
            end
        end
    end

    // A read at an edge that also writes its row, or changes its set's tags or valid bits, is stale.
    wire set_change = ((eng_state == E_VICTIM) && !eng_clean) || fill_last;
    wire read_stale = (data_write && (write_index == read_index)) || (set_change && (eng_set == read_set));

    // Block RAM: one row holds every way, read whole; writes go to one way's slice. No reset.
    always @(posedge clk) begin
        for (m = 0; m < NUM_WAYS; m = m + 1) begin
            for (b = 0; b < 4; b = b + 1) begin
                if (data_write && (write_way == m[WAY_BITS-1:0]) && write_be[b]) begin
                    data_mem[write_index][m*32 + b*8 +: 8] <= write_data[b*8 +: 8];
                end
            end
            if (fill_last && (eng_way == m[WAY_BITS-1:0])) begin
                tag_mem[eng_set][m*TAG_BITS +: TAG_BITS] <= head_line[LINE_ADDR_BITS-1:SET_INDEX_BITS];
            end
        end
        data_rd_q <= data_mem[read_index];
        tag_rd_q <= tag_mem[read_set];
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            valid_rd_q <= {NUM_WAYS{1'b0}};
            rd_index_q <= {WORD_INDEX_BITS{1'b0}};
            rd_fresh_q <= 1'b0;
            valid_q <= {(NUM_WAYS*SETS){1'b0}};
            dirty_q <= {(NUM_WAYS*SETS){1'b0}};
            plru_q <= {(PLRU_BITS*SETS){1'b0}};
            for (i = 0; i < NUM_MSHR; i = i + 1) begin
                mshr_line_q[i] <= {LINE_ADDR_BITS{1'b0}};
                mshr_be_q[i] <= {(WORDS*4){1'b0}};
                mshr_data_q[i] <= {(WORDS*32){1'b0}};
            end
            mshr_count <= {COUNT_WIDTH{1'b0}};
            eng_state <= E_IDLE;
            eng_clean <= 1'b0;
            eng_set <= {SET_INDEX_BITS{1'b0}};
            eng_way <= {WAY_BITS{1'b0}};
            eng_tag <= {TAG_BITS{1'b0}};
            eng_word <= {(WORD_OFFSET_BITS+1){1'b0}};
            evict_buf <= {(WORDS*32){1'b0}};
            scan_set <= {SET_INDEX_BITS{1'b0}};
            stat_hits <= 32'b0;
            stat_misses <= 32'b0;
            stat_evictions <= 32'b0;
            stat_mshr_full_cycles <= 32'b0;
        end else begin
            // Valid bits are read with the arrays, before this edge's changes.
            for (x = 0; x < NUM_WAYS; x = x + 1) begin
                valid_rd_q[x] <= valid_q[x*SETS + {{(32-SET_INDEX_BITS){1'b0}}, read_set}];
            end
            rd_index_q <= read_index;
            rd_fresh_q <= !read_stale;

            if (store_hit) begin
                dirty_q[hit_way*SETS + {{(32-SET_INDEX_BITS){1'b0}}, req_set}] <= 1'b1;
            end
            if (store_hit || load_hit) begin
                plru_q[req_set*PLRU_BITS +: PLRU_BITS] <= hit_plru;
                stat_hits <= stat_hits + 32'd1;
            end
            if (alloc) begin
                stat_misses <= stat_misses + 32'd1;
            end
            if (lookup && !hit_any && !match_any && mshr_full) begin
                stat_mshr_full_cycles <= stat_mshr_full_cycles + 32'd1;
            end

            // Entry 0 retires as its fill ends; nothing is allocated or merged that cycle.
            for (i = 0; i < NUM_MSHR - 1; i = i + 1) begin
                if (fill_last) begin
                    mshr_line_q[i] <= mshr_line_q[i + 1];
                    mshr_be_q[i] <= mshr_be_q[i + 1];
                    mshr_data_q[i] <= mshr_data_q[i + 1];
                end
            end
            for (i = 0; i < NUM_MSHR; i = i + 1) begin
                if ((alloc && ({{(32-COUNT_WIDTH){1'b0}}, mshr_count} == i)) ||
                    (store_merge && ({{(32-MSHR_BITS){1'b0}}, match_index} == i))) begin
                    if (alloc) begin
                        mshr_line_q[i] <= req_line;
                    end
                    for (w = 0; w < WORDS; w = w + 1) begin
                        for (d = 0; d < 4; d = d + 1) begin
                            if (alloc) begin
                                mshr_be_q[i][w*4 + d] <= 1'b0;
                            end
                            if (we && (req_word == w[WORD_OFFSET_BITS-1:0]) && lane_be[d]) begin
                                mshr_be_q[i][w*4 + d] <= 1'b1;
                                mshr_data_q[i][w*32 + d*8 +: 8] <= lane_data[d*8 +: 8];
                            end
                        end
                    end
                end
            end
            if (alloc) begin
                mshr_count <= mshr_count + 1'b1;
            end else if (fill_last) begin
                mshr_count <= mshr_count - 1'b1;
            end

            case (eng_state)
                E_IDLE: begin
                    if (bypass_go) begin
                        if (mem_gnt && !mem_rvalid) begin
                            eng_state <= E_BYPASS;
                        end
                    end else if (!mshr_empty) begin
                        eng_state <= E_TAG;
                        eng_clean <= 1'b0;
                        eng_set <= head_line[SET_INDEX_BITS-1:0];
                    end else if (clean_req && (|dirty_q)) begin
                        eng_state <= E_SCAN;
                    end
                end
                E_SCAN: begin
                    if (!mshr_empty || !clean_req || !(|dirty_q)) begin
                        eng_state <= E_IDLE;
                    end else if (scan_dirty) begin
                        eng_state <= E_TAG;
                        eng_clean <= 1'b1;
                        eng_set <= scan_set;
                    end else begin
                        scan_set <= scan_set + 1'b1;
                    end
                end
                E_TAG: begin
                    eng_state <= E_VICTIM;
                end
                E_VICTIM: begin
                    eng_way <= victim;
                    eng_tag <= tag_rd_q[victim*TAG_BITS +: TAG_BITS];
                    eng_word <= {(WORD_OFFSET_BITS+1){1'b0}};
                    dirty_q[victim*SETS + {{(32-SET_INDEX_BITS){1'b0}}, eng_set}] <= 1'b0;
                    if (!eng_clean) begin
                        valid_q[victim*SETS + {{(32-SET_INDEX_BITS){1'b0}}, eng_set}] <= 1'b0;
                    end
                    eng_state <= victim_dirty ? E_EVICT_READ : eng_clean ? E_SCAN : E_FILL;
                end
                E_EVICT_READ: begin
                    // Word n is in the read register the cycle after its row was read.
                    if (eng_word != {(WORD_OFFSET_BITS+1){1'b0}}) begin
                        evict_buf[evict_word*32 +: 32] <= data_rd_q[eng_way*32 +: 32];
                    end
                    if (eng_word == WORDS_COUNT) begin
                        eng_state <= E_EVICT_WRITE;
                        eng_word <= {(WORD_OFFSET_BITS+1){1'b0}};
                    end else begin
                        eng_word <= eng_word + 1'b1;
                    end
                end
                E_EVICT_WRITE: begin
                    if (mem_rvalid) begin
                        eng_word <= eng_word + 1'b1;
                        if (eng_word_index == {WORD_OFFSET_BITS{1'b1}}) begin
                            eng_state <= eng_clean ? E_SCAN : E_FILL;
                            eng_word <= {(WORD_OFFSET_BITS+1){1'b0}};
                            stat_evictions <= stat_evictions + 32'd1;
                        end
                    end
                end
                E_FILL: begin
                    if (fill_write) begin
                        eng_word <= eng_word + 1'b1;
                    end
                    if (fill_last) begin
                        eng_state <= E_IDLE;
                        valid_q[eng_way*SETS + {{(32-SET_INDEX_BITS){1'b0}}, eng_set}] <= 1'b1;
                        dirty_q[eng_way*SETS + {{(32-SET_INDEX_BITS){1'b0}}, eng_set}] <= |head_be;
                        plru_q[eng_set*PLRU_BITS +: PLRU_BITS] <= fill_plru;
                    end
                end
                E_BYPASS: begin
                    if (mem_rvalid) begin
                        eng_state <= E_IDLE;
                    end
                end
                default: begin
                    eng_state <= E_IDLE;
                end
            endcase
        end
    end
endmodule
