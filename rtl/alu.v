`default_nettype none
module alu (
    input wire [31:0] rs1,
    input wire [31:0] rs2,
    input wire [31:0] imm,
    input wire [31:0] instructions,
    input wire [31:0] pc_input,
    output reg [31:0] ALUoutput
);

    always @(*) begin
        case (instructions)
            32'h1: ALUoutput = rs1 + rs2;   // Addition
            32'h2: ALUoutput = rs1 - rs2;   // Subtraction
            32'h3: ALUoutput = rs1 ^ rs2;   // Bitwise XOR
            32'h4: ALUoutput = rs1 | rs2;   // Bitwise OR
            32'h5: ALUoutput = rs1 & rs2;   // Bitwise AND
            32'h6: ALUoutput = rs1 << rs2[4:0];  // Logical left shift
            32'h7: ALUoutput = rs1 >> rs2[4:0];  // Logical right shift
            32'h8: ALUoutput = $signed(rs1) >>> rs2[4:0];  // Arithmetic right shift
            32'h9: ALUoutput = {32{$signed(rs1) < $signed(rs2)}};  // Set less than (signed comparison)
            32'hA: ALUoutput = {32{rs1 < rs2}};  // Set less than (unsigned comparison)
            32'hB: ALUoutput = (rs1 + imm);  // Add immediate
            32'hC: ALUoutput = (rs1 ^ imm);  // Bitwise XOR with immediate
            32'hD: ALUoutput = (rs1 | imm);  // Bitwise OR with immediate
            32'hE: ALUoutput = (rs1 & imm);  // Bitwise AND with immediate
            32'hF: ALUoutput = (rs1 << imm[4:0]);  // Logical left shift with immediate
            32'h10: ALUoutput = (rs1 >> imm[4:0]);  // Logical right shift with immediate
            32'h11: ALUoutput = ($signed(rs1) >>> imm[4:0]);  // Arithmetic right shift with immediate
            32'h12: ALUoutput = {32{$signed(rs1) < $signed(imm)}};  // Set less than immediate (signed comparison)
            32'h13: ALUoutput = {32{rs1 < imm}};  // Set less than immediate (unsigned comparison)
            32'h14: ALUoutput = imm << 12;  // Load upper immediate
            32'h15: ALUoutput = pc_input + (imm << 12);  // Add upper immediate to PC
            default: ALUoutput = 0;  // Default case: output zero
        endcase
        // $monitor("MONITOR rs2[4:0]: %b, rs1: %b, ALUout: %b", rs2[4:0], rs1, ALUoutput);
    end
endmodule
