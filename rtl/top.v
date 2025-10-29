`default_nettype none
`include "memory_map.vh"

module top (
    input wire clk,
    input wire rst,

    // External interrupt inputs
    input wire software_interrupt,
    input wire external_interrupt,

    // UART output
    output wire uart_tx,

    // Optional debug outputs
    output wire [31:0] pc_debug,
    output wire [31:0] instr_debug,

    // RVFI interface for formal verification
    output wire        rvfi_valid,
    output wire [63:0] rvfi_order,
    output wire [31:0] rvfi_insn,
    output wire        rvfi_trap,
    output wire        rvfi_halt,
    output wire        rvfi_intr,
    output wire [1:0]  rvfi_mode,
    output wire [1:0]  rvfi_ixl,
    output wire [4:0]  rvfi_rs1_addr,
    output wire [4:0]  rvfi_rs2_addr,
    output wire [31:0] rvfi_rs1_rdata,
    output wire [31:0] rvfi_rs2_rdata,
    output wire [4:0]  rvfi_rd_addr,
    output wire [31:0] rvfi_rd_wdata,
    output wire [31:0] rvfi_pc_rdata,
    output wire [31:0] rvfi_pc_wdata,
    output wire [31:0] rvfi_mem_addr,
    output wire [3:0]  rvfi_mem_rmask,
    output wire [31:0] rvfi_mem_rdata,
    output wire [31:0] rvfi_mem_wdata,
    output wire [3:0]  rvfi_mem_wmask,
    output wire [31:0] rvfi_csr_mstatus_rmask,
    output wire [31:0] rvfi_csr_mstatus_wmask,
    output wire [31:0] rvfi_csr_mstatus_rdata,
    output wire [31:0] rvfi_csr_mstatus_wdata,
    output wire [31:0] rvfi_csr_misa_rmask,
    output wire [31:0] rvfi_csr_misa_wmask,
    output wire [31:0] rvfi_csr_misa_rdata,
    output wire [31:0] rvfi_csr_misa_wdata,
    output wire [31:0] rvfi_csr_mie_rmask,
    output wire [31:0] rvfi_csr_mie_wmask,
    output wire [31:0] rvfi_csr_mie_rdata,
    output wire [31:0] rvfi_csr_mie_wdata,
    output wire [31:0] rvfi_csr_mtvec_rmask,
    output wire [31:0] rvfi_csr_mtvec_wmask,
    output wire [31:0] rvfi_csr_mtvec_rdata,
    output wire [31:0] rvfi_csr_mtvec_wdata,
    output wire [31:0] rvfi_csr_mscratch_rmask,
    output wire [31:0] rvfi_csr_mscratch_wmask,
    output wire [31:0] rvfi_csr_mscratch_rdata,
    output wire [31:0] rvfi_csr_mscratch_wdata,
    output wire [31:0] rvfi_csr_mepc_rmask,
    output wire [31:0] rvfi_csr_mepc_wmask,
    output wire [31:0] rvfi_csr_mepc_rdata,
    output wire [31:0] rvfi_csr_mepc_wdata,
    output wire [31:0] rvfi_csr_mcause_rmask,
    output wire [31:0] rvfi_csr_mcause_wmask,
    output wire [31:0] rvfi_csr_mcause_rdata,
    output wire [31:0] rvfi_csr_mcause_wdata,
    output wire [31:0] rvfi_csr_mtval_rmask,
    output wire [31:0] rvfi_csr_mtval_wmask,
    output wire [31:0] rvfi_csr_mtval_rdata,
    output wire [31:0] rvfi_csr_mtval_wdata,
    output wire [31:0] rvfi_csr_mip_rmask,
    output wire [31:0] rvfi_csr_mip_wmask,
    output wire [31:0] rvfi_csr_mip_rdata,
    output wire [31:0] rvfi_csr_mip_wdata
);

    // Size memories differently for formal vs functional builds
`ifdef FORMAL
    localparam integer INSTR_MEM_WORDS = 32;
    localparam integer DATA_MEM_BYTES  = 64;
`else
    localparam integer INSTR_MEM_WORDS = 4096;  // 16KB instruction space
    localparam integer DATA_MEM_BYTES  = 4096;  // 4KB data space
