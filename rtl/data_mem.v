`default_nettype none
`include "memory_map.vh"

// data_mem.v - byte-addressable data memory for RISC-V CPU

module data_mem #(parameter DATA_WIDTH = 32, ADDR_WIDTH = 32, MEM_SIZE = 1048576) ( // 1MB = 1024*1024 bytes
    input wire clk, 
    input wire wr_en,
    input wire rd_en,
    input wire [3:0] write_byte_enable,   // Write byte enables
    input wire [2:0] load_type,           // Load type encoding
    input wire [ADDR_WIDTH-1:0] addr, 
    input wire [DATA_WIDTH-1:0] wr_data,
    output wire [DATA_WIDTH-1:0] rd_data_out
);

    // Array of 1MB bytes
    reg [7:0] data_ram [0:MEM_SIZE-1];

    // Initialize memory to zeros
    initial begin
        integer i;
        for (i = 0; i < MEM_SIZE; i = i + 1) begin
            data_ram[i] = 8'h00;
        end
    end
    `ifdef COCOTB_SIM
    //dump 80 registers to a wire using generate statement so that I can scope them
    // This is useful for debugging in cocotb
    generate
        genvar j;
        for (j = 0; j < 80; j = j + 1) begin : dump_regs
            wire [7:0] reg_data = data_ram[j];
        end
    endgenerate
    `endif


    // Direct byte access for reads (much simpler and more accurate)
    wire [7:0] byte_data;
    wire [15:0] halfword_data;
    wire [31:0] word_data;
    
    // Read individual bytes directly
    assign byte_data = (addr < MEM_SIZE) ? data_ram[addr] : 8'h00;
    
    // Read halfwords (little-endian: low byte first)
    assign halfword_data = (addr < MEM_SIZE-1) ? 
        {data_ram[addr+1], data_ram[addr]} : 16'h0000;
    
    // Read words (little-endian: low byte first)
    assign word_data = (addr < MEM_SIZE-3) ? 
        {data_ram[addr+3], data_ram[addr+2], data_ram[addr+1], data_ram[addr]} : 32'h00000000;

    // Format read data based on load type - much simpler logic
    assign rd_data_out = rd_en ? (
        (load_type == 3'b000) ? {{24{byte_data[7]}}, byte_data} :      // LB - Load Byte (sign-extend)
        (load_type == 3'b100) ? {24'h0, byte_data} :                  // LBU - Load Byte Unsigned
        (load_type == 3'b001) ? {{16{halfword_data[15]}}, halfword_data} : // LH - Load Halfword (sign-extend)
        (load_type == 3'b101) ? {16'h0, halfword_data} :              // LHU - Load Halfword Unsigned
        (load_type == 3'b010) ? word_data :                           // LW - Load Word
        32'h0  // Invalid load type
    ) : 32'h0;

    // Synchronous write logic for byte-addressable memory
    always @(posedge clk) begin
        if (wr_en && (addr < MEM_SIZE)) begin
            // For byte writes: always write wr_data[7:0] to data_ram[addr]
            if (write_byte_enable[0]) begin
                data_ram[addr] <= wr_data[7:0];
            end
            // For halfword writes: write 2 consecutive bytes
            if (write_byte_enable[1]) begin
                data_ram[addr+1] <= wr_data[15:8];
            end
            // For word writes: write 4 consecutive bytes
            if (write_byte_enable[2]) begin
                data_ram[addr+2] <= wr_data[23:16];
            end
            if (write_byte_enable[3]) begin
                data_ram[addr+3] <= wr_data[31:24];
            end
        end
    end

endmodule