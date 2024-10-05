/**
 * @file data_mem.v
 * 
 * This module is a memory module with read and write capabilities.
 *
 * @param DATA_WIDTH The width of the data bus (default is 32).
 * @param ADDR_WIDTH The width of the address bus (default is 32).
 * @param MEM_SIZE   The number of memory locations (default is 64).
 * @param GPIO       The number of GPIO pins (default is 8).
 *
 * @input clk        Inputs clock signal.
 * @input wr_en      Write enable signal.
 * @input wr_addr    Writes Address.
 * @input wr_data    Writes Data.
 * @output rd_data_mem Output read data.
 * @inout gpio_pins  Bi-directional GPIO pins.
 */

// data_mem.v - data memory for single-cycle RISC-V CPU

module data_mem #(parameter DATA_WIDTH = 32, ADDR_WIDTH = 32, MEM_SIZE = 512, GPIO = 28) (
    input                           clk, wr_en,
    input       [ADDR_WIDTH-1:0]    instr_addr,
    input       [ADDR_WIDTH-1:0]    wr_addr, wr_data,
    output reg  [DATA_WIDTH-1:0]    rd_data_mem,
    output      [DATA_WIDTH-1:0]    instr,
    inout       [GPIO - 1    :0]    gpio_pins
);

reg [DATA_WIDTH-1:0] data_ram [0:MEM_SIZE-1];
reg [DATA_WIDTH-1:0] instr_ram [0:MEM_SIZE-1];
reg [GPIO -1 : 0] gpio_reg [0:MEM_SIZE-1];


localparam GPIO_START = 32'h2000800;
localparam GPIO_END = 32'h200081C;
localparam DMEM_START = 32'h02000000;
localparam DMEM_END = (DMEM_START + MEM_SIZE * 4);


initial begin
    $readmemh("/home/shrivishakh/project_1/project_1.sim/sim_1/behav/xsim/program_dump.hex", instr_ram);
end

assign gpio_pins = gpio_reg;
assign instr     =  instr_ram[instr_addr[31:2]];


//! combinational read logic
//! word-aligned memory access
//!if address is greater than 0x01ffffff, then it is a data memory access
//!if it is less than 0x01ffffff, then it is an instruction memory access
assign rd_data_mem = ((wr_en == 1) && (wr_addr >= 32'h02000000)) ? data_ram[wr_addr[DATA_WIDTH-1:2] % 64] : 0;

//! synchronous write logic
always @(posedge clk) begin
    if (wr_en) data_ram[wr_addr[DATA_WIDTH-2:2] % 64] <= wr_data;
end

endmodule
