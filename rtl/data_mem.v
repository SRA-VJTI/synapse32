
// data_mem.v - data memory for single-cycle RISC-V CPU

module data_mem #(parameter DATA_WIDTH = 32, ADDR_WIDTH = 32, MEM_SIZE = 64) (
    input       clk, wr_en,
    input       [ADDR_WIDTH-1:0] wr_addr, wr_data,
    output      [DATA_WIDTH-1:0] rd_data_mem
);

// array of 64 32-bit words or data
reg [DATA_WIDTH-1:0] data_ram [0:MEM_SIZE-1];

reg [DATA_WIDTH-1:0] instr_ram [0:511];
initial begin
    $readmemh("program_dump.hex", instr_ram);
end
// combinational read logic
// word-aligned memory access
//if address is greater than 0x02000000, then it is a data memory access
//if it is less than 0x02000000, then it is an instruction memory access
assign rd_data_mem =
    (wr_en == 0) ?
        ((wr_addr >= 32'h02000000) ?
            data_ram[wr_addr[DATA_WIDTH-1:2] % 64] : instr_ram[wr_addr[DATA_WIDTH-1:2]])
        : 0;

// synchronous write logic
always @(posedge clk) begin
    if (wr_en) data_ram[wr_addr[DATA_WIDTH-1:2] % 64] <= wr_data;
end

endmodule
