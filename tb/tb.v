`timescale 1ns / 1ps

module testbench;

    // Declare testbench variables
    reg [31:0] instruction;        // Instruction to be tested
    reg [31:0] rs1, rs2;          // Operand registers
    wire [31:0] result;           // Result of operation
    wire [31:0] expected_result;  // Expected result for comparison
    reg clk, reset;               // Clock and Reset signals
    reg [1:0] test_case;          // Test case selector

    // Instantiate the ALU or the CPU module
    alu #(.WIDTH(32)) uut (
        .clk(clk),
        .reset(reset),
        .instruction(instruction),
        .rs1(rs1),
        .rs2(rs2),
        .result(result)
    );

    // Clock generation
    always begin
        #5 clk = ~clk;
    end

    // Test case generator
    always @(*) begin
        case (test_case)
            2'b00: begin
                // MUL (Multiply)
                instruction = 32'b0000001_000_001_010_0000000_0000001;  // Example encoding for MUL instruction
                rs1 = 32'd6;   // Operand 1
                rs2 = 32'd7;   // Operand 2
                expected_result = 32'd42;  // 6 * 7 = 42
            end
            2'b01: begin
                // DIV (Signed Division)
                instruction = 32'b0000001_000_001_010_0000000_0000100;  // Example encoding for DIV instruction
                rs1 = 32'd10;  // Operand 1
                rs2 = 32'd2;   // Operand 2
                expected_result = 32'd5;  // 10 / 2 = 5
            end
            2'b10: begin
                // DIVU (Unsigned Division)
                instruction = 32'b0000001_000_001_010_0000000_0000101;  // Example encoding for DIVU instruction
                rs1 = 32'd10;  // Operand 1
                rs2 = 32'd2;   // Operand 2
                expected_result = 32'd5;  // 10 / 2 = 5 (unsigned)
            end
            2'b11: begin
                // REM (Signed Remainder)
                instruction = 32'b0000001_000_001_010_0000000_0000110;  // Example encoding for REM instruction
                rs1 = 32'd10;  // Operand 1
                rs2 = 32'd3;   // Operand 2
                expected_result = 32'd1;  // 10 % 3 = 1
            end
            default: begin
                instruction = 32'd0;
                rs1 = 32'd0;
                rs2 = 32'd0;
                expected_result = 32'd0;
            end
        endcase
    end

    // Reset procedure
    initial begin
        clk = 0;
        reset = 1;
        #10 reset = 0;  // Reset for 10 ns

        // Test each case
        test_case = 2'b00;  // MUL
        #20;
        
        test_case = 2'b01;  // DIV
        #20;
        
        test_case = 2'b10;  // DIVU
        #20;
        
        test_case = 2'b11;  // REM
        #20;
        
        $finish;
    end

    // Check results and print them
    always @(posedge clk) begin
        if (reset == 0) begin
            if (result == expected_result) begin
                $display("Test Case %b PASSED: Instruction %b, Result = %d", test_case, instruction, result);
            end else begin
                $display("Test Case %b FAILED: Instruction %b, Expected = %d, Got = %d", test_case, instruction, expected_result, result);
            end
        end
    end

endmodule
