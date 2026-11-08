`default_nettype none
`include "memory_map.vh"

module top #(
    parameter MEM_LATENCY = 0,  // Cycles to answer an access; 0 is today's combinational memory
    parameter STORE_BUFFER_DEPTH = 4,
    parameter NUM_MSHR = 8,
    parameter [31:0] BOOT_ADDR = `INSTR_MEM_BASE,
    parameter CACHEABLE_REGIONS = 2,
    parameter [32*CACHEABLE_REGIONS-1:0] CACHEABLE_BASES = {`DATA_MEM_BASE, `INSTR_MEM_BASE},
    parameter [32*CACHEABLE_REGIONS-1:0] CACHEABLE_SIZES = {`DATA_MEM_SIZE, `INSTR_MEM_SIZE},
    parameter ICACHE_ENABLE = 1,
    parameter DCACHE_ENABLE = 1,
    parameter ICACHE_WAYS = 4,
    parameter ICACHE_SET_INDEX_BITS = 6,
    parameter ICACHE_WORD_OFFSET_BITS = 2,
    parameter DCACHE_WAYS = 4,
    parameter DCACHE_SET_INDEX_BITS = 6,
    parameter DCACHE_WORD_OFFSET_BITS = 2,
    parameter TLB_ENTRIES = 8,
    parameter MEM_PORTS = 1  // 1: fetch and data share one memory port; 2: each has its own
) (
    input wire clk,
    input wire rst,
    
    // External interrupt inputs: a machine software interrupt line next to the CLINT's msip, and
    // an interrupt line that enters the PLIC as source 2 (source 1 is the UART)
    input wire software_interrupt,
    input wire external_interrupt,
    
    // UART
    output wire uart_tx,
    input  wire uart_rx,
    
    // Optional debug outputs
    output wire [31:0] pc_debug,
    output wire [31:0] instr_debug
);

    // Wires to connect CPU and memories
    wire [31:0] cpu_pc_out;
    wire [31:0] cpu_instr_out;
    wire [31:0] mem_read_data;
    wire [31:0] ram_read_data;
    // The CPU's memory port, in front of the adapter
    wire mem_req;
    wire [31:0] mem_addr;
    wire mem_we;
    wire [3:0] mem_be;
    wire [31:0] mem_wdata;
    wire [2:0] mem_load_type;
    wire mem_instr;
    wire mem_gnt;
    wire mem_rvalid;
    wire [31:0] mem_rdata;
    wire [31:0] mem_store_addr;
    wire [3:0] mem_store_be;
    wire [31:0] mem_store_wdata;
    wire mem_store_req;
    wire mem_store_we;
    wire mem_write_fire;
    wire mem_read_fire;
    // The CPU's fetch port (MEM_PORTS 2), in front of its own adapter
    wire fetch_mem_req;
    wire [31:0] fetch_mem_addr;
    wire fetch_mem_gnt;
    wire fetch_mem_rvalid;
    wire [31:0] fetch_mem_rdata;
    wire [31:0] fetch_store_addr;
    wire [31:0] fetch_ram_data;
    
    // Timer module wires
    wire [31:0] timer_read_data;
    wire timer_valid;
    wire timer_interrupt;
    wire machine_software_interrupt;
    wire [63:0] mtime;
    wire uart_interrupt;
    wire plic_machine_interrupt;
    wire plic_supervisor_interrupt;
    
    // UART module wires
    wire [31:0] uart_read_data;
    wire uart_valid;
    wire uart_access;
    wire [31:0] plic_read_data;
    wire plic_valid;
    wire plic_access;
    
    // Memory address decoding using memory map
    wire timer_access;
    wire ram_access;
    wire [31:0] mmu_instr_l1_pte_addr;
    wire [31:0] mmu_instr_l0_pte_addr;
    wire [31:0] mmu_data_l1_pte_addr;
    wire [31:0] mmu_data_l0_pte_addr;
    wire [31:0] mmu_instr_l1_pte_value;
    wire [31:0] mmu_instr_l0_pte_value;
    wire [31:0] mmu_data_l1_pte_value;
    wire [31:0] mmu_data_l0_pte_value;
    wire mmu_instr_l1_pte_backed;
    wire mmu_instr_l0_pte_backed;
    wire mmu_data_l1_pte_backed;
    wire mmu_data_l0_pte_backed;

    // Use memory map macros for clean address decoding. Devices answer data accesses only.
    assign timer_access    = `IS_TIMER_MEM(mem_store_addr) && !mem_instr;
    assign uart_access     = `IS_UART_MEM(mem_store_addr) && !mem_instr;
    assign plic_access     = `IS_PLIC_MEM(mem_store_addr) && !mem_instr;
    assign ram_access      = `IS_DATA_MEM(mem_store_addr) || `IS_INSTR_MEM(mem_store_addr);
    
    // Multiplex read data based on address
    assign mem_read_data = timer_access ? timer_read_data :
                          uart_access ? uart_read_data :
                          plic_access ? plic_read_data :
                          ram_access ? ram_read_data : 32'h00000000;
    
    // Debug outputs
    assign pc_debug = cpu_pc_out;
    assign instr_debug = cpu_instr_out;

    mem_adapter #(.RESPONSE_LATENCY(MEM_LATENCY)) mem_adapter_inst (
        .clk(clk),
        .rst(rst),
        .req(mem_req),
        .addr(mem_addr),
        .we(mem_we),
        .be(mem_be),
        .wdata(mem_wdata),
        .gnt(mem_gnt),
        .rvalid(mem_rvalid),
        .rdata(mem_rdata),
        .store_req(mem_store_req),
        .store_addr(mem_store_addr),
        .store_we(mem_store_we),
        .store_be(mem_store_be),
        .store_wdata(mem_store_wdata),
        .write_fire(mem_write_fire),
        .read_fire(mem_read_fire),
        .store_rdata(mem_read_data)
    );

    // The fetch port reads RAM only, so a fetch outside RAM reads 0 with either port count.
    generate
        if (MEM_PORTS == 2) begin : g_fetch_port
            wire fetch_ram_access = `IS_DATA_MEM(fetch_store_addr) || `IS_INSTR_MEM(fetch_store_addr);

            mem_adapter #(.RESPONSE_LATENCY(MEM_LATENCY)) fetch_adapter_inst (
                .clk(clk),
                .rst(rst),
                .req(fetch_mem_req),
                .addr(fetch_mem_addr),
                .we(1'b0),
                .be(4'b0),
                .wdata(32'b0),
                .gnt(fetch_mem_gnt),
                .rvalid(fetch_mem_rvalid),
                .rdata(fetch_mem_rdata),
                .store_req(),
                .store_addr(fetch_store_addr),
                .store_we(),
                .store_be(),
                .store_wdata(),
                .write_fire(),
                .read_fire(),
                .store_rdata(fetch_ram_access ? fetch_ram_data : 32'b0)
            );
        end else begin : g_no_fetch_port
            assign fetch_mem_gnt = 1'b0;
            assign fetch_mem_rvalid = 1'b0;
            assign fetch_mem_rdata = 32'b0;
            assign fetch_store_addr = 32'b0;
        end
    endgenerate

    // Instantiate the RISC-V CPU core
    riscv_cpu #(
        .STORE_BUFFER_DEPTH(STORE_BUFFER_DEPTH),
        .NUM_MSHR(NUM_MSHR),
        .BOOT_ADDR(BOOT_ADDR),
        .CACHEABLE_REGIONS(CACHEABLE_REGIONS),
        .CACHEABLE_BASES(CACHEABLE_BASES),
        .CACHEABLE_SIZES(CACHEABLE_SIZES),
        .ICACHE_ENABLE(ICACHE_ENABLE),
        .DCACHE_ENABLE(DCACHE_ENABLE),
        .ICACHE_WAYS(ICACHE_WAYS),
        .ICACHE_SET_INDEX_BITS(ICACHE_SET_INDEX_BITS),
        .ICACHE_WORD_OFFSET_BITS(ICACHE_WORD_OFFSET_BITS),
        .DCACHE_WAYS(DCACHE_WAYS),
        .DCACHE_SET_INDEX_BITS(DCACHE_SET_INDEX_BITS),
        .DCACHE_WORD_OFFSET_BITS(DCACHE_WORD_OFFSET_BITS),
        .TLB_ENTRIES(TLB_ENTRIES),
        .MEM_PORTS(MEM_PORTS)
    ) cpu_inst (
        .clk(clk),
        .rst(rst),
        .mem_req(mem_req),
        .mem_addr(mem_addr),
        .mem_we(mem_we),
        .mem_be(mem_be),
        .mem_wdata(mem_wdata),
        .mem_load_type(mem_load_type),
        .mem_instr(mem_instr),
        .mem_gnt(mem_gnt),
        .mem_rvalid(mem_rvalid),
        .mem_rdata(mem_rdata),
        .fetch_mem_req(fetch_mem_req),
        .fetch_mem_addr(fetch_mem_addr),
        .fetch_mem_gnt(fetch_mem_gnt),
        .fetch_mem_rvalid(fetch_mem_rvalid),
        .fetch_mem_rdata(fetch_mem_rdata),
        .module_pc_out(cpu_pc_out),
        .module_instr_out(cpu_instr_out),
        .timer_interrupt(timer_interrupt),
        .machine_software_interrupt(machine_software_interrupt || software_interrupt),
        .machine_external_interrupt(plic_machine_interrupt),
        .supervisor_external_interrupt(plic_supervisor_interrupt),
        .mtime_in(mtime)
    );

    // Instantiate unified memory
    unified_mem #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32),
        .MEM_SIZE(17039360)  // (64MB + 1MB) / 4 words
    ) unified_mem_inst (
        .clk(clk),
        // The memory port reads through the formatted read port, the fetch port (MEM_PORTS 2) through the other.
        .instr_addr(fetch_store_addr),
        .instr_addr_p2(mem_store_addr),
        .data_wr_req(mem_store_req && mem_store_we && ram_access),
        .data_rd_en(mem_store_req && !mem_store_we && ram_access),
        // A write lands once, in the cycle the adapter commits it.
        .wr_en(mem_write_fire && ram_access),
        .write_byte_enable(mem_store_be),
        .wr_data(mem_store_wdata),
        .load_type(mem_load_type),
        // The walker reads PTEs over the data interface now, so the side channel is unused.
        .pte_wr_en_a(1'b0),
        .pte_wr_addr_a(32'b0),
        .pte_wr_value_a(32'b0),
        .pte_wr_en_b(1'b0),
        .pte_wr_addr_b(32'b0),
        .pte_wr_value_b(32'b0),
        .pte_rd_addr_a(32'b0),
        .pte_rd_addr_b(32'b0),
        .pte_rd_addr_c(32'b0),
        .pte_rd_addr_d(32'b0),
        .instr(fetch_ram_data),
        .instr_p2(ram_read_data),
        .pte_rd_value_a(mmu_instr_l1_pte_value),
        .pte_rd_value_b(mmu_instr_l0_pte_value),
        .pte_rd_value_c(mmu_data_l1_pte_value),
        .pte_rd_value_d(mmu_data_l0_pte_value),
        .pte_rd_backed_a(mmu_instr_l1_pte_backed),
        .pte_rd_backed_b(mmu_instr_l0_pte_backed),
        .pte_rd_backed_c(mmu_data_l1_pte_backed),
        .pte_rd_backed_d(mmu_data_l0_pte_backed)
    );
    
    // Instantiate timer module
    timer timer_inst (
        .clk(clk),
        .rst(rst),
        .addr(mem_store_addr),
        .write_data(mem_store_wdata),
        .write_enable(mem_write_fire && timer_access),
        .read_enable(mem_read_fire && timer_access),
        .read_data(timer_read_data),
        .timer_valid(timer_valid),
        .timer_interrupt(timer_interrupt),
        .machine_software_interrupt(machine_software_interrupt),
        .mtime_out(mtime)
    );

    // Instantiate the UART module
    uart uart_inst (
        .clk(clk),
        .rst(rst),
        .addr(mem_store_addr),
        .write_data(mem_store_wdata),
        .write_enable(mem_write_fire && uart_access),
        .read_enable(mem_read_fire && uart_access),
        .read_data(uart_read_data),
        .uart_valid(uart_valid),
        .interrupt(uart_interrupt),
        .tx(uart_tx),
        .rx(uart_rx)
    );

    plic plic_inst (
        .clk(clk),
        .rst(rst),
        .addr(mem_store_addr),
        .write_data(mem_store_wdata),
        .write_enable(mem_write_fire && plic_access),
        .read_enable(mem_read_fire && plic_access),
        .read_data(plic_read_data),
        .plic_valid(plic_valid),
        .source_irq({external_interrupt, uart_interrupt}),
        .machine_external_interrupt(plic_machine_interrupt),
        .supervisor_external_interrupt(plic_supervisor_interrupt)
    );

`ifdef COCOTB_SIM
`ifdef VM_TRACE
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
`endif

endmodule
