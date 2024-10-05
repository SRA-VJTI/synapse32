`timescale 1 ns/1 ns

module tb;

reg clk, reset;
wire [7:0] led;

top uut (clk, reset//, //led[0], led[1], led[2], led[3], led[4], led[5], led[6], led[7] 
);

initial begin
    $dumpfile("tb.vcd");
    $dumpvars(0, tb);
    clk <= 0;
    reset <= 0;
end

always begin
    #5 clk = ~clk;
    if (reset == 0) begin
        $display(led);
    end else if (reset == 1) begin
        $finish;
    end
end

endmodule