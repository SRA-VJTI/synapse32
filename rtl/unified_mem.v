`default_nettype none
// unified_mem.v - unified instruction/data memory backing RAM
`include "memory_map.vh"

module unified_mem #(
    parameter DATA_WIDTH = 32, 
    parameter ADDR_WIDTH = 32, 
    parameter MEM_SIZE = 512
) (
    input wire clk,
    input wire [ADDR_WIDTH-1:0] instr_addr,      // Instruction fetch address (word-aligned)
    input wire [ADDR_WIDTH-1:0] instr_addr_p2,   // Data access address (byte-aligned)
    input wire data_wr_req,
    input wire data_rd_en,
    input wire data_translate_enable,
    input wire [1:0] data_priv_mode,
    input wire [31:0] satp,
    input wire data_sum,
    input wire data_mxr,
    input wire wr_en,                            // Data write enable for unified-memory accesses
    input wire [3:0] write_byte_enable,          // Data write byte enables
    input wire [DATA_WIDTH-1:0] wr_data,         // Data write payload
    input wire [2:0] load_type,                  // Load type for data access
    output reg [DATA_WIDTH-1:0] instr,           // Instruction output (always word)
    output reg [DATA_WIDTH-1:0] instr_p2,        // Data read output (byte/halfword/word)
    output reg data_load_page_fault,
    output reg data_store_page_fault,
    output reg [31:0] data_fault_addr
);

// Array of 32-bit words (keeps $readmemh compatibility)
reg [DATA_WIDTH-1:0] instr_ram [0:MEM_SIZE-1];
localparam PRIV_U = 2'b00;
localparam PRIV_S = 2'b01;
localparam WORD_INDEX_MSB = 20;

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

reg [31:0] data_phys_addr;
reg data_phys_addr_valid;

`ifdef COCOTB_SIM
initial begin
    `ifdef INSTR_HEX_FILE
        $display("Loading instruction memory from file: %s", `INSTR_HEX_FILE);
        $readmemh(`INSTR_HEX_FILE, instr_ram);
    `else
        $display("No instruction file specified, initializing memory with NOPs.");
    `endif
    // Debug: Print first few instructions after loading
    // $display("Instruction memory loaded - first few entries:");
    // $display("  [0x00]: 0x%08h", instr_ram[0]);
    // $display("  [0x04]: 0x%08h", instr_ram[1]);
    // $display("  [0x08]: 0x%08h", instr_ram[2]);
end
`else
initial begin
    // Initialize instruction memory with NOPs
    integer i;
    for (i = 0; i < MEM_SIZE; i = i + 1) begin
        instr_ram[i] = 32'h00000013; // Default to NOP instruction
    end
end
`endif

