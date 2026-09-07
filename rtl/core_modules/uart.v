`default_nettype none
`include "memory_map.vh"

// NS16550-compatible UART (TX only, reg_shift=2 — registers at 4-byte offsets).
// openSBI uart8250 driver sequence:
//   1. LCR = 0x83 (DLAB=1, 8N1)
//   2. DLL = divisor[7:0], DLH = divisor[15:8]
//   3. LCR = 0x03 (DLAB=0, 8N1)
//   4. FCR = 0x07 (enable+clear FIFOs)
//   5. Per byte: poll LSR[5] (THRE=1 = ready), write THR

module uart (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] addr,
    input  wire [31:0] write_data,
    input  wire        write_enable,
    input  wire        read_enable,
    output reg  [31:0] read_data,
    output wire        uart_valid,
    output wire        tx
);

wire [2:0] reg_sel = addr[4:2];
assign uart_valid = (addr >= `UART_BASE) && (addr <= (`UART_BASE + 7*4));

// Tracked registers
reg [7:0] lcr;   // Line Control (bit 7 = DLAB)
reg [7:0] ier;   // Interrupt Enable (stored, interrupts unused)
reg [7:0] scr;   // Scratch
reg [7:0] dll;   // Divisor Latch Low
reg [7:0] dlh;   // Divisor Latch High

wire dlab = lcr[7];

// TX state machine
reg [7:0]  tx_data;
reg        tx_busy;
reg        tx_start_pending;
reg [3:0]  tx_state;
reg [3:0]  tx_bit_count;
reg        tx_out;
reg [15:0] baud_counter;
reg [15:0] baud_div;

localparam TX_IDLE  = 4'd0;
localparam TX_START = 4'd1;
localparam TX_DATA  = 4'd2;
localparam TX_STOP  = 4'd3;

// Default baud divisor: 10 cycles/bit for fast simulation
localparam DEFAULT_BAUD_DIV = 16'd10;

assign tx = tx_out;

// LSR: bit5=THRE (TX holding register empty), bit6=TEMT (TX empty)
wire [7:0] lsr = {1'b0, !tx_busy, !tx_busy, 4'b0, 1'b0};
// IIR: no interrupt pending (bit0=1), FIFO enabled (bits7:6=11)
wire [7:0] iir = 8'hC1;

// -------------------------------------------------------------------------
// Register writes + TX state machine (single always block, no multi-driver)
// -------------------------------------------------------------------------
initial begin
    lcr              = 8'h00;
    ier              = 8'h00;
    scr              = 8'h00;
    dll              = DEFAULT_BAUD_DIV[7:0];
    dlh              = DEFAULT_BAUD_DIV[15:8];
    tx_data          = 8'h00;
    tx_busy          = 1'b0;
    tx_start_pending = 1'b0;
    tx_state         = TX_IDLE;
    tx_bit_count     = 4'b0;
    tx_out           = 1'b1;
    baud_div         = DEFAULT_BAUD_DIV;
    baud_counter     = 16'd1;
end

always @(posedge clk or posedge rst) begin
    if (rst) begin
        lcr              <= 8'h00;
        ier              <= 8'h00;
        scr              <= 8'h00;
        dll              <= DEFAULT_BAUD_DIV[7:0];
        dlh              <= DEFAULT_BAUD_DIV[15:8];
        tx_data          <= 8'h00;
        tx_busy          <= 1'b0;
        tx_start_pending <= 1'b0;
        tx_state         <= TX_IDLE;
        tx_bit_count     <= 4'b0;
        tx_out           <= 1'b1;
        baud_div         <= DEFAULT_BAUD_DIV;
        baud_counter     <= 16'd1;
    end else begin
        // ---- baud counter + TX state machine (runs first) ----
        if (baud_counter > 0) begin
            baud_counter <= baud_counter - 1'b1;
        end else begin
            baud_counter <= baud_div;
            case (tx_state)
                TX_IDLE: begin
                    if (tx_start_pending) begin
                        tx_state         <= TX_START;
                        tx_out           <= 1'b0;   // start bit
                        tx_bit_count     <= 4'b0;
                        tx_start_pending <= 1'b0;
                    end else begin
                        tx_out <= 1'b1;
                        // do NOT touch tx_busy here — only TX_STOP clears it
                    end
                end
                TX_START: begin
                    tx_state     <= TX_DATA;
                    tx_out       <= tx_data[0];
                    tx_bit_count <= 4'd1;
                end
                TX_DATA: begin
                    if (tx_bit_count < 8) begin
                        tx_out       <= tx_data[tx_bit_count[2:0]];
                        tx_bit_count <= tx_bit_count + 1'b1;
                    end else begin
                        tx_state <= TX_STOP;
                        tx_out   <= 1'b1;   // stop bit
                    end
                end
                TX_STOP: begin
                    tx_state <= TX_IDLE;
                    tx_busy  <= 1'b0;
                end
                default: tx_state <= TX_IDLE;
            endcase
        end

        // ---- register writes (after state machine so writes take priority) ----
        if (write_enable && uart_valid) begin
            case (reg_sel)
                3'd0: begin
                    if (dlab)
                        dll <= write_data[7:0];
                    else if (!tx_busy) begin
                        tx_data          <= write_data[7:0];
                        tx_start_pending <= 1'b1;
                        tx_busy          <= 1'b1;
                    end
                end
                3'd1: begin
                    if (dlab) dlh <= write_data[7:0];
                    else      ier <= write_data[7:0];
                end
                3'd3: begin
                    if (lcr[7] && !write_data[7])
                        baud_div <= {dlh, dll};
                    lcr <= write_data[7:0];
                end
                3'd7: scr <= write_data[7:0];
                default: ; // FCR, MCR writes accepted and ignored
            endcase
        end
    end
end

// ---- register reads -------------------------------------------------------
always @(*) begin
    read_data = 32'h0;
    if (read_enable && uart_valid) begin
        case (reg_sel)
            3'd0: read_data = dlab ? {24'h0, dll} : 32'h0; // THR/RBR/DLL (no RX)
            3'd1: read_data = dlab ? {24'h0, dlh} : {24'h0, ier};
            3'd2: read_data = {24'h0, iir};
            3'd3: read_data = {24'h0, lcr};
            3'd4: read_data = 32'h0;             // MCR
            3'd5: read_data = {24'h0, lsr};      // LSR — the key one
            3'd6: read_data = 32'h0;             // MSR (no modem)
            3'd7: read_data = {24'h0, scr};      // SCR
        endcase
    end
end

endmodule
