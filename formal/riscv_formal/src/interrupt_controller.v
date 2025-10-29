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
    output reg interrupt_pending,
    output reg [31:0] interrupt_cause,
    
    // Control signals
    input wire interrupt_taken,
    input wire [31:0] current_pc,
    output reg [31:0] interrupt_pc
);

    // Interrupt cause codes (RISC-V standard)
    localparam MACHINE_SOFTWARE_INTERRUPT = 32'h80000003;
    localparam MACHINE_TIMER_INTERRUPT    = 32'h80000007;
    localparam MACHINE_EXTERNAL_INTERRUPT = 32'h8000000B;
    
    // Machine interrupt enable bits
    wire msie = mie[3];  // Machine software interrupt enable
    wire mtie = mie[7];  // Machine timer interrupt enable
    wire meie = mie[11]; // Machine external interrupt enable
    wire mie_global = mstatus[3]; // Global machine interrupt enable
    
    // Machine interrupt pending bits
    wire msip = mip[3];  // Machine software interrupt pending
    wire mtip = mip[7];  // Machine timer interrupt pending
    wire meip = mip[11]; // Machine external interrupt pending
    
    always @(*) begin
        interrupt_pending = 1'b0;
        interrupt_cause = 32'b0;
        interrupt_pc = current_pc;
        
        if (mie_global) begin
            // Priority: External > Timer > Software
            if (meip && meie) begin
                interrupt_pending = 1'b1;
                interrupt_cause = MACHINE_EXTERNAL_INTERRUPT;
            end else if (mtip && mtie) begin
                interrupt_pending = 1'b1;
                interrupt_cause = MACHINE_TIMER_INTERRUPT;
            end else if (msip && msie) begin
                interrupt_pending = 1'b1;
                interrupt_cause = MACHINE_SOFTWARE_INTERRUPT;
            end
        end
    end

endmodule