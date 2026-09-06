`default_nettype none
// unified_mem.v - unified physical backing RAM
`include "memory_map.vh"

module unified_mem #(
    parameter DATA_WIDTH = 32,
    parameter ADDR_WIDTH = 32,
    parameter MEM_SIZE = 512
) (
    input wire clk,
    input wire [ADDR_WIDTH-1:0] instr_addr,
    input wire [ADDR_WIDTH-1:0] instr_addr_p2,
    input wire data_wr_req,
    input wire data_rd_en,
    input wire wr_en,
    input wire [3:0] write_byte_enable,
    input wire [DATA_WIDTH-1:0] wr_data,
    input wire [2:0] load_type,
    input wire        pte_wr_en_a,
    input wire [31:0] pte_wr_addr_a,
    input wire [31:0] pte_wr_value_a,
    input wire        pte_wr_en_b,
    input wire [31:0] pte_wr_addr_b,
    input wire [31:0] pte_wr_value_b,
    input wire [31:0] pte_rd_addr_a,
    input wire [31:0] pte_rd_addr_b,
    input wire [31:0] pte_rd_addr_c,
    input wire [31:0] pte_rd_addr_d,
    output reg [DATA_WIDTH-1:0] instr,
    output reg [DATA_WIDTH-1:0] instr_p2,
    output wire [31:0] pte_rd_value_a,
    output wire [31:0] pte_rd_value_b,
    output wire [31:0] pte_rd_value_c,
    output wire [31:0] pte_rd_value_d,
    output wire        pte_rd_backed_a,
    output wire        pte_rd_backed_b,
    output wire        pte_rd_backed_c,
    output wire        pte_rd_backed_d
);

reg [DATA_WIDTH-1:0] instr_ram [0:MEM_SIZE-1];
localparam WORD_INDEX_MSB = 26;

