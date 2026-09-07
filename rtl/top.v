`default_nettype none
`include "memory_map.vh"

module top (
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
    
    // Timer module wires
    wire [31:0] timer_read_data;
    wire timer_valid;
    wire timer_interrupt;
    wire external_interrupt_combined;
    
    // UART module wires
    wire [31:0] uart_read_data;
    wire uart_valid;
    wire uart_access;
    
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
    wire mmu_instr_pte_update_req;
    wire [31:0] mmu_instr_pte_update_addr;
    wire [31:0] mmu_instr_pte_update_value;
    wire mmu_data_pte_update_req;
    wire [31:0] mmu_data_pte_update_addr;
    wire [31:0] mmu_data_pte_update_value;

    // The current platform exposes the external interrupt input directly.
    // Keep this top-level path independent of an optional PLIC implementation.
    assign external_interrupt_combined = external_interrupt;

    // Use memory map macros for clean address decoding
    assign translated_data_access = cpu_data_mmu_enable && (cpu_mem_write_en || cpu_mem_read_en);
    assign cpu_page_fault_addr = mmu_data_fault_addr;
    assign data_mem_access = !translated_data_access && `IS_DATA_MEM(data_mem_addr);
    assign timer_access    = `IS_TIMER_MEM(phys_data_addr);
    assign uart_access     = `IS_UART_MEM(phys_data_addr);
    assign instr_mem_access = !translated_data_access && `IS_INSTR_MEM(data_mem_addr);
    // RAM covers translated accesses that aren't peripheral, plus direct RAM accesses.
    assign ram_access = (translated_data_access && !timer_access && !uart_access)
                        || data_mem_access || instr_mem_access;
    
    // Select the appropriate address for memory access
    assign data_mem_addr = cpu_mem_write_en ? cpu_mem_write_addr : cpu_mem_read_addr;
    
    // Multiplex read data based on address
    assign mem_read_data = timer_access ? timer_read_data :
                          uart_access ? uart_read_data :
                          ram_access ? instr_read_data : 32'h00000000;
    
    // Debug outputs
    assign pc_debug = cpu_pc_out;
    assign instr_debug = instr_to_cpu;
    
    // Instantiate the RISC-V CPU core
    riscv_cpu cpu_inst (
        .clk(clk),
        .rst(rst),
        .timer_interrupt(timer_interrupt),
        .software_interrupt(software_interrupt),
        .external_interrupt(external_interrupt_combined),
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
        .module_load_page_fault_in(cpu_load_page_fault),
        .module_store_page_fault_in(cpu_store_page_fault),
        .module_page_fault_addr_in(cpu_page_fault_addr),
        .module_instr_page_fault_in(cpu_instr_page_fault),
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
        .instr_translate_enable(cpu_instr_mmu_enable),
        .instr_virtual_addr(cpu_pc_out),
        .instr_priv_mode(cpu_instr_privilege),
        .data_translate_enable(translated_data_access),
        .data_virtual_addr(data_mem_addr),
        .data_wr_req(cpu_mem_write_en),
        .data_rd_en(cpu_mem_read_en),
        .data_priv_mode(cpu_data_privilege),
        .satp(cpu_satp),
        .data_sum(cpu_data_sum),
        .data_mxr(cpu_data_mxr),
        .instr_l1_pte_value(mmu_instr_l1_pte_value),
        .instr_l1_pte_backed(mmu_instr_l1_pte_backed),
        .instr_l0_pte_value(mmu_instr_l0_pte_value),
        .instr_l0_pte_backed(mmu_instr_l0_pte_backed),
        .data_l1_pte_value(mmu_data_l1_pte_value),
        .data_l1_pte_backed(mmu_data_l1_pte_backed),
        .data_l0_pte_value(mmu_data_l0_pte_value),
        .data_l0_pte_backed(mmu_data_l0_pte_backed),
        .instr_l1_pte_addr(mmu_instr_l1_pte_addr),
        .instr_l0_pte_addr(mmu_instr_l0_pte_addr),
        .data_l1_pte_addr(mmu_data_l1_pte_addr),
        .data_l0_pte_addr(mmu_data_l0_pte_addr),
        .instr_phys_addr(phys_instr_addr),
        .instr_page_fault(cpu_instr_page_fault),
        .data_phys_addr(phys_data_addr),
        .data_load_page_fault(cpu_load_page_fault),
        .data_store_page_fault(cpu_store_page_fault),
        .data_fault_addr(mmu_data_fault_addr),
        .instr_pte_update_req(mmu_instr_pte_update_req),
        .instr_pte_update_addr(mmu_instr_pte_update_addr),
        .instr_pte_update_value(mmu_instr_pte_update_value),
        .data_pte_update_req(mmu_data_pte_update_req),
        .data_pte_update_addr(mmu_data_pte_update_addr),
        .data_pte_update_value(mmu_data_pte_update_value)
    );

    // Instantiate unified memory
    unified_mem #(
        .DATA_WIDTH(32),
        .ADDR_WIDTH(32),
        .MEM_SIZE(17039360)  // (64MB + 1MB) / 4 words
    ) unified_mem_inst (
        .clk(clk),
        .instr_addr(phys_instr_addr),
        .instr_addr_p2(phys_data_addr),
        .data_wr_req(cpu_mem_write_en && ram_access),
        .data_rd_en(cpu_mem_read_en && ram_access),
        .wr_en(cpu_mem_write_en && ram_access && !cpu_store_page_fault),
        .write_byte_enable(cpu_write_byte_enable),
        .wr_data(cpu_mem_write_data),
        .load_type(cpu_load_type),
        .pte_wr_en_a(mmu_instr_pte_update_req),
        .pte_wr_addr_a(mmu_instr_pte_update_addr),
        .pte_wr_value_a(mmu_instr_pte_update_value),
        .pte_wr_en_b(mmu_data_pte_update_req),
        .pte_wr_addr_b(mmu_data_pte_update_addr),
        .pte_wr_value_b(mmu_data_pte_update_value),
        .pte_rd_addr_a(mmu_instr_l1_pte_addr),
        .pte_rd_addr_b(mmu_instr_l0_pte_addr),
        .pte_rd_addr_c(mmu_data_l1_pte_addr),
        .pte_rd_addr_d(mmu_data_l0_pte_addr),
        .instr(instr_to_cpu),
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
        .addr(phys_data_addr),
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
        .addr(phys_data_addr),
        .write_data(cpu_mem_write_data),
        .write_enable(cpu_mem_write_en && uart_access),
        .read_enable(cpu_mem_read_en && uart_access),
        .read_data(uart_read_data),
        .uart_valid(uart_valid),
        .tx(uart_tx)
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
