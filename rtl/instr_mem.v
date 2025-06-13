`default_nettype none
// instr_mem.v - instruction memory for single-cycle RISC-V CPU

module instr_mem #(parameter DATA_WIDTH = 32, ADDR_WIDTH = 32, MEM_SIZE = 512) (
    input wire [ADDR_WIDTH-1:0] instr_addr,
    output reg [DATA_WIDTH-1:0] instr
);

// array of 64 32-bit words or instructions
reg [DATA_WIDTH-1:0] instr_ram [0:MEM_SIZE-1];

`ifdef COCOTB_SIM
initial begin
    $display("Loading instruction memory from file: %s", `INSTR_HEX_FILE);
    $readmemh(`INSTR_HEX_FILE, instr_ram);
end
`else
initial begin
    // Initialize instruction memory with zeros
    integer i;
    for (i = 0; i < MEM_SIZE; i = i + 1) begin
        instr_ram[i] = 32'h00000000; // Default instruction (NOP)
    end
end
`endif

// word-aligned memory access
// combinational read logic
always @(*) begin
    instr = instr_ram[{2'b0, instr_addr[ADDR_WIDTH-1:2]}]; // Align address to word boundar
end

endmodule
