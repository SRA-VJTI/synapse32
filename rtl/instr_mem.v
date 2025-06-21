`default_nettype none
// instr_mem.v - instruction memory for single-cycle RISC-V CPU with byte/halfword/word access

module instr_mem #(
    parameter DATA_WIDTH = 32, 
    parameter ADDR_WIDTH = 32, 
    parameter MEM_SIZE = 512
) (
    input wire [ADDR_WIDTH-1:0] instr_addr,      // Instruction fetch address (word-aligned)
    input wire [ADDR_WIDTH-1:0] instr_addr_p2,   // Data access address (byte-aligned)
    input wire [2:0] load_type,                  // Load type for data access
    output reg [DATA_WIDTH-1:0] instr,           // Instruction output (always word)
    output reg [DATA_WIDTH-1:0] instr_p2         // Data read output (byte/halfword/word)
);

// Array of 32-bit words (keeps $readmemh compatibility)
reg [DATA_WIDTH-1:0] instr_ram [0:MEM_SIZE-1];

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
    // Extract word address and byte offset
    reg [ADDR_WIDTH-3:0] word_addr;
    reg [1:0] byte_offset;
    reg [31:0] word_data;
    reg [7:0] byte_data;
    reg [15:0] halfword_data;
    
    word_addr = instr_addr_p2[ADDR_WIDTH-1:2];
    byte_offset = instr_addr_p2[1:0];
    
    // Read the 32-bit word containing our target data
    if (word_addr < MEM_SIZE) begin
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
        if (word_addr + 1 < MEM_SIZE) begin
            next_word_data = instr_ram[word_addr + 1];
        end else begin
            next_word_data = 32'h00000000;
        end
        halfword_data = {next_word_data[7:0], word_data[31:24]};
    end
    
    if (byte_offset != 2'b00 && load_type == 3'b010) begin
        // Word access that crosses word boundary - need to combine two words
        reg [31:0] next_word_data;
        if (word_addr + 1 < MEM_SIZE) begin
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

endmodule