function [31:0] phys_to_local_addr;
    input [31:0] phys_addr;
    begin
        if (`IS_INSTR_MEM(phys_addr)) begin
            phys_to_local_addr = phys_addr - `INSTR_MEM_BASE;
        end else if (`IS_DATA_MEM(phys_addr)) begin
            phys_to_local_addr = (phys_addr - `DATA_MEM_BASE) + `INSTR_MEM_SIZE;
        end else begin
            phys_to_local_addr = 32'hFFFFFFFF;
        end
    end
endfunction

function phys_addr_is_backed;
    input [31:0] phys_addr;
    reg [31:0] local_addr;
    begin
        local_addr = phys_to_local_addr(phys_addr);
        phys_addr_is_backed = (local_addr != 32'hFFFFFFFF) && (local_addr[WORD_INDEX_MSB:2] < MEM_SIZE);
    end
endfunction

function [31:0] phys_read_word;
    input [31:0] phys_addr;
    reg [31:0] local_addr;
    begin
        local_addr = phys_to_local_addr(phys_addr);
        if ((local_addr != 32'hFFFFFFFF) && (local_addr[WORD_INDEX_MSB:2] < MEM_SIZE)) begin
            phys_read_word = instr_ram[local_addr[WORD_INDEX_MSB:2]];
        end else begin
            phys_read_word = 32'h00000000;
        end
    end
endfunction

assign pte_rd_value_a = phys_read_word(pte_rd_addr_a);
assign pte_rd_value_b = phys_read_word(pte_rd_addr_b);
assign pte_rd_value_c = phys_read_word(pte_rd_addr_c);
assign pte_rd_value_d = phys_read_word(pte_rd_addr_d);
assign pte_rd_backed_a = phys_addr_is_backed(pte_rd_addr_a);
assign pte_rd_backed_b = phys_addr_is_backed(pte_rd_addr_b);
assign pte_rd_backed_c = phys_addr_is_backed(pte_rd_addr_c);
assign pte_rd_backed_d = phys_addr_is_backed(pte_rd_addr_d);

`ifdef COCOTB_SIM
initial begin
    `ifdef INSTR_HEX_FILE
        $display("Loading instruction memory from file: %s", `INSTR_HEX_FILE);
        $readmemh(`INSTR_HEX_FILE, instr_ram);
    `else
        $display("No instruction file specified, initializing memory with NOPs.");
    `endif
end
`else
initial begin
    integer i;
    for (i = 0; i < MEM_SIZE; i = i + 1) begin
        instr_ram[i] = 32'h00000013;
    end
end
`endif

always @(*) begin
    reg [31:0] local_addr;
    instr = 32'h00000013;
    local_addr = phys_to_local_addr(instr_addr);
    if ((local_addr != 32'hFFFFFFFF) && (local_addr[WORD_INDEX_MSB:2] < MEM_SIZE)) begin
        instr = instr_ram[local_addr[WORD_INDEX_MSB:2]];
    end
end

always @(*) begin
    reg [WORD_INDEX_MSB-2:0] word_addr;
    reg [1:0] byte_offset;
    reg [31:0] word_data;
    reg [7:0] byte_data;
    reg [15:0] halfword_data;
    reg [31:0] data_local_addr;
    reg [31:0] next_word_data;

    instr_p2        = 32'h0;
    word_data       = 32'h0;
    byte_data       = 8'h0;
    halfword_data   = 16'h0;
    data_local_addr = 32'h0;
    word_addr       = 0;
    byte_offset     = 2'b0;
    next_word_data  = 32'h0;

    if (data_rd_en || data_wr_req) begin
        data_local_addr = phys_to_local_addr(instr_addr_p2);
        word_addr = data_local_addr[WORD_INDEX_MSB:2];
        byte_offset = instr_addr_p2[1:0];

        if ((data_local_addr != 32'hFFFFFFFF) && (word_addr < MEM_SIZE)) begin
            /* verilator lint_off WIDTHTRUNC */
            word_data = instr_ram[word_addr];
            /* verilator lint_on WIDTHTRUNC */
        end

        case (byte_offset)
            2'b00: byte_data = word_data[7:0];
            2'b01: byte_data = word_data[15:8];
            2'b10: byte_data = word_data[23:16];
            2'b11: byte_data = word_data[31:24];
        endcase

        case (byte_offset[1])
            1'b0: halfword_data = word_data[15:0];
            1'b1: halfword_data = word_data[31:16];
        endcase

        if (byte_offset == 2'b11 && (load_type == 3'b001 || load_type == 3'b101)) begin
            if (word_addr + 1 < MEM_SIZE) begin
                next_word_data = instr_ram[word_addr + 1];
            end
            halfword_data = {next_word_data[7:0], word_data[31:24]};
        end

        if (byte_offset != 2'b00 && load_type == 3'b010) begin
            if (word_addr + 1 < MEM_SIZE) begin
                next_word_data = instr_ram[word_addr + 1];
            end
            case (byte_offset)
                2'b01: word_data = {next_word_data[7:0],  word_data[31:8]};
                2'b10: word_data = {next_word_data[15:0], word_data[31:16]};
                2'b11: word_data = {next_word_data[23:0], word_data[31:24]};
                default: word_data = word_data;
            endcase
        end

        case (load_type)
            3'b000: instr_p2 = {{24{byte_data[7]}}, byte_data};
            3'b100: instr_p2 = {24'h0, byte_data};
            3'b001: instr_p2 = {{16{halfword_data[15]}}, halfword_data};
            3'b101: instr_p2 = {16'h0, halfword_data};
            3'b010: instr_p2 = word_data;
            default: instr_p2 = 32'h0;
        endcase
    end
end

always @(posedge clk) begin
    reg [WORD_INDEX_MSB-2:0] word_addr;
    reg [WORD_INDEX_MSB-2:0] next_word_addr;
    reg [WORD_INDEX_MSB-2:0] pte_word_addr_a;
    reg [WORD_INDEX_MSB-2:0] pte_word_addr_b;
    reg [1:0] byte_offset;
    reg [31:0] byte_addr;
    reg [31:0] local_addr;
    reg [31:0] byte_local_addr;
    reg [31:0] store_word_value;
    reg [31:0] store_next_word_value;
    reg [31:0] pte_merged_word;
    reg        pte_valid_a;
    reg        pte_valid_b;
    reg        pte_same_word;
    reg        next_word_valid;
    reg        store_word_dirty;
    reg        store_next_word_dirty;
    integer i;

    pte_word_addr_a = {((WORD_INDEX_MSB-1)){1'b0}};
    pte_word_addr_b = {((WORD_INDEX_MSB-1)){1'b0}};
    pte_valid_a = 1'b0;
    pte_valid_b = 1'b0;
    pte_same_word = 1'b0;
    pte_merged_word = 32'h0;
    next_word_addr = {((WORD_INDEX_MSB-1)){1'b0}};
    next_word_valid = 1'b0;
    store_word_dirty = 1'b0;
    store_next_word_dirty = 1'b0;
    store_word_value = 32'h0;
    store_next_word_value = 32'h0;

    if (pte_wr_en_a) begin
        local_addr = phys_to_local_addr(pte_wr_addr_a);
        pte_word_addr_a = local_addr[WORD_INDEX_MSB:2];
        if ((local_addr != 32'hFFFFFFFF) && (pte_word_addr_a < MEM_SIZE)) begin
            pte_valid_a = 1'b1;
        end
    end

    if (pte_wr_en_b) begin
        local_addr = phys_to_local_addr(pte_wr_addr_b);
        pte_word_addr_b = local_addr[WORD_INDEX_MSB:2];
        if ((local_addr != 32'hFFFFFFFF) && (pte_word_addr_b < MEM_SIZE)) begin
            pte_valid_b = 1'b1;
        end
    end

    pte_same_word = pte_valid_a && pte_valid_b && (pte_word_addr_a == pte_word_addr_b);
    if (pte_same_word) begin
        pte_merged_word = pte_wr_value_a | pte_wr_value_b;
    end

    if (pte_valid_a && !pte_same_word) begin
        instr_ram[pte_word_addr_a] <= pte_wr_value_a;
    end

    if (pte_valid_b && !pte_same_word) begin
        instr_ram[pte_word_addr_b] <= pte_wr_value_b;
    end

    if (pte_same_word) begin
        instr_ram[pte_word_addr_a] <= pte_merged_word;
    end

    if (wr_en) begin
        local_addr = phys_to_local_addr(instr_addr_p2);
        word_addr = local_addr[WORD_INDEX_MSB:2];
        if ((local_addr != 32'hFFFFFFFF) && (word_addr < MEM_SIZE)) begin
            store_word_value = instr_ram[word_addr];
            store_word_dirty = 1'b1;

            if (pte_same_word && (pte_word_addr_a == word_addr)) begin
                store_word_value = pte_merged_word;
            end else if (pte_valid_b && (pte_word_addr_b == word_addr)) begin
                store_word_value = pte_wr_value_b;
            end else if (pte_valid_a && (pte_word_addr_a == word_addr)) begin
                store_word_value = pte_wr_value_a;
            end

            next_word_addr = word_addr + 1'b1;
            next_word_valid = (next_word_addr < MEM_SIZE);
            if (next_word_valid) begin
                store_next_word_value = instr_ram[next_word_addr];

                if (pte_same_word && (pte_word_addr_a == next_word_addr)) begin
                    store_next_word_value = pte_merged_word;
                end else if (pte_valid_b && (pte_word_addr_b == next_word_addr)) begin
                    store_next_word_value = pte_wr_value_b;
                end else if (pte_valid_a && (pte_word_addr_a == next_word_addr)) begin
                    store_next_word_value = pte_wr_value_a;
                end
            end

            for (i = 0; i < 4; i = i + 1) begin
                if (write_byte_enable[i]) begin
                    byte_addr = instr_addr_p2 + i;
                    byte_local_addr = local_addr + i;
                    byte_offset = byte_addr[1:0];
                    if (byte_local_addr[WORD_INDEX_MSB:2] == word_addr) begin
                        case (byte_offset)
                            2'b00: store_word_value[7:0]   = wr_data[(i*8) +: 8];
                            2'b01: store_word_value[15:8]  = wr_data[(i*8) +: 8];
                            2'b10: store_word_value[23:16] = wr_data[(i*8) +: 8];
                            2'b11: store_word_value[31:24] = wr_data[(i*8) +: 8];
                            default: begin end
                        endcase
                    end else if (next_word_valid && (byte_local_addr[WORD_INDEX_MSB:2] == next_word_addr)) begin
                        store_next_word_dirty = 1'b1;
                        case (byte_offset)
                            2'b00: store_next_word_value[7:0]   = wr_data[(i*8) +: 8];
                            2'b01: store_next_word_value[15:8]  = wr_data[(i*8) +: 8];
                            2'b10: store_next_word_value[23:16] = wr_data[(i*8) +: 8];
                            2'b11: store_next_word_value[31:24] = wr_data[(i*8) +: 8];
                            default: begin end
                        endcase
                    end
                end
            end

            if (store_word_dirty) begin
                instr_ram[word_addr] <= store_word_value;
            end
            if (store_next_word_dirty) begin
                instr_ram[next_word_addr] <= store_next_word_value;
            end
        end
    end
end

endmodule