// Port 1: Instruction fetch (always word-aligned)
always @(*) begin
    if (instr_addr[ADDR_WIDTH-1:2] < MEM_SIZE) begin
        instr = instr_ram[{2'b0, instr_addr[ADDR_WIDTH-1:2]}]; // Word-aligned access
    end else begin
        instr = 32'h00000013; // NOP for out-of-bounds
    end
end

// Port 2: Data access with byte/halfword/word support
always @(*) begin
    reg [31:0] root_pt_base;
    reg [31:0] pte_addr_l1;
    reg [31:0] pte_addr_l0;
    reg [31:0] pte_l1;
    reg [31:0] pte_l0;
    reg [31:0] pte;
    reg pte_valid;
    reg pte_read;
    reg pte_write;
    reg pte_exec;
    reg pte_user;
    reg pte_accessed;
    reg pte_dirty;
    reg effective_read_ok;
    reg permission_fault;
    reg [9:0] vpn1;
    reg [9:0] vpn0;
    reg [31:0] translated_phys_addr;
    reg [WORD_INDEX_MSB-2:0] word_addr;
    reg [1:0] byte_offset;
    reg [31:0] word_data;
    reg [7:0] byte_data;
    reg [15:0] halfword_data;
    reg [31:0] data_local_addr;

    data_load_page_fault = 1'b0;
    data_store_page_fault = 1'b0;
    data_fault_addr = instr_addr_p2;
    data_phys_addr = instr_addr_p2;
    data_phys_addr_valid = 1'b1;
    translated_phys_addr = instr_addr_p2;

    if ((data_rd_en || data_wr_req) && data_translate_enable) begin
        vpn1 = instr_addr_p2[31:22];
        vpn0 = instr_addr_p2[21:12];
        root_pt_base = {satp[19:0], 12'b0};
        pte_addr_l1 = root_pt_base + {20'b0, vpn1, 2'b00};
        pte_l1 = phys_read_word(pte_addr_l1);
        pte = pte_l1;

        if (!phys_addr_is_backed(pte_addr_l1) || !pte_l1[0] || (!pte_l1[1] && pte_l1[2])) begin
            data_phys_addr_valid = 1'b0;
        end else if (pte_l1[1] || pte_l1[3]) begin
            if (pte_l1[19:10] != 10'b0) begin
                data_phys_addr_valid = 1'b0;
            end else begin
                translated_phys_addr = {pte_l1[29:20], vpn0, instr_addr_p2[11:0]};
            end
        end else begin
            pte_addr_l0 = {pte_l1[29:10], 12'b0} + {20'b0, vpn0, 2'b00};
            pte_l0 = phys_read_word(pte_addr_l0);
            pte = pte_l0;
            if (!phys_addr_is_backed(pte_addr_l0) || !pte_l0[0] || (!pte_l0[1] && pte_l0[2]) ||
                (!pte_l0[1] && !pte_l0[3])) begin
                data_phys_addr_valid = 1'b0;
            end else begin
                translated_phys_addr = {pte_l0[29:10], instr_addr_p2[11:0]};
            end
        end

        if (data_phys_addr_valid) begin
            pte_valid = pte[0];
            pte_read = pte[1];
            pte_write = pte[2];
            pte_exec = pte[3];
            pte_user = pte[4];
            pte_accessed = pte[6];
            pte_dirty = pte[7];
            effective_read_ok = pte_read || (data_mxr && pte_exec);
            permission_fault = !pte_valid ||
                               ((data_priv_mode == PRIV_U) && !pte_user) ||
                               ((data_priv_mode == PRIV_S) && pte_user && !data_sum) ||
                               ((data_rd_en && !data_wr_req) && (!effective_read_ok || !pte_accessed)) ||
                               (data_wr_req && (!pte_write || !pte_accessed || !pte_dirty));

            if (permission_fault || !phys_addr_is_backed(translated_phys_addr)) begin
                data_phys_addr_valid = 1'b0;
            end else begin
                data_phys_addr = translated_phys_addr;
            end
        end

        if (!data_phys_addr_valid) begin
            data_load_page_fault = data_rd_en;
            data_store_page_fault = data_wr_req;
        end
    end

    data_local_addr = phys_to_local_addr(data_phys_addr);
    word_addr = data_local_addr[WORD_INDEX_MSB:2];
    byte_offset = data_phys_addr[1:0];
    
    // Read the 32-bit word containing our target data
    if (data_phys_addr_valid && (word_addr < MEM_SIZE)) begin
        /* verilator lint_off WIDTHTRUNC */
        word_data = instr_ram[word_addr]; // Read word-aligned data
    end else begin
        word_data = 32'h00000000;
    end
    
    // Extract byte based on offset (little-endian)
    case (byte_offset)
        2'b00: byte_data = word_data[7:0];
        2'b01: byte_data = word_data[15:8];
        2'b10: byte_data = word_data[23:16];
        2'b11: byte_data = word_data[31:24];
    endcase
    
    // Extract halfword based on offset (little-endian)
    case (byte_offset[1])
        1'b0: halfword_data = word_data[15:0];   // bytes 0-1
        1'b1: halfword_data = word_data[31:16];  // bytes 2-3
    endcase
    
    // Handle cross-word boundary access for halfwords and words
    if (byte_offset == 2'b11 && (load_type == 3'b001 || load_type == 3'b101)) begin
        // Halfword access that crosses word boundary
        reg [31:0] next_word_data;
        if (data_phys_addr_valid && (word_addr + 1 < MEM_SIZE)) begin
            next_word_data = instr_ram[word_addr + 1];
        end else begin
            next_word_data = 32'h00000000;
        end
        halfword_data = {next_word_data[7:0], word_data[31:24]};
    end
    
    if (byte_offset != 2'b00 && load_type == 3'b010) begin
        // Word access that crosses word boundary - need to combine two words
        reg [31:0] next_word_data;
        if (data_phys_addr_valid && (word_addr + 1 < MEM_SIZE)) begin
            next_word_data = instr_ram[word_addr + 1];
        end else begin
            next_word_data = 32'h00000000;
        end
        
        case (byte_offset)
            2'b01: word_data = {next_word_data[7:0], word_data[31:8]};
            2'b10: word_data = {next_word_data[15:0], word_data[31:16]};
            2'b11: word_data = {next_word_data[23:0], word_data[31:24]};
            default: word_data = word_data; // No change for 2'b00
        endcase
    end
    
    // Format output based on load type
    case (load_type)
        3'b000: instr_p2 = {{24{byte_data[7]}}, byte_data};      // LB - Load Byte (sign-extend)
        3'b100: instr_p2 = {24'h0, byte_data};                  // LBU - Load Byte Unsigned
        3'b001: instr_p2 = {{16{halfword_data[15]}}, halfword_data}; // LH - Load Halfword (sign-extend)
        3'b101: instr_p2 = {16'h0, halfword_data};              // LHU - Load Halfword Unsigned
        3'b010: instr_p2 = word_data;                           // LW - Load Word
        default: instr_p2 = 32'h0;                              // Invalid load type
    endcase
end

// Port 2 write path for unified memory behavior (used by riscv-tests env/p).
always @(posedge clk) begin
    reg [WORD_INDEX_MSB-2:0] word_addr;
    reg [1:0] byte_offset;
    reg [ADDR_WIDTH-1:0] byte_addr;
    reg [31:0] local_addr;
    integer i;
    if (wr_en && !data_store_page_fault) begin
        for (i = 0; i < 4; i = i + 1) begin
            if (write_byte_enable[i]) begin
                byte_addr = data_phys_addr + i;
                local_addr = phys_to_local_addr(byte_addr);
                word_addr = local_addr[WORD_INDEX_MSB:2];
                byte_offset = byte_addr[1:0];
                if ((local_addr != 32'hFFFFFFFF) && (word_addr < MEM_SIZE)) begin
                    case (byte_offset)
                        2'b00: instr_ram[word_addr][7:0]   <= wr_data[(i*8) +: 8];
                        2'b01: instr_ram[word_addr][15:8]  <= wr_data[(i*8) +: 8];
                        2'b10: instr_ram[word_addr][23:16] <= wr_data[(i*8) +: 8];
                        2'b11: instr_ram[word_addr][31:24] <= wr_data[(i*8) +: 8];
                        default: begin end
                    endcase
                end
            end
        end
    end
end

endmodule
