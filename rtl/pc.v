/**
 * @module PC
 * @brief Program Counter module.
 * 
 * This module implements the program counter (PC) for a CPU, updating the PC value
 * based on clock cycles, reset signal, and jump signal.
 * 
 * @input clk      Clock input signal.
 * @input reset    Reset signal to initialize the program counter.
 * @input j_signal Jump signal indicating a branch or jump instruction.
 * @input jump     32-bit jump address to be loaded into the program counter on a jump.
 * 
 * @return out_sign Current value of the program counter.
 */





module PC(
    input           clk,
    input           reset,
    input           j_signal,
    input   [31:0]  jump,
    output  [31:0]  out_sign     
);
    reg [31:0] next_pc = 32'd0;

    always @ (posedge clk) begin
        if      (reset)     next_pc <= 32'b0;
        else if (j_signal)  next_pc <= jump;
        else                next_pc <= next_pc + 32'h4;
    end
    
    assign out_sign = next_pc;
endmodule
