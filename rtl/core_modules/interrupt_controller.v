`default_nettype none
module interrupt_controller (
    input wire clk,
    input wire rst,
    
    // External interrupt inputs
    input wire timer_interrupt,
    input wire software_interrupt,
    input wire external_interrupt,
    
    // CPU interface
    input wire [31:0] mstatus,
    input wire [31:0] mie,
    input wire [31:0] mip,
    input wire [31:0] mideleg,
    input wire [1:0] privilege_mode,
    output reg interrupt_pending,
    output reg [31:0] interrupt_cause,
    output reg interrupt_to_supervisor,
    
    // Control signals
    input wire interrupt_taken,
    input wire [31:0] current_pc,
    output reg [31:0] interrupt_pc
);

    // Interrupt cause codes (RISC-V standard)
    localparam MACHINE_SOFTWARE_INTERRUPT = 32'h80000003;
    localparam MACHINE_TIMER_INTERRUPT    = 32'h80000007;
    localparam MACHINE_EXTERNAL_INTERRUPT = 32'h8000000B;
    localparam SUPERVISOR_SOFTWARE_INTERRUPT = 32'h80000001;
    localparam SUPERVISOR_TIMER_INTERRUPT    = 32'h80000005;
    localparam SUPERVISOR_EXTERNAL_INTERRUPT = 32'h80000009;

    localparam PRIV_U = 2'b00;
    localparam PRIV_S = 2'b01;
    localparam PRIV_M = 2'b11;
    
    // Machine interrupt enable bits
    wire msie = mie[3];  // Machine software interrupt enable
    wire mtie = mie[7];  // Machine timer interrupt enable
    wire meie = mie[11]; // Machine external interrupt enable
    wire ssie = mie[1];  // Supervisor software interrupt enable
    wire stie = mie[5];  // Supervisor timer interrupt enable
    wire seie = mie[9];  // Supervisor external interrupt enable
    wire mie_global = mstatus[3]; // Global machine interrupt enable
    wire sie_global = mstatus[1]; // Global supervisor interrupt enable
    
    // Machine interrupt pending bits
    wire msip = mip[3];  // Machine software interrupt pending
    wire mtip = mip[7];  // Machine timer interrupt pending
    wire meip = mip[11]; // Machine external interrupt pending
    wire ssip = mip[1];  // Supervisor software interrupt pending
    wire stip = mip[5];  // Supervisor timer interrupt pending
    wire seip = mip[9];  // Supervisor external interrupt pending

    wire m_interrupts_enabled = (privilege_mode != PRIV_M) || mie_global;
    wire s_interrupts_enabled = (privilege_mode == PRIV_U) ||
                                ((privilege_mode == PRIV_S) && sie_global);
    
    always @(*) begin
        interrupt_pending = 1'b0;
        interrupt_cause = 32'b0;
        interrupt_to_supervisor = 1'b0;
        interrupt_pc = current_pc;

        // Interrupts targeting a higher-privilege mode win, and within a
        // mode the priority is External > Software > Timer
        // (privileged spec §3.1.14 / §4.1.3).
        if (m_interrupts_enabled) begin
            if (meip && meie) begin
                interrupt_pending = 1'b1;
                interrupt_cause = MACHINE_EXTERNAL_INTERRUPT;
            end else if (msip && msie) begin
                interrupt_pending = 1'b1;
                interrupt_cause = MACHINE_SOFTWARE_INTERRUPT;
            end else if (mtip && mtie) begin
                interrupt_pending = 1'b1;
                interrupt_cause = MACHINE_TIMER_INTERRUPT;
            end
        end

        if (!interrupt_pending && s_interrupts_enabled) begin
            if (seip && seie && mideleg[9]) begin
                interrupt_pending = 1'b1;
                interrupt_cause = SUPERVISOR_EXTERNAL_INTERRUPT;
                interrupt_to_supervisor = 1'b1;
            end else if (ssip && ssie && mideleg[1]) begin
                interrupt_pending = 1'b1;
                interrupt_cause = SUPERVISOR_SOFTWARE_INTERRUPT;
                interrupt_to_supervisor = 1'b1;
            end else if (stip && stie && mideleg[5]) begin
                interrupt_pending = 1'b1;
                interrupt_cause = SUPERVISOR_TIMER_INTERRUPT;
                interrupt_to_supervisor = 1'b1;
            end
        end
    end

endmodule
