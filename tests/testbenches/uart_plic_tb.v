`default_nettype none

module uart_plic_tb (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] addr,
    input  wire [31:0] write_data,
    input  wire        write_enable,
    input  wire        read_enable,
    input  wire        rx,
    output wire [31:0] read_data,
    output wire        tx,
    output wire        external_interrupt
);
    wire [31:0] uart_read_data;
    wire [31:0] plic_read_data;
    wire uart_valid;
    wire plic_valid;
    wire uart_interrupt;

    assign read_data = uart_valid ? uart_read_data :
                       plic_valid ? plic_read_data : 32'h0;

    uart uart_inst (
        .clk(clk),
        .rst(rst),
        .addr(addr),
        .write_data(write_data),
        .write_enable(write_enable),
        .read_enable(read_enable),
        .read_data(uart_read_data),
        .uart_valid(uart_valid),
        .interrupt(uart_interrupt),
        .tx(tx),
        .rx(rx)
    );

    plic plic_inst (
        .clk(clk),
        .rst(rst),
        .addr(addr),
        .write_data(write_data),
        .write_enable(write_enable),
        .read_enable(read_enable),
        .read_data(plic_read_data),
        .plic_valid(plic_valid),
        .source_irq(uart_interrupt),
        .external_interrupt(external_interrupt)
    );
endmodule

