`default_nettype none
module csr_file (
    input wire clk,
    input wire rst,
    input wire [11:0] csr_addr,
    input wire [31:0] write_data,
    input wire write_enable,
    input wire read_enable,
    output reg [31:0] read_data,
    output wire csr_valid,

    // Add interrupt handling ports
    input wire interrupt_pending,
    input wire [31:0] interrupt_cause_in,
    input wire [31:0] interrupt_pc_in,
    input wire [31:0] exception_pc_in,
    input wire interrupt_taken,
    input wire mret_instruction,
    input wire sret_instruction,
    input wire interrupt_to_supervisor,
    input wire trap_to_supervisor,
    input wire ecall_exception,
    input wire ebreak_exception,
    input wire illegal_instruction_exception,
    input wire instruction_address_misaligned_exception,
    input wire load_address_misaligned_exception,
    input wire store_address_misaligned_exception,
    input wire [31:0] exception_tval_in,
    
    // Timer interrupt input
    input wire timer_interrupt,
    input wire software_interrupt,
    input wire external_interrupt
);

    // Common CSR addresses
    localparam CSR_MSTATUS   = 12'h300;
    localparam CSR_MISA      = 12'h301;
    localparam CSR_MEDELEG   = 12'h302;
    localparam CSR_MIDELEG   = 12'h303;
    localparam CSR_MIE       = 12'h304;
    localparam CSR_MTVEC     = 12'h305;
    localparam CSR_MSCRATCH  = 12'h340;
    localparam CSR_MEPC      = 12'h341;
    localparam CSR_MCAUSE    = 12'h342;
    localparam CSR_MTVAL     = 12'h343;
    localparam CSR_MIP       = 12'h344;
    localparam CSR_SSTATUS   = 12'h100;
    localparam CSR_SIE       = 12'h104;
    localparam CSR_STVEC     = 12'h105;
    localparam CSR_SSCRATCH  = 12'h140;
    localparam CSR_SEPC      = 12'h141;
    localparam CSR_SCAUSE    = 12'h142;
    localparam CSR_STVAL     = 12'h143;
    localparam CSR_SIP       = 12'h144;
    localparam CSR_CYCLE     = 12'hC00;
    localparam CSR_CYCLEH    = 12'hC80;
    // Read-only machine info CSRs (addr[11:10]=2'b11 → any write is illegal)
    localparam CSR_MVENDORID = 12'hF11;
    localparam CSR_MARCHID   = 12'hF12;
    localparam CSR_MIMPID    = 12'hF13;
    localparam CSR_MHARTID   = 12'hF14;

    localparam PRIV_U = 2'b00;
    localparam PRIV_S = 2'b01;
    localparam PRIV_M = 2'b11;
    localparam SSTATUS_MASK = 32'h00000122;
    localparam S_INTERRUPT_MASK = 32'h00000222;

    // CSR registers
    reg [31:0] mstatus;
    reg [31:0] misa;
    reg [31:0] medeleg;
    reg [31:0] mideleg;
    reg [31:0] mie;
    reg [31:0] mtvec;
    reg [31:0] mscratch;
    reg [31:0] mepc;
    reg [31:0] mcause;
    reg [31:0] mtval;
    reg [31:0] mip;
    reg [63:0] cycle_counter;
    reg [1:0] privilege_mode;
    reg [31:0] stvec;
    reg [31:0] sscratch;
    reg [31:0] sepc;
    reg [31:0] scause;
    reg [31:0] stval;

    wire [31:0] sstatus = mstatus & SSTATUS_MASK;
    wire [31:0] sie = mie & S_INTERRUPT_MASK;
    wire [31:0] sip = mip & S_INTERRUPT_MASK;
    wire synchronous_exception = ecall_exception || ebreak_exception ||
                                 illegal_instruction_exception ||
                                 instruction_address_misaligned_exception ||
                                 load_address_misaligned_exception ||
                                 store_address_misaligned_exception;
    wire [31:0] exception_cause =
        instruction_address_misaligned_exception ? 32'h00000000 :
        illegal_instruction_exception             ? 32'h00000002 :
        ebreak_exception                          ? 32'h00000003 :
        load_address_misaligned_exception         ? 32'h00000004 :
        store_address_misaligned_exception        ? 32'h00000006 :
        (privilege_mode == PRIV_S)                ? 32'h00000009 :
                                                    32'h0000000B;
    wire [31:0] exception_tval = (ecall_exception || ebreak_exception) ?
                                 32'h00000000 : exception_tval_in;

    // Check if CSR address is valid
    assign csr_valid = (csr_addr == CSR_MSTATUS) || (csr_addr == CSR_MISA) ||
                       (csr_addr == CSR_MEDELEG) || (csr_addr == CSR_MIDELEG) ||
                       (csr_addr == CSR_MIE) || (csr_addr == CSR_MTVEC) ||
                       (csr_addr == CSR_MSCRATCH) || (csr_addr == CSR_MEPC) ||
                       (csr_addr == CSR_MCAUSE) || (csr_addr == CSR_MTVAL) ||
                       (csr_addr == CSR_SSTATUS) || (csr_addr == CSR_SIE) ||
                       (csr_addr == CSR_STVEC) ||
                       (csr_addr == CSR_SSCRATCH) || (csr_addr == CSR_SEPC) ||
                       (csr_addr == CSR_SCAUSE) || (csr_addr == CSR_STVAL) ||
                       (csr_addr == CSR_SIP) ||
                       (csr_addr == CSR_MIP) || (csr_addr == CSR_CYCLE) ||
                       (csr_addr == CSR_CYCLEH) ||
                       (csr_addr == CSR_MVENDORID) || (csr_addr == CSR_MARCHID) ||
                       (csr_addr == CSR_MIMPID) || (csr_addr == CSR_MHARTID);

    // Initialize CSRs
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            mstatus <= 32'h00001800;  // MPP=11 (machine mode)
            misa <= 32'h40000100;     // RV32I base
            medeleg <= 32'h0;
            mideleg <= 32'h0;
            mie <= 32'h0;
            mtvec <= 32'h0;
            mscratch <= 32'h0;
            mepc <= 32'h0;
            mcause <= 32'h0;
            mtval <= 32'h0;
            mip <= 32'h0;
            cycle_counter <= 64'h0;
            privilege_mode <= PRIV_M;
            stvec <= 32'h0;
            sscratch <= 32'h0;
            sepc <= 32'h0;
            scause <= 32'h0;
            stval <= 32'h0;
        end else begin
            cycle_counter <= cycle_counter + 1;
            
            // Update MIP based on interrupt inputs
            mip[3] <= software_interrupt;  // MSIP
            mip[7] <= timer_interrupt;     // MTIP
            mip[11] <= external_interrupt; // MEIP
            
            // Handle interrupt entry
            if (interrupt_taken) begin
                if (interrupt_to_supervisor) begin
                    sepc <= interrupt_pc_in;       // Save interrupted PC
                    scause <= interrupt_cause_in;  // Save interrupt cause
                    mstatus[5] <= mstatus[1];      // Save SIE to SPIE
                    mstatus[1] <= 1'b0;            // Disable supervisor interrupts
                    mstatus[8] <= (privilege_mode == PRIV_S);
                    privilege_mode <= PRIV_S;      // Trap to supervisor mode
                end else begin
                    mepc <= interrupt_pc_in;       // Save current PC
                    mcause <= interrupt_cause_in;  // Save interrupt cause
                    mstatus[7] <= mstatus[3];      // Save MIE to MPIE
                    mstatus[3] <= 1'b0;            // Disable interrupts
                    mstatus[12:11] <= privilege_mode; // Save previous privilege in MPP
                    privilege_mode <= PRIV_M;      // Trap to machine mode
                end
            end
            
            // Handle MRET
            else if (mret_instruction) begin
                mstatus[3] <= mstatus[7];        // Restore MIE from MPIE
                mstatus[7] <= 1'b1;              // Set MPIE to 1
                privilege_mode <= mstatus[12:11]; // Return to privilege encoded in MPP
                mstatus[12:11] <= PRIV_U;        // Clear MPP after return
            end

            // Handle SRET
            else if (sret_instruction) begin
                mstatus[1] <= mstatus[5];        // Restore SIE from SPIE
                mstatus[5] <= 1'b1;              // Set SPIE to 1
                privilege_mode <= mstatus[8] ? PRIV_S : PRIV_U;
                mstatus[8] <= 1'b0;              // Clear SPP after return
            end
            
            // Handle synchronous exceptions
            else if (synchronous_exception) begin
                if (trap_to_supervisor) begin
                    sepc <= exception_pc_in;        // Save exception PC
                    scause <= exception_cause;
                    stval <= exception_tval;
                    mstatus[5] <= mstatus[1];      // Save SIE to SPIE
                    mstatus[1] <= 1'b0;            // Disable supervisor interrupts
                    mstatus[8] <= (privilege_mode == PRIV_S);
                    privilege_mode <= PRIV_S;      // Trap to supervisor mode
                end else begin
                    mepc <= exception_pc_in;        // Save exception PC
                    mcause <= exception_cause;
                    mtval <= exception_tval;
                    mstatus[7] <= mstatus[3];      // Save MIE to MPIE
                    mstatus[3] <= 1'b0;            // Disable interrupts
                    mstatus[12:11] <= privilege_mode; // Save previous privilege in MPP
                    privilege_mode <= PRIV_M;      // Trap to machine mode
                end
            end
            
            // Normal CSR writes
            else if (write_enable && csr_valid) begin
                case (csr_addr)
                    CSR_MSTATUS:  mstatus <= write_data;
                    CSR_SSTATUS:  mstatus <= (mstatus & ~SSTATUS_MASK) | (write_data & SSTATUS_MASK);
                    CSR_MEDELEG:  medeleg <= write_data;
                    CSR_MIDELEG:  mideleg <= write_data;
                    CSR_MIE:      mie <= write_data;
                    CSR_SIE:      mie <= (mie & ~S_INTERRUPT_MASK) | (write_data & S_INTERRUPT_MASK);
                    CSR_MTVEC:    mtvec <= write_data;
                    CSR_MSCRATCH: mscratch <= write_data;
                    CSR_MEPC:     mepc <= write_data;
                    CSR_MCAUSE:   mcause <= write_data;
                    CSR_MTVAL:    mtval <= write_data;
                    CSR_STVEC:    stvec <= write_data;
                    CSR_SSCRATCH: sscratch <= write_data;
                    CSR_SEPC:     sepc <= write_data;
                    CSR_SCAUSE:   scause <= write_data;
                    CSR_STVAL:    stval <= write_data;
                    CSR_SIP:      mip <= (mip & ~S_INTERRUPT_MASK) | (write_data & S_INTERRUPT_MASK);
                    // MIP is updated by hardware, only software bits writable
                    CSR_MIP:      mip <= (mip & 32'h888) | (write_data & 32'h777);
                    default: ;
                endcase
            end
        end
    end

    // Read logic
    always @(*) begin
        if (read_enable && csr_valid) begin
            case (csr_addr)
                CSR_MSTATUS:  read_data = mstatus;
                CSR_SSTATUS:  read_data = sstatus;
                CSR_MISA:     read_data = misa;
                CSR_MEDELEG:  read_data = medeleg;
                CSR_MIDELEG:  read_data = mideleg;
                CSR_MIE:      read_data = mie;
                CSR_SIE:      read_data = sie;
                CSR_MTVEC:    read_data = mtvec;
                CSR_MSCRATCH: read_data = mscratch;
                CSR_MEPC:     read_data = mepc;
                CSR_MCAUSE:   read_data = mcause;
                CSR_MTVAL:    read_data = mtval;
                CSR_MIP:      read_data = mip;
                CSR_STVEC:    read_data = stvec;
                CSR_SSCRATCH: read_data = sscratch;
                CSR_SEPC:     read_data = sepc;
                CSR_SCAUSE:   read_data = scause;
                CSR_STVAL:    read_data = stval;
                CSR_SIP:      read_data = sip;
                CSR_CYCLE:    read_data = cycle_counter[31:0];
                CSR_CYCLEH:   read_data = cycle_counter[63:32];
                CSR_MVENDORID: read_data = 32'h0;
                CSR_MARCHID:   read_data = 32'h0;
                CSR_MIMPID:    read_data = 32'h0;
                CSR_MHARTID:   read_data = 32'h0;
                default:      read_data = 32'h0;
            endcase
        end else begin
            read_data = 32'h0;
        end
    end

endmodule
