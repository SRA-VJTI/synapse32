`default_nettype none
`include "memory_map.vh"

// NS16550-compatible UART (TX+RX, reg_shift=2 — registers at 4-byte offsets).
// openSBI uart8250 driver sequence:
//   1. LCR = 0x83 (DLAB=1, 8N1)
//   2. DLL = divisor[7:0], DLH = divisor[15:8]
//   3. LCR = 0x03 (DLAB=0, 8N1)
//   4. FCR = 0x07 (enable+clear FIFOs)
//   5. Per byte: poll LSR[5] (THRE=1 = ready), write THR
//   RX: poll LSR[0] (DR=1 = data ready), read RBR

module uart (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] addr,
    input  wire [31:0] write_data,
    input  wire        write_enable,
    input  wire        read_enable,
    output reg  [31:0] read_data,
    output wire        uart_valid,
    output wire        interrupt,
    output wire        tx,
    input  wire        rx
);

wire [2:0] reg_sel = addr[4:2];
assign uart_valid = (addr >= `UART_BASE) && (addr <= (`UART_BASE + 7*4));

// Tracked registers
reg [7:0] lcr;   // Line Control (bit 7 = DLAB)
reg [7:0] ier;   // Interrupt Enable (stored, interrupts unused)
reg [7:0] fcr;   // FIFO Control (minimal TX FIFO support)
reg [7:0] scr;   // Scratch
reg [7:0] dll;   // Divisor Latch Low
reg [7:0] dlh;   // Divisor Latch High

wire dlab = lcr[7];
wire fifo_enabled = fcr[0];

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
localparam TX_FIFO_DEPTH = 16;

// Default baud divisor: 10 cycles/bit for fast simulation
localparam DEFAULT_BAUD_DIV = 16'd10;

assign tx = tx_out;

reg [7:0] tx_fifo [0:TX_FIFO_DEPTH-1];
reg [3:0] tx_fifo_head;
reg [3:0] tx_fifo_tail;
reg [4:0] tx_fifo_count;
wire tx_fifo_empty = (tx_fifo_count == 0);
wire tx_fifo_full = (tx_fifo_count == TX_FIFO_DEPTH);
wire tx_temt = !tx_busy && !tx_start_pending && tx_fifo_empty;
// In FIFO mode, LSR[5] reports the TX FIFO/holding register is empty.
wire tx_thre = fifo_enabled ? tx_fifo_empty : (!tx_busy && !tx_start_pending);
reg tx_fifo_pushed;
reg tx_fifo_popped;
reg tx_fifo_cleared;

