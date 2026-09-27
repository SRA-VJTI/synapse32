`default_nettype none
// Fully associative Sv32 TLB of leaf PTEs, one lookup port each for fetch and data. Megapage
// entries compare only VPN[1]; SFENCE.VMA and a write to satp flush it entirely.
module sv32_tlb #(
    parameter ENTRIES = 8
) (
    input wire clk,
    input wire rst,
    input wire flush,

    input wire [31:0] instr_vaddr,
    output reg instr_hit,
    output reg [31:0] instr_pte,
    output reg instr_megapage,

    input wire [31:0] data_vaddr,
    output reg data_hit,
    output reg [31:0] data_pte,
    output reg data_megapage,

    input wire fill_en,
    input wire [31:0] fill_vaddr,
    input wire [31:0] fill_pte,
    input wire fill_megapage
);

    localparam INDEX_WIDTH = (ENTRIES <= 2) ? 1 :
                             (ENTRIES <= 4) ? 2 :
                             (ENTRIES <= 8) ? 3 :
                             (ENTRIES <= 16) ? 4 :
                             (ENTRIES <= 32) ? 5 : 6;

    reg entry_valid [0:ENTRIES-1];
    reg [19:0] entry_tag [0:ENTRIES-1];      // vaddr[31:12]
    reg entry_megapage [0:ENTRIES-1];
    reg [31:0] entry_pte [0:ENTRIES-1];
    reg [INDEX_WIDTH-1:0] next_victim;

    integer i;

    always @(*) begin
        instr_hit = 1'b0;
        instr_pte = 32'b0;
        instr_megapage = 1'b0;
        for (i = 0; i < ENTRIES; i = i + 1) begin
            if (entry_valid[i] &&
                (entry_megapage[i] ? (entry_tag[i][19:10] == instr_vaddr[31:22])
                                   : (entry_tag[i] == instr_vaddr[31:12]))) begin
                instr_hit = 1'b1;
                instr_pte = entry_pte[i];
                instr_megapage = entry_megapage[i];
            end
        end
    end

    always @(*) begin
        data_hit = 1'b0;
        data_pte = 32'b0;
        data_megapage = 1'b0;
        for (i = 0; i < ENTRIES; i = i + 1) begin
            if (entry_valid[i] &&
                (entry_megapage[i] ? (entry_tag[i][19:10] == data_vaddr[31:22])
                                   : (entry_tag[i] == data_vaddr[31:12]))) begin
                data_hit = 1'b1;
                data_pte = entry_pte[i];
                data_megapage = entry_megapage[i];
            end
        end
    end

    // Round-robin replacement: one walk at a time, so a counter is enough.
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            next_victim <= {INDEX_WIDTH{1'b0}};
            for (i = 0; i < ENTRIES; i = i + 1) begin
                entry_valid[i] <= 1'b0;
                entry_tag[i] <= 20'b0;
                entry_megapage[i] <= 1'b0;
                entry_pte[i] <= 32'b0;
            end
        end else if (flush) begin
            for (i = 0; i < ENTRIES; i = i + 1) begin
                entry_valid[i] <= 1'b0;
            end
        end else if (fill_en) begin
            entry_valid[next_victim] <= 1'b1;
            entry_tag[next_victim] <= fill_vaddr[31:12];
            entry_megapage[next_victim] <= fill_megapage;
            entry_pte[next_victim] <= fill_pte;
            next_victim <= (next_victim == ENTRIES[INDEX_WIDTH-1:0] - {{(INDEX_WIDTH-1){1'b0}}, 1'b1}) ?
                           {INDEX_WIDTH{1'b0}} :
                           next_victim + {{(INDEX_WIDTH-1){1'b0}}, 1'b1};
        end
    end

endmodule
