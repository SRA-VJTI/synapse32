`timescale 1ns/1ps

// Execute real instructions through the CPU and Sv32 permission checker.
// Seed architectural state only; do not force pipeline control or fault signals.
module page_fault_priority_tb;
    integer case_id = 0;
    reg clk = 0;
    reg rst = 1;
    always #5 clk = ~clk;

    wire amo_case = (case_id == 1 || case_id == 4);
    wire machine_case = (case_id == 3);
    wire [31:0] pc, read_addr, write_addr, write_data;
    wire read_enable, write_enable, mmu_enable, load_fault, store_fault;
    wire [1:0] privilege;
    reg [31:0] instruction;
    always @* begin
        instruction = 32'h00000013;
        case (pc)
            32'h80000000: instruction = amo_case ? 32'h0020a2af : 32'h00002283;
            32'h80000004: begin
                case (case_id)
                    0: instruction = 32'h10200073; // sret
                    2: instruction = 32'h10500073; // wfi
                    3: instruction = 32'h30200073; // mret
                    default: instruction = 32'h00000013;
                endcase
            end
            32'h80000100: instruction = 32'h00700313; // handler: addi x6,x0,7
        endcase
    end

    riscv_cpu cpu (
        .clk(clk), .rst(rst), .module_instr_in(instruction),
        .module_read_data_in(32'h12345678), .module_pc_out(pc),
        .module_wr_data_out(write_data), .module_mem_wr_en(write_enable),
        .module_mem_rd_en(read_enable), .module_read_addr(read_addr),
        .module_write_addr(write_addr), .module_write_byte_enable(), .module_load_type(),
        .module_load_page_fault_in(load_fault), .module_store_page_fault_in(store_fault),
        .module_page_fault_addr_in(read_addr), .module_instr_page_fault_in(1'b0),
        .module_data_mmu_enable_out(mmu_enable), .module_data_privilege_out(privilege),
        .module_satp_out(), .module_data_sum_out(), .module_data_mxr_out(),
        .module_instr_mmu_enable_out(), .module_instr_privilege_out(),
        .timer_interrupt(1'b0), .software_interrupt(1'b0), .external_interrupt(1'b0)
    );
    sv32_data_check permissions (
        .translate_enable(mmu_enable), .addr_valid_in(case_id == 1),
        .privilege_mode(privilege), .sum(1'b0), .mxr(1'b0),
        .data_rd_en(read_enable), .data_wr_req(write_enable),
        .leaf_pte(32'h00000053), // valid, readable user page; no write permission
        .load_page_fault(load_fault), .store_page_fault(store_fault),
        .update_accessed(), .update_dirty()
    );

    initial begin
        if ($value$plusargs("CASE_ID=%d", case_id)) begin end
        repeat (3) @(negedge clk);
        rst = 0;
        cpu.csr_file_inst.privilege_mode = machine_case ? 2'b11 : amo_case ? 2'b00 : 2'b01;
        // M-mode case uses MPRV with MPP=S so its load still translates.
        cpu.csr_file_inst.mstatus = machine_case ? 32'h00020800 : 0;
        cpu.csr_file_inst.satp = 32'h80080000;
        cpu.csr_file_inst.medeleg = machine_case ? 0 : 32'h0000a000;
        cpu.csr_file_inst.stvec = 32'h80000100;
        cpu.csr_file_inst.mtvec = 32'h80000100;
        cpu.csr_file_inst.sepc = 32'h80000200;
        cpu.csr_file_inst.mepc = 32'h80000200;
        cpu.csr_file_inst.scause = 32'hdeadbeef;
        cpu.csr_file_inst.mcause = 32'hdeadbeef;
        cpu.csr_file_inst.stval = 32'h12345678;
        cpu.csr_file_inst.mtval = 32'h12345678;
        cpu.rf_inst0.register_file[1] = 32'h00400000;
        cpu.rf_inst0.register_file[2] = 3;
        cpu.rf_inst0.register_file[6] = 0;
        repeat (20) begin
            @(negedge clk);
            if (cpu.mem_stage_page_fault_taken) begin
                if (amo_case && (load_fault || !store_fault))
                    $fatal(1, "AMO must raise only a store/AMO page fault");
                @(posedge clk); #1;
                if (pc != 32'h80000100)
                    $fatal(1, "Wrong trap target: %h", pc);
                if (cpu.csr_file_inst.privilege_mode != (machine_case ? 2'b11 : 2'b01))
                    $fatal(1, "Younger return changed trap privilege");
                if (machine_case) begin
                    if (cpu.csr_file_inst.mepc != 32'h80000000 ||
                        cpu.csr_file_inst.mcause != 13 || cpu.csr_file_inst.mtval != 0)
                        $fatal(1, "Machine trap state was not recorded");
                end else begin
                    if (cpu.csr_file_inst.sepc != 32'h80000000 ||
                        cpu.csr_file_inst.scause != (amo_case ? 15 : 13) ||
                        cpu.csr_file_inst.stval != (amo_case ? 32'h00400000 : 0))
                        $fatal(1, "Supervisor trap state was not recorded correctly");
                end
                if (cpu.wfi_active)
                    $fatal(1, "Squashed WFI put the fault handler to sleep");
                repeat (10) @(negedge clk);
                if (cpu.rf_inst0.register_file[6] != 7)
                    $fatal(1, "Trap handler did not execute");
                $display("PASS page-fault priority case %0d", case_id);
                $finish;
            end
        end
        $fatal(1, "No page fault observed");
    end
endmodule