// RX state machine
reg [2:0]  rx_state;
reg [7:0]  rx_shift;
reg [2:0]  rx_bit_count;
reg [15:0] rx_baud_counter;
reg        rx_prev;     // previous rx sample for edge detect
reg [7:0]  rbr;         // Receive Buffer Register
reg        rx_oe;       // LSR[1]: Overrun Error
reg [7:0]  rx_fifo [0:TX_FIFO_DEPTH-1];
reg [3:0]  rx_fifo_head;
reg [3:0]  rx_fifo_tail;
reg [4:0]  rx_fifo_count;
reg        rx_fifo_pushed;
reg        rx_fifo_popped;
reg        rx_fifo_cleared;
wire       rx_dr = (rx_fifo_count != 0); // LSR[0]: Data Ready
wire       rx_fifo_full = (rx_fifo_count == TX_FIFO_DEPTH);
wire [7:0] rx_fifo_data = rx_fifo[rx_fifo_head];
wire       rx_fifo_pop_request = read_enable && uart_valid &&
                                 (reg_sel == 3'd0) && !dlab && rx_dr;
wire       rx_fifo_clear_request = write_enable && uart_valid &&
                                   (reg_sel == 3'd2) && write_data[1];

localparam RX_IDLE  = 3'd0;
localparam RX_START = 3'd1;
localparam RX_DATA  = 3'd2;
localparam RX_STOP  = 3'd3;

// LSR: bit6=TEMT, bit5=THRE, bit1=OE, bit0=DR
wire [7:0] lsr = {1'b0, tx_temt, tx_thre, 3'b0, rx_oe, rx_dr};
wire rx_irq_pending = ier[0] && rx_dr;
// THRE interrupt: latched when THRE rises (transmitter drains) and cleared
// by reading IIR or writing THR, matching 16550 behavior so IRQ-driven TX
// (Linux 8250 driver) works without an interrupt storm from a pure level.
reg thre_irq;
reg tx_thre_prev;
wire thre_irq_set = tx_thre && !tx_thre_prev;
// An IIR read clears the THRE interrupt only when IIR actually reports THRE
// (RX data outranks it). If RX is pending, the THRE latch must survive so
// the interrupt re-asserts after the RX byte is drained — otherwise TX
// stalls waiting for an interrupt that was silently swallowed.
wire thre_irq_clear = (read_enable && uart_valid && (reg_sel == 3'd2) && !rx_irq_pending) ||
                      (write_enable && uart_valid && (reg_sel == 3'd0) && !dlab);
wire thre_irq_pending = ier[1] && thre_irq;
assign interrupt = rx_irq_pending || thre_irq_pending;
// IIR: bit0=0 when an interrupt is pending. Receiver-data-available
// (0b100 in bits[3:1]) outranks THRE (0b010), per 16550 priorities.
wire [7:0] iir = rx_irq_pending ? (fifo_enabled ? 8'hC4 : 8'h04) :
                 thre_irq_pending ? (fifo_enabled ? 8'hC2 : 8'h02) :
                                    (fifo_enabled ? 8'hC1 : 8'h01);

// -------------------------------------------------------------------------
// Register writes + TX/RX state machines (single always block)
// -------------------------------------------------------------------------
initial begin
    lcr              = 8'h00;
    ier              = 8'h00;
    fcr              = 8'h00;
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
    tx_fifo_head     = 4'd0;
    tx_fifo_tail     = 4'd0;
    tx_fifo_count    = 5'd0;
    rx_state         = RX_IDLE;
    rx_shift         = 8'h00;
    rx_bit_count     = 3'b0;
    rx_baud_counter  = 16'd0;
    rx_prev          = 1'b1;
    rbr              = 8'h00;
    rx_oe            = 1'b0;
    rx_fifo_head     = 4'd0;
    rx_fifo_tail     = 4'd0;
    rx_fifo_count    = 5'd0;
    thre_irq         = 1'b0;
    tx_thre_prev     = 1'b1;
end

always @(posedge clk or posedge rst) begin
    if (rst) begin
        lcr              <= 8'h00;
        ier              <= 8'h00;
        fcr              <= 8'h00;
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
        tx_fifo_head     <= 4'd0;
        tx_fifo_tail     <= 4'd0;
        tx_fifo_count    <= 5'd0;
        rx_state         <= RX_IDLE;
        rx_shift         <= 8'h00;
        rx_bit_count     <= 3'b0;
        rx_baud_counter  <= 16'd0;
        rx_prev          <= 1'b1;
        rbr              <= 8'h00;
        rx_oe            <= 1'b0;
        rx_fifo_head     <= 4'd0;
        rx_fifo_tail     <= 4'd0;
        rx_fifo_count    <= 5'd0;
        thre_irq         <= 1'b0;
        tx_thre_prev     <= 1'b1;
    end else begin
        tx_fifo_pushed = 1'b0;
        tx_fifo_popped = 1'b0;
        tx_fifo_cleared = 1'b0;
        rx_fifo_pushed = 1'b0;
        rx_fifo_popped = 1'b0;
        rx_fifo_cleared = 1'b0;

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
                    end else if (!tx_fifo_empty) begin
                        tx_data       <= tx_fifo[tx_fifo_head];
                        tx_fifo_head  <= tx_fifo_head + 1'b1;
                        tx_fifo_popped = 1'b1;
                        tx_state      <= TX_START;
                        tx_out        <= 1'b0;   // start bit
                        tx_bit_count  <= 4'b0;
                        tx_busy       <= 1'b1;
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
                    if (!tx_fifo_empty) begin
                        tx_data       <= tx_fifo[tx_fifo_head];
                        tx_fifo_head  <= tx_fifo_head + 1'b1;
                        tx_fifo_popped = 1'b1;
                        tx_state      <= TX_START;
                        tx_out        <= 1'b0;   // next start bit
                        tx_bit_count  <= 4'b0;
                    end else begin
                        tx_state <= TX_IDLE;
                        tx_busy  <= 1'b0;
                    end
                end
                default: tx_state <= TX_IDLE;
            endcase
        end

        // ---- register writes (after state machine so writes take priority) ----
        if (write_enable && uart_valid) begin
            case (reg_sel)
                3'd0: begin
                    if (dlab) begin
                        dll <= write_data[7:0];
                    end else if (fifo_enabled) begin
                        if (!tx_fifo_full) begin
                            tx_fifo[tx_fifo_tail] <= write_data[7:0];
                            tx_fifo_tail          <= tx_fifo_tail + 1'b1;
                            tx_fifo_pushed        = 1'b1;
                        end
                    end else if (!tx_busy && !tx_start_pending) begin
                        tx_data          <= write_data[7:0];
                        tx_start_pending <= 1'b1;
                        tx_busy          <= 1'b1;
                    end
                end
                3'd1: begin
                    if (dlab) dlh <= write_data[7:0];
                    else      ier <= write_data[7:0];
                end
                3'd2: begin
                    fcr <= write_data[7:0];
                    if (write_data[1]) begin
                        rx_fifo_head <= 4'd0;
                        rx_fifo_tail <= 4'd0;
                        rx_fifo_cleared = 1'b1;
                        rx_oe <= 1'b0;
                    end
                    if (write_data[2]) begin
                        tx_fifo_head  <= 4'd0;
                        tx_fifo_tail  <= 4'd0;
                        tx_fifo_cleared = 1'b1;
                        if (tx_start_pending && (tx_state == TX_IDLE)) begin
                            tx_start_pending <= 1'b0;
                            tx_busy          <= 1'b0;
                        end
                    end
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

        if (tx_fifo_cleared) begin
            tx_fifo_count <= 5'd0;
        end else if (tx_fifo_pushed && !tx_fifo_popped) begin
            tx_fifo_count <= tx_fifo_count + 1'b1;
        end else if (!tx_fifo_pushed && tx_fifo_popped) begin
            tx_fifo_count <= tx_fifo_count - 1'b1;
        end

        // ---- RX state machine ----
        rx_prev <= rx;
        case (rx_state)
            RX_IDLE: begin
                // Falling edge on rx = start bit
                if (rx_prev && !rx) begin
                    // Wait half a baud period to sample in the middle of start bit
                    rx_baud_counter <= {1'b0, baud_div[15:1]};
                    rx_state        <= RX_START;
                end
            end
            RX_START: begin
                if (rx_baud_counter > 0) begin
                    rx_baud_counter <= rx_baud_counter - 1'b1;
                end else begin
                    // Confirm start bit still low
                    if (!rx) begin
                        rx_baud_counter <= baud_div;
                        rx_state        <= RX_DATA;
                        rx_bit_count    <= 3'b0;
                        rx_shift        <= 8'h00;
                    end else begin
                        rx_state <= RX_IDLE; // false start
                    end
                end
            end
            RX_DATA: begin
                if (rx_baud_counter > 0) begin
                    rx_baud_counter <= rx_baud_counter - 1'b1;
                end else begin
                    rx_baud_counter             <= baud_div;
                    rx_shift[rx_bit_count]      <= rx;
                    if (rx_bit_count == 3'd7) begin
                        rx_state <= RX_STOP;
                    end else begin
                        rx_bit_count <= rx_bit_count + 1'b1;
                    end
                end
            end
            RX_STOP: begin
                if (rx_baud_counter > 0) begin
                    rx_baud_counter <= rx_baud_counter - 1'b1;
                end else begin
                    // Sample stop bit; if high → valid frame
                    if (rx && !rx_fifo_clear_request) begin
                        // A simultaneous RBR read frees a slot at this edge.
                        // An explicit FIFO clear discards the arriving byte.
                        if (rx_fifo_full && !rx_fifo_pop_request) begin
                            rx_oe <= 1'b1;
                        end else begin
                            rx_fifo[rx_fifo_tail] <= rx_shift;
                            rx_fifo_tail <= rx_fifo_tail + 1'b1;
                            rx_fifo_pushed = 1'b1;
                            rbr <= rx_shift;
                        end
                    end
                    rx_state <= RX_IDLE;
                end
            end
            default: rx_state <= RX_IDLE;
        endcase

        // Reading RBR consumes one queued byte. LSR.OE remains asserted until
        // the receiver FIFO is explicitly cleared, as on a 16550.
        if (rx_fifo_pop_request) begin
            rx_fifo_head <= rx_fifo_head + 1'b1;
            rx_fifo_popped = 1'b1;
        end

        if (rx_fifo_cleared) begin
            rx_fifo_count <= 5'd0;
        end else if (rx_fifo_pushed && !rx_fifo_popped) begin
            rx_fifo_count <= rx_fifo_count + 1'b1;
        end else if (!rx_fifo_pushed && rx_fifo_popped) begin
            rx_fifo_count <= rx_fifo_count - 1'b1;
        end

        // ---- THRE interrupt latch ----
        tx_thre_prev <= tx_thre;
        if (thre_irq_set) begin
            thre_irq <= 1'b1;
        end
        if (thre_irq_clear) begin
            thre_irq <= 1'b0;
        end
    end
end

// ---- register reads -------------------------------------------------------
always @(*) begin
    read_data = 32'h0;
    if (read_enable && uart_valid) begin
        case (reg_sel)
            3'd0: read_data = dlab ? {24'h0, dll} :
                                   {24'h0, (rx_dr ? rx_fifo_data : rbr)}; // RBR/DLL
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
