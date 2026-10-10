`default_nettype none
`include "memory_map.vh"

module top #(
    parameter MEM_LATENCY = 0,  // Cycles to answer an access; 0 is today's combinational memory
    parameter FETCH_LATENCY = MEM_LATENCY  // Fetch side only, when it should differ
) (
    input wire clk,
    input wire rst,
    
    // External interrupt inputs
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
    wire [31:0] instr_to_cpu;
    wire [31:0] cpu_mem_read_addr;
    wire [31:0] cpu_mem_write_addr;
    wire [31:0] cpu_mem_write_data;
    wire [31:0] mem_read_data;
    wire cpu_mem_write_en;
    wire cpu_mem_read_en;
    wire cpu_data_write_intent;
    wire [31:0] data_mem_addr;
    wire [3:0] cpu_write_byte_enable;  // Write byte enables
    wire [2:0] cpu_load_type;          // Load type
    wire cpu_load_page_fault;
    wire cpu_store_page_fault;
    wire [31:0] cpu_page_fault_addr;
    wire cpu_data_mmu_enable;
    wire [1:0] cpu_data_privilege;
    wire [31:0] cpu_satp;
    wire cpu_data_sum;
    wire cpu_data_mxr;
    wire [31:0] instr_read_data;
    // Memory interface: the core's requests and the adapters' responses.
    wire cpu_instr_gnt;
    wire cpu_instr_rvalid;
    wire cpu_data_req;
    wire cpu_data_gnt;
    wire cpu_data_rvalid;
    wire [31:0] cpu_data_rdata;
    wire [31:0] instr_store_addr;
    wire [31:0] instr_store_rdata;
    wire [31:0] data_store_addr;
    wire [3:0] data_store_be;
    wire [31:0] data_store_wdata;
    wire data_store_we;
    wire data_write_fire;
    wire data_read_fire;
    
    // Timer module wires
    wire [31:0] timer_read_data;
    wire timer_valid;
    wire timer_interrupt;
    wire uart_interrupt;
    wire plic_interrupt;
    wire external_interrupt_combined;
    
    // UART module wires
    wire [31:0] uart_read_data;
    wire uart_valid;
    wire uart_access;
    wire [31:0] plic_read_data;
    wire plic_valid;
    wire plic_access;
    
    // Memory address decoding using memory map
    wire data_mem_access;
    wire timer_access;
    wire instr_mem_access;
    wire ram_access;
    wire translated_data_access;
    wire [31:0] phys_data_addr;   // physical address after MMU walk (or virtual if MMU off)
    wire [31:0] phys_instr_addr;
    wire [31:0] mmu_data_fault_addr;
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
    // Sequential walker: the MMU reads PTEs over the data memory interface.
    wire mmu_instr_ready;
    wire mmu_data_ready;
    wire mmu_walk_req;
    wire [31:0] mmu_walk_addr;
    wire mmu_walk_gnt;
    wire mmu_walk_rvalid;
    wire cpu_tlb_flush;
    wire data_bus_walk_sel;
    wire data_bus_walk_owns;
    reg data_bus_walk_owner_q;
    wire data_store_req;
    wire adapter_data_gnt;
    wire adapter_data_rvalid;
    wire cpu_data_bus_req;

    assign external_interrupt_combined = external_interrupt | plic_interrupt;

    // Use memory map macros for clean address decoding
    assign translated_data_access = cpu_data_mmu_enable && (cpu_mem_write_en || cpu_mem_read_en);
    assign cpu_page_fault_addr = mmu_data_fault_addr;
    assign data_mem_access = !translated_data_access && `IS_DATA_MEM(data_store_addr);
    assign timer_access    = `IS_TIMER_MEM(data_store_addr);
    assign uart_access     = `IS_UART_MEM(data_store_addr);
    assign plic_access     = `IS_PLIC_MEM(data_store_addr);
    assign instr_mem_access = !translated_data_access && `IS_INSTR_MEM(data_store_addr);
    // RAM covers translated accesses that aren't peripheral, plus direct RAM accesses.
    assign ram_access = (translated_data_access && !timer_access && !uart_access && !plic_access)
                        || data_mem_access || instr_mem_access;
    
    // Select the appropriate address for memory access
    assign data_mem_addr = cpu_mem_write_en ? cpu_mem_write_addr : cpu_mem_read_addr;
    
    // Multiplex read data based on address
    assign mem_read_data = timer_access ? timer_read_data :
                          uart_access ? uart_read_data :
                          plic_access ? plic_read_data :
                          ram_access ? instr_read_data : 32'h00000000;
    
    // Debug outputs
    assign pc_debug = cpu_pc_out;
    assign instr_debug = instr_to_cpu;
    
    // Memory adapters: the core presents a physical address and waits for the response.
    // A faulting access is never accepted, or it would commit after the trap.
    assign cpu_data_req = (cpu_mem_read_en || cpu_mem_write_en) &&
                          !cpu_load_page_fault && !cpu_store_page_fault;
    // The core may only go to memory once its translation is available.
    assign cpu_data_bus_req = cpu_data_req && mmu_data_ready;
    // One master at a time on the data interface; the core goes first, as its instruction is older.
    assign data_bus_walk_sel = mmu_walk_req && !cpu_data_bus_req;
    assign data_bus_walk_owns = data_bus_walk_owner_q || (data_bus_walk_sel && adapter_data_gnt);
    assign mmu_walk_gnt = adapter_data_gnt && data_bus_walk_sel;
    assign mmu_walk_rvalid = adapter_data_rvalid && data_bus_walk_owns;
    assign cpu_data_gnt = adapter_data_gnt && !data_bus_walk_sel;
    assign cpu_data_rvalid = adapter_data_rvalid && !data_bus_walk_owns;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            data_bus_walk_owner_q <= 1'b0;
        end else if (adapter_data_rvalid) begin
            data_bus_walk_owner_q <= 1'b0;
        end else if (data_bus_walk_sel && adapter_data_gnt) begin
            data_bus_walk_owner_q <= 1'b1;
        end
    end

    mem_adapter #(.RESPONSE_LATENCY(FETCH_LATENCY)) instr_adapter (
        .clk(clk),
        .rst(rst),
        // A fetch goes to memory only once translated; a fetch that faults never does.
        .req(mmu_instr_ready && !cpu_instr_page_fault),
        .addr(phys_instr_addr),
        .we(1'b0),
        .be(4'b0),
        .wdata(32'b0),
        .gnt(cpu_instr_gnt),
        .rvalid(cpu_instr_rvalid),
        .rdata(instr_to_cpu),
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
        .req(data_bus_walk_sel ? 1'b1 : cpu_data_bus_req),
        .addr(data_bus_walk_sel ? mmu_walk_addr : phys_data_addr),
        .we(data_bus_walk_sel ? 1'b0 : cpu_mem_write_en),
        .be(data_bus_walk_sel ? 4'b1111 : cpu_write_byte_enable),
        .wdata(data_bus_walk_sel ? 32'b0 : cpu_mem_write_data),
        .gnt(adapter_data_gnt),
        .rvalid(adapter_data_rvalid),
        .rdata(cpu_data_rdata),
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
    riscv_cpu cpu_inst (
        .clk(clk),
        .rst(rst),
        .timer_interrupt(timer_interrupt),
        .software_interrupt(software_interrupt),
        .external_interrupt(external_interrupt_combined),
        .module_instr_in(instr_to_cpu),
        .module_read_data_in(cpu_data_rdata),
        .module_pc_out(cpu_pc_out),
        .module_wr_data_out(cpu_mem_write_data),
        .module_mem_wr_en(cpu_mem_write_en),
        .module_mem_rd_en(cpu_mem_read_en),
        .module_read_addr(cpu_mem_read_addr),
        .module_write_addr(cpu_mem_write_addr),
        .module_write_byte_enable(cpu_write_byte_enable),
        .module_load_type(cpu_load_type),
        .module_load_page_fault_in(cpu_load_page_fault),
        .module_store_page_fault_in(cpu_store_page_fault),
        .module_page_fault_addr_in(cpu_page_fault_addr),
        .module_instr_page_fault_in(cpu_instr_page_fault),
        .module_instr_gnt_in(cpu_instr_gnt),
        .module_instr_rvalid_in(cpu_instr_rvalid),
        .module_data_gnt_in(cpu_data_gnt),
        .module_data_rvalid_in(cpu_data_rvalid),
        .module_data_write_intent_out(cpu_data_write_intent),
        .module_tlb_flush_out(cpu_tlb_flush),
        .module_data_mmu_enable_out(cpu_data_mmu_enable),
        .module_data_privilege_out(cpu_data_privilege),
        .module_satp_out(cpu_satp),
        .module_data_sum_out(cpu_data_sum),
        .module_data_mxr_out(cpu_data_mxr),
        .module_instr_mmu_enable_out(cpu_instr_mmu_enable),
        .module_instr_privilege_out(cpu_instr_privilege)
    );

    wire cpu_instr_mmu_enable;
    wire [1:0] cpu_instr_privilege;
    wire cpu_instr_page_fault;

    sv32_mmu mmu_inst (
        .clk(clk),
        .rst(rst),
        .flush_tlb(cpu_tlb_flush),
        .satp(cpu_satp),
        .data_sum(cpu_data_sum),
        .data_mxr(cpu_data_mxr),
        .instr_translate_enable(cpu_instr_mmu_enable),
        .instr_virtual_addr(cpu_pc_out),
        .instr_priv_mode(cpu_instr_privilege),
        .instr_phys_addr(phys_instr_addr),
        .instr_ready(mmu_instr_ready),
        .instr_page_fault(cpu_instr_page_fault),
        .data_translate_enable(translated_data_access),
        .data_virtual_addr(data_mem_addr),
        .data_rd_en(cpu_mem_read_en),
        .data_wr_req(cpu_data_write_intent),
        .data_priv_mode(cpu_data_privilege),
        .data_phys_addr(phys_data_addr),
        .data_ready(mmu_data_ready),
        .data_load_page_fault(cpu_load_page_fault),
        .data_store_page_fault(cpu_store_page_fault),
        .data_fault_addr(mmu_data_fault_addr),
        .walk_req(mmu_walk_req),
        .walk_addr(mmu_walk_addr),
        .walk_gnt(mmu_walk_gnt),
        .walk_rvalid(mmu_walk_rvalid),
        .walk_rdata(cpu_data_rdata)
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
        .wr_en(data_write_fire && ram_access && !cpu_store_page_fault),
        .write_byte_enable(data_store_be),
        .wr_data(data_store_wdata),
        // A walk reads a whole PTE word; the core's load type applies to its own accesses.
        .load_type(data_bus_walk_owns ? 3'b010 : cpu_load_type),
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
        .timer_interrupt(timer_interrupt)
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
        .source_irq(uart_interrupt),
        .external_interrupt(plic_interrupt)
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