`endif

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
    wire [3:0] cpu_write_byte_enable;  // Write byte enables
    wire [2:0] cpu_load_type;          // Load type
    wire [31:0] instr_read_data;

    // Timer module wires
    wire [31:0] timer_read_data;
    wire timer_valid;
    wire timer_interrupt;

    // UART module wires
    wire [31:0] uart_read_data;
    wire uart_valid;
    wire uart_access;

    // Memory address decoding using memory map
    wire data_mem_access;
    wire timer_access;
    wire instr_mem_access;

    // Use memory map macros for clean address decoding
    assign data_mem_access = `IS_DATA_MEM(data_mem_addr);
    assign timer_access = `IS_TIMER_MEM(data_mem_addr);
    assign uart_access = `IS_UART_MEM(data_mem_addr);
    assign instr_mem_access = `IS_INSTR_MEM(data_mem_addr);

    // Select the appropriate address for memory access
    assign data_mem_addr = cpu_mem_write_en ? cpu_mem_write_addr : cpu_mem_read_addr;

    // Multiplex read data based on address
    assign mem_read_data = timer_access ? timer_read_data :
                          data_mem_access ? data_mem_read_data :
                          uart_access ? uart_read_data :
                            instr_mem_access ? instr_read_data : 32'h00000000;

    // Debug outputs
    assign pc_debug = cpu_pc_out;
    assign instr_debug = instr_to_cpu;

    // Data memory read data (separate wire for clarity)
    wire [31:0] data_mem_read_data;

    // Instantiate the RISC-V CPU core
    riscv_cpu cpu_inst (
        .clk(clk),
        .rst(rst),
        .timer_interrupt(timer_interrupt),
        .software_interrupt(software_interrupt),
        .external_interrupt(external_interrupt),
        .module_instr_in(instr_to_cpu),
        .module_read_data_in(mem_read_data),
        .module_pc_out(cpu_pc_out),
        .module_wr_data_out(cpu_mem_write_data),
        .module_mem_wr_en(cpu_mem_write_en),
        .module_mem_rd_en(cpu_mem_read_en),
        .module_read_addr(cpu_mem_read_addr),
        .module_write_addr(cpu_mem_write_addr),
        .module_write_byte_enable(cpu_write_byte_enable),
        .module_load_type(cpu_load_type),

        // RVFI interface connections
        .rvfi_valid(rvfi_valid),
        .rvfi_order(rvfi_order),
        .rvfi_insn(rvfi_insn),
        .rvfi_trap(rvfi_trap),
        .rvfi_halt(rvfi_halt),
        .rvfi_intr(rvfi_intr),
        .rvfi_mode(rvfi_mode),
        .rvfi_ixl(rvfi_ixl),
        .rvfi_rs1_addr(rvfi_rs1_addr),
        .rvfi_rs2_addr(rvfi_rs2_addr),
        .rvfi_rs1_rdata(rvfi_rs1_rdata),
        .rvfi_rs2_rdata(rvfi_rs2_rdata),
        .rvfi_rd_addr(rvfi_rd_addr),
        .rvfi_rd_wdata(rvfi_rd_wdata),
        .rvfi_pc_rdata(rvfi_pc_rdata),
        .rvfi_pc_wdata(rvfi_pc_wdata),
        .rvfi_mem_addr(rvfi_mem_addr),
        .rvfi_mem_rmask(rvfi_mem_rmask),
        .rvfi_mem_rdata(rvfi_mem_rdata),
        .rvfi_mem_wdata(rvfi_mem_wdata),
        .rvfi_mem_wmask(rvfi_mem_wmask),
        .rvfi_csr_mstatus_rmask(rvfi_csr_mstatus_rmask),
        .rvfi_csr_mstatus_wmask(rvfi_csr_mstatus_wmask),
        .rvfi_csr_mstatus_rdata(rvfi_csr_mstatus_rdata),
        .rvfi_csr_mstatus_wdata(rvfi_csr_mstatus_wdata),
        .rvfi_csr_misa_rmask(rvfi_csr_misa_rmask),
        .rvfi_csr_misa_wmask(rvfi_csr_misa_wmask),
        .rvfi_csr_misa_rdata(rvfi_csr_misa_rdata),
        .rvfi_csr_misa_wdata(rvfi_csr_misa_wdata),
        .rvfi_csr_mie_rmask(rvfi_csr_mie_rmask),
        .rvfi_csr_mie_wmask(rvfi_csr_mie_wmask),
        .rvfi_csr_mie_rdata(rvfi_csr_mie_rdata),
        .rvfi_csr_mie_wdata(rvfi_csr_mie_wdata),
        .rvfi_csr_mtvec_rmask(rvfi_csr_mtvec_rmask),
        .rvfi_csr_mtvec_wmask(rvfi_csr_mtvec_wmask),
        .rvfi_csr_mtvec_rdata(rvfi_csr_mtvec_rdata),
        .rvfi_csr_mtvec_wdata(rvfi_csr_mtvec_wdata),
        .rvfi_csr_mscratch_rmask(rvfi_csr_mscratch_rmask),
        .rvfi_csr_mscratch_wmask(rvfi_csr_mscratch_wmask),
        .rvfi_csr_mscratch_rdata(rvfi_csr_mscratch_rdata),
        .rvfi_csr_mscratch_wdata(rvfi_csr_mscratch_wdata),
        .rvfi_csr_mepc_rmask(rvfi_csr_mepc_rmask),
        .rvfi_csr_mepc_wmask(rvfi_csr_mepc_wmask),
        .rvfi_csr_mepc_rdata(rvfi_csr_mepc_rdata),
        .rvfi_csr_mepc_wdata(rvfi_csr_mepc_wdata),
        .rvfi_csr_mcause_rmask(rvfi_csr_mcause_rmask),
        .rvfi_csr_mcause_wmask(rvfi_csr_mcause_wmask),
        .rvfi_csr_mcause_rdata(rvfi_csr_mcause_rdata),
        .rvfi_csr_mcause_wdata(rvfi_csr_mcause_wdata),
        .rvfi_csr_mtval_rmask(rvfi_csr_mtval_rmask),
        .rvfi_csr_mtval_wmask(rvfi_csr_mtval_wmask),
        .rvfi_csr_mtval_rdata(rvfi_csr_mtval_rdata),
        .rvfi_csr_mtval_wdata(rvfi_csr_mtval_wdata),
        .rvfi_csr_mip_rmask(rvfi_csr_mip_rmask),
        .rvfi_csr_mip_wmask(rvfi_csr_mip_wmask),
        .rvfi_csr_mip_rdata(rvfi_csr_mip_rdata),
        .rvfi_csr_mip_wdata(rvfi_csr_mip_wdata)
    );

    // Instantiate instruction memory
    instr_mem #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32),
        .MEM_SIZE(INSTR_MEM_WORDS)
    ) instr_mem_inst (
        .instr_addr(cpu_pc_out),
        .instr_addr_p2(data_mem_addr),
        .load_type(cpu_load_type),
        .instr(instr_to_cpu),
        .instr_p2(instr_read_data)
    );

    // Instantiate data memory
    data_mem #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32),
        .MEM_SIZE(DATA_MEM_BYTES)
    ) data_mem_inst (
        .clk(clk),
        .wr_en(cpu_mem_write_en && data_mem_access),
        .rd_en(cpu_mem_read_en && data_mem_access),
        .write_byte_enable(cpu_write_byte_enable),
        .load_type(cpu_load_type),
        .addr(data_mem_addr - `DATA_MEM_BASE),
        .wr_data(cpu_mem_write_data),
        .rd_data_out(data_mem_read_data)
    );

    // Instantiate timer module
    timer timer_inst (
        .clk(clk),
        .rst(rst),
        .addr(data_mem_addr),
        .write_data(cpu_mem_write_data),
        .write_enable(cpu_mem_write_en && timer_access),
        .read_enable(cpu_mem_read_en && timer_access),
        .read_data(timer_read_data),
        .timer_valid(timer_valid),
        .timer_interrupt(timer_interrupt)
    );

    // Instantiate the UART module
    uart uart_inst (
        .clk(clk),
        .rst(rst),
        .addr(data_mem_addr),
        .write_data(cpu_mem_write_data),
        .write_enable(cpu_mem_write_en && uart_access),
        .read_enable(cpu_mem_read_en && uart_access),
        .read_data(uart_read_data),
        .uart_valid(uart_valid),
        .tx(uart_tx)
    );

`ifdef COCOTB_SIM
    // Add parameter to control FST file path
    reg [1023:0] dumpfile_path = "riscv_cpu.fst"; // Default path

    initial begin
        // Check for custom dump file name from plusargs
        if (!$value$plusargs("dumpfile=%s", dumpfile_path)) begin
            // Use default if not specified
            dumpfile_path = "riscv_cpu.fst";
        end

        // Set up wave dumping
        $dumpfile(dumpfile_path);
        $dumpvars(0, top);
        $display("FST dump file: %s", dumpfile_path);
    end
`endif

endmodule
