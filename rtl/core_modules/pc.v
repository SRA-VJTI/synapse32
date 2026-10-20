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

    always @ (posedge clk) begin
        if(rst)
            next_pc <= `INSTR_MEM_BASE;
        else if(j_signal) begin
            next_pc <= jump;
        end
        else if(stall) begin
            // If stalling, don't update PC
            next_pc <= next_pc;
        end
        else begin
            next_pc <= next_pc + 32'h4;
        end
    end

    assign out = next_pc;
    assign next_out = rst ? `INSTR_MEM_BASE :
                      j_signal ? jump :
                      stall ? next_pc : next_pc + 32'h4;
endmodule
