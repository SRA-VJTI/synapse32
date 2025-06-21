`default_nettype none
`include "memory_map.vh"

module uart (
    input wire clk,
    input wire rst,
    
    // Memory interface
    input wire [31:0] addr,
    input wire [31:0] write_data,
    input wire write_enable,
    input wire read_enable,
    output reg [31:0] read_data,
    output wire uart_valid,
    
    // UART output
    output wire tx
);

    // Registers
    reg [7:0] tx_data;        // Data to transmit
    reg [15:0] baud_div;      // Baud rate divisor
    reg [15:0] baud_counter;  // Baud rate counter
    reg tx_busy;              // Transmission in progress
    reg tx_enable;            // Enable transmission
    reg tx_start_pending;     // Start transmission flag that persists
    reg baud_reload;          // Flag to reload baud counter
    
    // Status bits
    reg tx_fifo_full;
    reg tx_fifo_empty;

    // UART control state machine
    reg [3:0] tx_state;
    reg [3:0] tx_bit_count;
    reg tx_out;

    // Constants
    localparam TX_IDLE = 4'd0;
    localparam TX_START = 4'd1;
    localparam TX_DATA = 4'd2;
    localparam TX_STOP = 4'd3;
    
    // Address validation
    assign uart_valid = (addr == `UART_DATA) || 
                       (addr == `UART_STATUS) || 
                       (addr == `UART_CONTROL) ||
                       (addr == `UART_BAUD);
    
    // UART TX output
    assign tx = tx_out;
    
    // Default baud rate (115200 @ 50MHz clock)
    localparam DEFAULT_BAUD_DIVISOR = 16'd434; 
    
    // Initialize registers
    initial begin
        tx_data = 8'h00;
        baud_div = DEFAULT_BAUD_DIVISOR;
        tx_busy = 1'b0;
        tx_enable = 1'b1;
        tx_out = 1'b1;  // Idle state is high
        tx_state = TX_IDLE;
        tx_bit_count = 4'b0;
        tx_fifo_full = 1'b0;
        tx_fifo_empty = 1'b1;
        baud_counter = 16'b1;  // Start at 1 so first baud tick happens quickly
        tx_start_pending = 1'b0;
        baud_reload = 1'b0;
    end
    
    // Handle register writes (only updates registers, no counter manipulation)
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx_data <= 8'h00;
            baud_div <= DEFAULT_BAUD_DIVISOR;
            tx_enable <= 1'b1;
            tx_start_pending <= 1'b0;
            tx_busy <= 1'b0;
            baud_reload <= 1'b1;  // Force reload after reset
        end else begin
            // Clear baud_reload flag after one cycle
            baud_reload <= 1'b0;
            
            if (write_enable && uart_valid) begin
                case (addr)
                    `UART_DATA: begin
                        // Single-byte transmit buffer: if busy, set tx_fifo_full but do not buffer additional bytes.
                        if (!tx_busy && tx_enable) begin
                            tx_data <= write_data[7:0];
                            tx_start_pending <= 1'b1;  // Set pending flag
                            tx_busy <= 1'b1;           // Set busy immediately
                            tx_fifo_empty <= 1'b0;
                        end else begin
                            tx_fifo_full <= 1'b1;
                        end
                    end
                    `UART_CONTROL: begin
                        tx_enable <= write_data[0];
                    end
                    `UART_BAUD: begin
                        baud_div <= write_data[15:0];
                        baud_reload <= 1'b1;  // Signal to reload counter
                    end
                    default: ; // Do nothing
                endcase
            end
        end
    end
    
    // Handle register reads
    always @(*) begin
        if (read_enable && uart_valid) begin
            case (addr)
                `UART_DATA: read_data = {24'b0, tx_data};
                `UART_STATUS: read_data = {29'b0, tx_busy, tx_fifo_empty, tx_fifo_full};
                `UART_CONTROL: read_data = {31'b0, tx_enable};
                `UART_BAUD: read_data = {16'b0, baud_div};
                default: read_data = 32'h0;
            endcase
        end else begin
            read_data = 32'h0;
        end
    end
    
    // UART transmitter state machine and baud counter
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            tx_state <= TX_IDLE;
            tx_out <= 1'b1;
            tx_bit_count <= 4'b0;
            baud_counter <= 16'b1;  // Start at 1
            tx_fifo_empty <= 1'b1;
            tx_fifo_full <= 1'b0;
        end else begin
            // Handle baud counter reload
            if (baud_reload) begin
                baud_counter <= baud_div;
            end else begin
                // Normal baud rate counter logic
                if (baud_counter > 0) begin
                    baud_counter <= baud_counter - 1'b1;
                end else begin
                    // Baud tick occurred - reload counter and process state machine
                    baud_counter <= baud_div;
                    
                    case (tx_state)
                        TX_IDLE: begin
                            if (tx_enable && tx_start_pending) begin
                                tx_state <= TX_START;
                                tx_out <= 1'b0;  // Start bit
                                tx_bit_count <= 4'b0;
                                tx_start_pending <= 1'b0;  // Clear pending flag
                            end else begin
                                tx_out <= 1'b1;  // Idle state
                                // Only clear busy when truly idle (no pending transmission)
                                if (!tx_start_pending) begin
                                    tx_busy <= 1'b0;
                                    tx_fifo_empty <= 1'b1;
                                    tx_fifo_full <= 1'b0;
                                end
                            end
                        end
                        
                        TX_START: begin
                            tx_state <= TX_DATA;
                            tx_out <= tx_data[0];  // First data bit (LSB first)
                            tx_bit_count <= 4'b1;
                        end
                        
                        TX_DATA: begin
                            if (tx_bit_count < 8) begin
                                tx_out <= tx_data[tx_bit_count[2:0]];
                                tx_bit_count <= tx_bit_count + 1'b1;
                            end else begin
                                tx_state <= TX_STOP;
                                tx_out <= 1'b1;  // Stop bit
                            end
                        end
                        
                        TX_STOP: begin
                            tx_state <= TX_IDLE;
                            tx_busy <= 1'b0;
                            tx_fifo_empty <= 1'b1;
                            tx_fifo_full <= 1'b0;
                        end
                        
                        default: tx_state <= TX_IDLE;
                    endcase
                end
            end
        end
    end

endmodule