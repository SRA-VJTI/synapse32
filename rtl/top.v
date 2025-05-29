`default_nettype none
module top (
    input wire clk,
    input wire rst,
    // Optional debug outputs
    output wire [31:0] pc_debug,
    output wire [31:0] instr_debug
);

    // Wires to connect CPU and memories
    wire [31:0] cpu_pc_out;
    wire [31:0] instr_to_cpu;
    wire [31:0] cpu_mem_read_addr;
    wire [31:0] cpu_mem_write_addr;
    wire [31:0] cpu_mem_write_data;
    wire [31:0] mem_read_data;
    wire cpu_mem_write_en;
    wire cpu_mem_read_en;
    wire [31:0] data_mem_addr;

    // Select the appropriate address for data memory access
    // Use write address when writing, read address when reading
    assign data_mem_addr = cpu_mem_write_en ? cpu_mem_write_addr : cpu_mem_read_addr;
    
    // Debug outputs
    assign pc_debug = cpu_pc_out;
    assign instr_debug = instr_to_cpu;

    // Instantiate the RISC-V CPU core
    riscv_cpu cpu_inst (
        .clk(clk),
        .rst(rst),
        .module_instr_in(instr_to_cpu),
        .module_read_data_in(mem_read_data),
        .module_pc_out(cpu_pc_out),
        .module_wr_data_out(cpu_mem_write_data),
        .module_mem_wr_en(cpu_mem_write_en),
        .module_mem_rd_en(cpu_mem_read_en),
        .module_read_addr(cpu_mem_read_addr),
        .module_write_addr(cpu_mem_write_addr)
    );

    // Instantiate instruction memory
    instr_mem #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32),
        .MEM_SIZE(512)
    ) instr_mem_inst (
        .instr_addr(cpu_pc_out),
        .instr(instr_to_cpu)
    );

    // Instantiate data memory
    data_mem #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32),
        .MEM_SIZE(64)
    ) data_mem_inst (
        .clk(clk),
        .wr_en(cpu_mem_write_en),
        .addr(data_mem_addr),
        .wr_data(cpu_mem_write_data),
        .rd_data_out(mem_read_data)
    );

endmodule