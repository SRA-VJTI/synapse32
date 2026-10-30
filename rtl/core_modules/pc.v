`include "memory_map.vh"
module pc(
   input clk,
   input rst,
   input j_signal,
   input stall,         // Added stall input
   input [31:0] jump,
   output[31:0] out,
   output[31:0] next_out  // Value loaded at the next edge
);
   reg [31:0] next_pc = `INSTR_MEM_BASE;

    // Single source for the register and next_out; the icache pre-reads its arrays with next_out.
    wire [31:0] next_pc_d = rst ? `INSTR_MEM_BASE :
                            j_signal ? jump :
                            stall ? next_pc : next_pc + 32'h4;

    always @ (posedge clk) begin
        next_pc <= next_pc_d;
    end

    assign out = next_pc;
    assign next_out = next_pc_d;
endmodule
