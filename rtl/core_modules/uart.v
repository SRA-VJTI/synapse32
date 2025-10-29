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

    // Register set
    reg [7:0]  tx_shift_reg;
    reg [7:0]  tx_buffer_data;
    reg        tx_buffer_valid;
    reg [15:0] baud_divider;
    reg [15:0] baud_counter;
    reg [3:0]  tx_state;
    reg [3:0]  tx_bit_index;
    reg        tx_out;
    reg        tx_enable;

    // Status flags
    reg tx_busy;
    reg tx_fifo_full;
    reg tx_fifo_empty;

    // Constants
    localparam TX_IDLE  = 4'd0;
    localparam TX_START = 4'd1;
    localparam TX_DATA  = 4'd2;
    localparam TX_STOP  = 4'd3;

    localparam [15:0] DEFAULT_BAUD_DIV = 16'd434; // 115200 @ 50 MHz

    // Address decode
    assign uart_valid = (addr == `UART_DATA)    ||
                        (addr == `UART_STATUS) ||
                        (addr == `UART_CONTROL)||
                        (addr == `UART_BAUD);

    assign tx = tx_out;

    // Helpers
    function [15:0] baud_reload_value;
        input [15:0] div;
        begin
            baud_reload_value = (div == 16'd0) ? 16'd1 : div;
        end
    endfunction

    // Next-state signals
    reg [7:0]  tx_shift_reg_next;
    reg [7:0]  tx_buffer_data_next;
    reg        tx_buffer_valid_next;
    reg [15:0] baud_divider_next;
    reg [15:0] baud_counter_next;
    reg [3:0]  tx_state_next;
    reg [3:0]  tx_bit_index_next;
    reg        tx_out_next;
    reg        tx_enable_next;
    reg        tx_busy_next;
    reg        tx_fifo_full_next;
    reg        tx_fifo_empty_next;
    reg        start_immediate;
    reg [7:0]  start_data;

    // State machine and buffering control
    always @(*) begin
        // Default next-state values
        tx_shift_reg_next    = tx_shift_reg;
        tx_buffer_data_next  = tx_buffer_data;
        tx_buffer_valid_next = tx_buffer_valid;
        baud_divider_next    = baud_divider;
        baud_counter_next    = baud_counter;
        tx_state_next        = tx_state;
        tx_bit_index_next    = tx_bit_index;
        tx_out_next          = tx_out;
        tx_enable_next       = tx_enable;
        tx_busy_next         = tx_busy;
        tx_fifo_full_next    = tx_fifo_full;
        tx_fifo_empty_next   = tx_fifo_empty;

        start_immediate = 1'b0;
        start_data      = 8'h00;

        // Handle register writes
        if (write_enable && uart_valid) begin
            case (addr)
                `UART_CONTROL: begin
                    tx_enable_next = write_data[0];
                    if (!write_data[0]) begin
                        tx_state_next        = TX_IDLE;
                        tx_out_next          = 1'b1;
                        tx_bit_index_next    = 4'd0;
                        tx_buffer_valid_next = 1'b0;
                        baud_counter_next    = baud_reload_value(baud_divider_next);
                    end
                end

                `UART_BAUD: begin
                    baud_divider_next = write_data[15:0];
                    if (tx_state == TX_IDLE) begin
                        baud_counter_next = baud_reload_value(write_data[15:0]);
                    end
                end

                `UART_DATA: begin
                    if (tx_enable_next) begin
                        if (tx_state == TX_IDLE && !tx_buffer_valid) begin
                            start_immediate = 1'b1;
                            start_data      = write_data[7:0];
                        end else if (!tx_buffer_valid) begin
                            tx_buffer_data_next  = write_data[7:0];
                            tx_buffer_valid_next = 1'b1;
                        end
                        // If buffer already holds data, keep it and signal full; handled via status flags.
                    end
                end

                default: ;
            endcase
        end

        // UART transmitter state machine
        case (tx_state)
            TX_IDLE: begin
                tx_out_next       = 1'b1;
                tx_bit_index_next = 4'd0;
                if (!tx_enable_next) begin
                    baud_counter_next = baud_reload_value(baud_divider_next);
                end else if (start_immediate) begin
                    tx_shift_reg_next   = start_data;
                    tx_state_next       = TX_START;
                    tx_out_next         = 1'b0;
                    baud_counter_next   = baud_reload_value(baud_divider_next);
                end else if (tx_buffer_valid_next) begin
                    tx_shift_reg_next   = tx_buffer_data_next;
                    tx_buffer_valid_next= 1'b0;
                    tx_state_next       = TX_START;
                    tx_out_next         = 1'b0;
                    baud_counter_next   = baud_reload_value(baud_divider_next);
                end else begin
                    baud_counter_next = baud_reload_value(baud_divider_next);
                end
            end

            TX_START: begin
                tx_out_next = 1'b0;
                if (!tx_enable_next) begin
                    tx_state_next       = TX_IDLE;
                    tx_out_next         = 1'b1;
                    tx_bit_index_next   = 4'd0;
                    baud_counter_next   = baud_reload_value(baud_divider_next);
                end else if (baud_counter <= 16'd1) begin
                    tx_state_next       = TX_DATA;
                    tx_out_next         = tx_shift_reg[0];
                    tx_bit_index_next   = 4'd1;
                    baud_counter_next   = baud_reload_value(baud_divider_next);
                end else begin
                    baud_counter_next = baud_counter - 16'd1;
                end
            end

            TX_DATA: begin
                if (!tx_enable_next) begin
                    tx_state_next       = TX_IDLE;
                    tx_out_next         = 1'b1;
                    tx_bit_index_next   = 4'd0;
                    baud_counter_next   = baud_reload_value(baud_divider_next);
                end else if (baud_counter <= 16'd1) begin
                    if (tx_bit_index < 4'd8) begin
                        tx_out_next       = tx_shift_reg[tx_bit_index[2:0]];
                        tx_bit_index_next = tx_bit_index + 4'd1;
                        baud_counter_next = baud_reload_value(baud_divider_next);
                    end else begin
                        tx_state_next     = TX_STOP;
                        tx_out_next       = 1'b1;
                        tx_bit_index_next = 4'd0;
                        baud_counter_next = baud_reload_value(baud_divider_next);
                    end
                end else begin
                    baud_counter_next = baud_counter - 16'd1;
                end
            end

            TX_STOP: begin
                if (!tx_enable_next) begin
                    tx_state_next       = TX_IDLE;
                    tx_out_next         = 1'b1;
                    tx_bit_index_next   = 4'd0;
                    baud_counter_next   = baud_reload_value(baud_divider_next);
                end else if (baud_counter <= 16'd1) begin
                    if (tx_buffer_valid_next) begin
                        tx_shift_reg_next   = tx_buffer_data_next;
                        tx_buffer_valid_next= 1'b0;
                        tx_state_next       = TX_START;
                        tx_out_next         = 1'b0;
                        tx_bit_index_next   = 4'd0;
                        baud_counter_next   = baud_reload_value(baud_divider_next);
                    end else begin
                        tx_state_next       = TX_IDLE;
                        tx_out_next         = 1'b1;
                        tx_bit_index_next   = 4'd0;
                        baud_counter_next   = baud_reload_value(baud_divider_next);
                    end
                end else begin
                    baud_counter_next = baud_counter - 16'd1;
                end
            end

            default: begin
                tx_state_next       = TX_IDLE;
                tx_out_next         = 1'b1;
                tx_bit_index_next   = 4'd0;
                baud_counter_next   = baud_reload_value(baud_divider_next);
            end
        endcase

        tx_busy_next       = (tx_state_next != TX_IDLE);
        tx_fifo_empty_next = (tx_state_next == TX_IDLE) && !tx_buffer_valid_next;
        tx_fifo_full_next  = tx_buffer_valid_next;
    end

    // Sequential logic: configuration, buffering, and transmitter state machine
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx_shift_reg    <= 8'h00;
            tx_buffer_data  <= 8'h00;
            tx_buffer_valid <= 1'b0;
            baud_divider    <= DEFAULT_BAUD_DIV;
            baud_counter    <= 16'd1;
            tx_state        <= TX_IDLE;
            tx_bit_index    <= 4'd0;
            tx_out          <= 1'b1;
            tx_enable       <= 1'b1;
            tx_busy         <= 1'b0;
            tx_fifo_full    <= 1'b0;
            tx_fifo_empty   <= 1'b1;
        end else begin
            tx_shift_reg    <= tx_shift_reg_next;
            tx_buffer_data  <= tx_buffer_data_next;
            tx_buffer_valid <= tx_buffer_valid_next;
            baud_divider    <= baud_divider_next;
            baud_counter    <= baud_counter_next;
            tx_state        <= tx_state_next;
            tx_bit_index    <= tx_bit_index_next;
            tx_out          <= tx_out_next;
            tx_enable       <= tx_enable_next;
            tx_busy         <= tx_busy_next;
            tx_fifo_full    <= tx_fifo_full_next;
            tx_fifo_empty   <= tx_fifo_empty_next;
        end
    end

    // Read path
    always @(*) begin
        if (read_enable && uart_valid) begin
            case (addr)
                `UART_DATA:    read_data = {24'b0, tx_shift_reg};
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
