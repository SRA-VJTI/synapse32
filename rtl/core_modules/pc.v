module pc(
   input clk,
   input rst,
   input j_signal,
   input stall,         // Added stall input
   input [31:0] jump,
   output[31:0] out
);
   reg [31:0] next_pc = 32'd0;

    always @ (posedge clk) begin
        if(rst)
            next_pc <= 32'b0;
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
endmodule
