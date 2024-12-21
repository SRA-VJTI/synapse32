/**
 * @file alu.v
 *
 * This module implements simple arithmetic operations based on control unit inputs.
 * 
 * @input in1           Inputs the first source value (unsigned only).
 * @input in2           Inputs the second source value (unsigned only).
 * @input instructions  Inputs the selection line for which operation to perform.
 *
 * @output ALUoutput    Outputs the calculated value.
 * 
 */

module alu(
    input       [31:0]  in1,
    input       [31:0]  in2,
    input       [12:0]  instructions,
    output reg  [63:0]  ALUoutput
);

initial begin
    ALUoutput <= 0;
end

always @(*) begin
    case (instructions) 
        16'd1     :   ALUoutput <= in1 + in2;                     // add                            
        16'd2     :   ALUoutput <= in1 - in2;                     // sub
        16'd4     :   ALUoutput <= in1 ^ in2;                     // xor
        16'd8     :   ALUoutput <= in1 | in2;                     // or
        16'd16    :   ALUoutput <= in1 & in2;                     // and
        16'd32    :   ALUoutput <= in1 << in2[4:0];               // sll
        16'd64    :   ALUoutput <= in1 >> in2[4:0];               // srl
        16'd128   :   ALUoutput <= in1 >>> in2[4:0];              // sra
        16'd256   :   ALUoutput <= (in1 < in2);                   // slt
        16'd512   :   ALUoutput <= (in1 < in2);                   // sltu
        16'd1024  :   ALUoutput <= in1 * in2;                     // mul
        16'd2048  :   ALUoutput <= in1 / in2;                     // div
        16'd4096  :   ALUoutput <= in1 % in2;                     // rem 
        default   :   ALUoutput <= 0;
    endcase  
end

endmodule
