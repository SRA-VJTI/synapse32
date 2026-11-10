`default_nettype none
`include "memory_map.vh"

module top #(
    parameter MEM_LATENCY = 0,  // Cycles to answer an access; 0 is today's combinational memory
    parameter FETCH_LATENCY = MEM_LATENCY,  // Fetch side only, when it should differ
    parameter STORE_BUFFER_DEPTH = 4,
    parameter NUM_MSHR = 8
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
    wire [31:0] instr_read_data;
    // The CPU's memory ports, each in front of an adapter
    wire instr_mem_req;
    wire [31:0] instr_mem_addr;
    wire instr_mem_gnt;
    wire instr_mem_rvalid;
    wire [31:0] instr_mem_rdata;
    wire data_mem_req;
    wire [31:0] data_mem_addr;
    wire data_mem_we;
    wire [3:0] data_mem_be;
    wire [31:0] data_mem_wdata;
    wire [2:0] data_mem_load_type;
    wire data_mem_gnt;
    wire data_mem_rvalid;
    wire [31:0] data_mem_rdata;
    wire [31:0] instr_store_addr;
    wire [31:0] instr_store_rdata;
    wire [31:0] data_store_addr;
    wire [3:0] data_store_be;
    wire [31:0] data_store_wdata;
    wire data_store_req;
    wire data_store_we;
    wire data_write_fire;
    wire data_read_fire;
    
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

    // Use memory map macros for clean address decoding
    assign timer_access    = `IS_TIMER_MEM(data_store_addr);
    assign uart_access     = `IS_UART_MEM(data_store_addr);
    assign plic_access     = `IS_PLIC_MEM(data_store_addr);
    assign ram_access      = `IS_DATA_MEM(data_store_addr) || `IS_INSTR_MEM(data_store_addr);
    
    // Multiplex read data based on address
    assign mem_read_data = timer_access ? timer_read_data :
                          uart_access ? uart_read_data :
                          plic_access ? plic_read_data :
                          ram_access ? instr_read_data : 32'h00000000;
    
    // Debug outputs
    assign pc_debug = cpu_pc_out;
    assign instr_debug = cpu_instr_out;

    mem_adapter #(.RESPONSE_LATENCY(FETCH_LATENCY)) instr_adapter (
        .clk(clk),
        .rst(rst),
        .req(instr_mem_req),
        .addr(instr_mem_addr),
        .we(1'b0),
        .be(4'b0),
        .wdata(32'b0),
        .gnt(instr_mem_gnt),
        .rvalid(instr_mem_rvalid),
        .rdata(instr_mem_rdata),
        .store_req(),
        .store_addr(instr_store_addr),
        .store_we(),
        .store_be(),
        .store_wdata(),
        .write_fire(),
        .read_fire(),
        .store_rdata(instr_store_rdata)
    );

    mem_adapter #(.RESPONSE_LATENCY(MEM_LATENCY)) data_adapter (
        .clk(clk),
        .rst(rst),
        .req(data_mem_req),
        .addr(data_mem_addr),
        .we(data_mem_we),
        .be(data_mem_be),
        .wdata(data_mem_wdata),
        .gnt(data_mem_gnt),
        .rvalid(data_mem_rvalid),
        .rdata(data_mem_rdata),
        .store_req(data_store_req),
        .store_addr(data_store_addr),
        .store_we(data_store_we),
        .store_be(data_store_be),
        .store_wdata(data_store_wdata),
        .write_fire(data_write_fire),
        .read_fire(data_read_fire),
        .store_rdata(mem_read_data)
    );

    // Instantiate the RISC-V CPU core
    riscv_cpu #(
        .STORE_BUFFER_DEPTH(STORE_BUFFER_DEPTH),
        .NUM_MSHR(NUM_MSHR)
    ) cpu_inst (
        .clk(clk),
        .rst(rst),
        .instr_mem_req(instr_mem_req),
        .instr_mem_addr(instr_mem_addr),
        .instr_mem_gnt(instr_mem_gnt),
        .instr_mem_rvalid(instr_mem_rvalid),
        .instr_mem_rdata(instr_mem_rdata),
        .data_mem_req(data_mem_req),
        .data_mem_addr(data_mem_addr),
        .data_mem_we(data_mem_we),
        .data_mem_be(data_mem_be),
        .data_mem_wdata(data_mem_wdata),
        .data_mem_load_type(data_mem_load_type),
        .data_mem_gnt(data_mem_gnt),
        .data_mem_rvalid(data_mem_rvalid),
        .data_mem_rdata(data_mem_rdata),
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
        .instr_addr(instr_store_addr),
        .instr_addr_p2(data_store_addr),
        .data_wr_req(data_store_req && data_store_we && ram_access),
        .data_rd_en(data_store_req && !data_store_we && ram_access),
        // A write lands once, in the cycle the adapter commits it.
        .wr_en(data_write_fire && ram_access),
        .write_byte_enable(data_store_be),
        .wr_data(data_store_wdata),
        .load_type(data_mem_load_type),
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
        .instr(instr_store_rdata),
        .instr_p2(instr_read_data),
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
        .addr(data_store_addr),
        .write_data(data_store_wdata),
        .write_enable(data_write_fire && timer_access),
        .read_enable(data_read_fire && timer_access),
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
        .addr(data_store_addr),
        .write_data(data_store_wdata),
        .write_enable(data_write_fire && uart_access),
        .read_enable(data_read_fire && uart_access),
        .read_data(uart_read_data),
        .uart_valid(uart_valid),
        .interrupt(uart_interrupt),
        .tx(uart_tx),
        .rx(uart_rx)
    );

    plic plic_inst (
        .clk(clk),
        .rst(rst),
        .addr(data_store_addr),
        .write_data(data_store_wdata),
        .write_enable(data_write_fire && plic_access),
        .read_enable(data_read_fire && plic_access),
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
