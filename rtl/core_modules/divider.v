`default_nettype none
// Restoring divider, one quotient bit per cycle on the operand magnitudes; the signs are applied to the result.
module divider (
    input wire clk,
    input wire rst,
    input wire req,          // EX holds a divide; when it drops, the division is abandoned
    input wire start,        // Operands are valid this cycle
    input wire ack,          // The result is taken this cycle
    input wire is_signed,
    input wire [31:0] dividend,
    input wire [31:0] divisor,
    output reg done,
    output wire [31:0] quotient,
    output wire [31:0] remainder
);

    reg busy_q;
    reg [4:0] step_q;
    reg [31:0] quotient_q;
    reg [31:0] remainder_q;
    reg [31:0] divisor_q;
    reg negate_quotient_q;
    reg negate_remainder_q;

    wire dividend_negative = is_signed && dividend[31];
    wire divisor_negative = is_signed && divisor[31];
    wire [32:0] shifted = {remainder_q, quotient_q[31]};
    wire [32:0] difference = shifted - {1'b0, divisor_q};

    assign quotient = negate_quotient_q ? -quotient_q : quotient_q;
    assign remainder = negate_remainder_q ? -remainder_q : remainder_q;

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            busy_q <= 1'b0;
            done <= 1'b0;
            step_q <= 5'd0;
            quotient_q <= 32'b0;
            remainder_q <= 32'b0;
            divisor_q <= 32'b0;
            negate_quotient_q <= 1'b0;
            negate_remainder_q <= 1'b0;
        end else if (!req) begin
            busy_q <= 1'b0;
            done <= 1'b0;
        end else if (done) begin
            if (ack) begin
                done <= 1'b0;
            end
        end else if (busy_q) begin
            remainder_q <= difference[32] ? shifted[31:0] : difference[31:0];
            quotient_q <= {quotient_q[30:0], !difference[32]};
            step_q <= step_q + 5'd1;
            if (step_q == 5'd31) begin
                busy_q <= 1'b0;
                done <= 1'b1;
            end
        end else if (start) begin
            busy_q <= 1'b1;
            step_q <= 5'd0;
            quotient_q <= dividend_negative ? -dividend : dividend;
            remainder_q <= 32'b0;
            divisor_q <= divisor_negative ? -divisor : divisor;
            // The M extension defines the quotient of a division by zero as all ones, whatever the signs.
            negate_quotient_q <= (dividend_negative != divisor_negative) && (divisor != 32'b0);
            negate_remainder_q <= dividend_negative;
        end
    end

endmodule
