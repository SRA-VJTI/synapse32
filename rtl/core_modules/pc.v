`include "memory_map.vh"
module pc #(
   parameter [31:0] BOOT_ADDR = `INSTR_MEM_BASE
) (
   input clk,
   input rst,
   input j_signal,
   input stall,         // Added stall input
   input [31:0] jump,
   output[31:0] out,
   output[31:0] next_out  // Value loaded at the next edge
);
   reg [31:0] next_pc = BOOT_ADDR;

    // Single source for the register and next_out; the icache pre-reads its arrays with next_out.
    wire [31:0] next_pc_d = rst ? BOOT_ADDR :
                            j_signal ? jump :
                            stall ? next_pc : next_pc + 32'h4;

    always @ (posedge clk) begin
        next_pc <= next_pc_d;
    end

    assign out = next_pc;
    assign next_out = next_pc_d;
endmodule
