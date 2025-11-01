`default_nettype none
`include "memory_map.vh"

module uart (
    input  wire        clk,
    input  wire        rst,

    // Memory interface
    input  wire [31:0] addr,
    input  wire [31:0] write_data,
    input  wire        write_enable,
    input  wire        read_enable,
    output reg  [31:0] read_data,
    output wire        uart_valid,

    // UART output
    output wire        tx
);

    // Transmit state
    reg [9:0]  tx_shift_reg;   // {stop, data[7:0], start}
    reg [7:0]  tx_last_data;   // Readback register for UART_DATA
    reg [15:0] baud_divider;   // Configured baud divisor
    reg [15:0] baud_counter;   // Baud counter
    reg [3:0]  tx_bit_index;   // Counts transmitted bits (start + data + stop)
    reg        tx_busy;        // Indicates transmission in progress
    reg        tx_enable;      // Global transmitter enable
    reg        tx_fifo_full;   // Indicates write while busy
    reg        tx_fifo_empty;  // Indicates transmitter idle
    reg        tx_out;         // Serialized TX output

    localparam [15:0] DEFAULT_BAUD_DIV = 16'd434; // 115200 @ 50 MHz

    // Address decode
    assign uart_valid = (addr == `UART_DATA)    ||
                        (addr == `UART_STATUS) ||
                        (addr == `UART_CONTROL)||
                        (addr == `UART_BAUD);

    assign tx = tx_out;

    function [15:0] baud_reload_value;
        input [15:0] raw_value;
        begin
            baud_reload_value = (raw_value <= 16'd1) ? 16'd1 : raw_value;
        end
    endfunction

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx_shift_reg  <= 10'h3FF;
            tx_last_data  <= 8'h00;
            baud_divider  <= DEFAULT_BAUD_DIV;
            baud_counter  <= DEFAULT_BAUD_DIV;
            tx_bit_index  <= 4'd0;
            tx_busy       <= 1'b0;
            tx_enable     <= 1'b1;
            tx_fifo_full  <= 1'b0;
            tx_fifo_empty <= 1'b1;
            tx_out        <= 1'b1; // idle high
        end else begin
            // Default idle status
            if (!tx_busy) begin
                tx_fifo_empty <= 1'b1;
                tx_fifo_full  <= 1'b0;
            end

            if (write_enable && uart_valid) begin
                case (addr)
                    `UART_CONTROL: begin
                        tx_enable <= write_data[0];
                        if (!write_data[0]) begin
                            tx_busy       <= 1'b0;
                            tx_fifo_empty <= 1'b1;
                            tx_fifo_full  <= 1'b0;
                            tx_out        <= 1'b1;
                        end
                    end

                    `UART_BAUD: begin
                        baud_divider <= baud_reload_value(write_data[15:0]);
                        if (!tx_busy) begin
                            baud_counter <= baud_reload_value(write_data[15:0]);
                        end
                    end

                    `UART_DATA: begin
                        if (tx_enable && !tx_busy) begin
                            tx_shift_reg  <= {1'b1, write_data[7:0], 1'b0};
                            tx_last_data  <= write_data[7:0];
                            tx_bit_index  <= 4'd0;
                            tx_busy       <= 1'b1;
                            tx_fifo_empty <= 1'b0;
                            tx_out        <= 1'b0; // start bit
                            baud_counter  <= baud_reload_value(baud_divider);
                        end else begin
                            tx_fifo_full <= 1'b1;
                        end
                    end

                    default: ;
                endcase
            end

            if (tx_enable && tx_busy) begin
                if (baud_counter == 16'd0) begin
                    if (tx_bit_index < 4'd9) begin
                        tx_out       <= tx_shift_reg[1];
                        tx_shift_reg <= {1'b1, tx_shift_reg[9:1]};
                        tx_bit_index <= tx_bit_index + 4'd1;
                        baud_counter <= baud_reload_value(baud_divider);
                    end else begin
                        tx_busy       <= 1'b0;
                        tx_out        <= 1'b1;
                        tx_fifo_empty <= 1'b1;
                        tx_fifo_full  <= 1'b0;
                    end
                end else begin
                    baud_counter <= baud_counter - 16'd1;
                end
            end
        end
    end

    always @(*) begin
        if (read_enable && uart_valid) begin
            case (addr)
                `UART_DATA:    read_data = {24'b0, tx_last_data};
                `UART_STATUS:  read_data = {29'b0, tx_busy, tx_fifo_empty, tx_fifo_full};
                `UART_CONTROL: read_data = {31'b0, tx_enable};
                `UART_BAUD:    read_data = {16'b0, baud_divider};
                default:       read_data = 32'h0;
            endcase
        end else begin
            read_data = 32'h0;
        end
    end

endmodule
