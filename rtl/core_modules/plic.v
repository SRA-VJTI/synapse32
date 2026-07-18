`default_nettype none
`include "memory_map.vh"

module plic (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] addr,
    input  wire [31:0] write_data,
    input  wire        write_enable,
    input  wire        read_enable,
    output reg  [31:0] read_data,
    output wire        plic_valid,
    input  wire        source_irq,
    output wire        external_interrupt
);

localparam PRIORITY_1_ADDR   = `PLIC_BASE + 32'h000004;
localparam PENDING_ADDR      = `PLIC_BASE + 32'h001000;
localparam ENABLE_M_ADDR     = `PLIC_BASE + 32'h002000;
localparam ENABLE_S_ADDR     = `PLIC_BASE + 32'h002080;
localparam THRESHOLD_M_ADDR  = `PLIC_BASE + 32'h200000;
localparam CLAIM_M_ADDR      = `PLIC_BASE + 32'h200004;
localparam THRESHOLD_S_ADDR  = `PLIC_BASE + 32'h201000;
localparam CLAIM_S_ADDR      = `PLIC_BASE + 32'h201004;

reg [2:0] priority_1;
reg       pending_1;
reg       gateway_busy_1;
reg       enable_m_1;
reg       enable_s_1;
reg [2:0] threshold_m;
reg [2:0] threshold_s;

wire plic_access = `IS_PLIC_MEM(addr);
wire irq_eligible_m = pending_1 && enable_m_1 && (priority_1 > threshold_m);
wire irq_eligible_s = pending_1 && enable_s_1 && (priority_1 > threshold_s);
wire claim_read_m = read_enable && plic_access && (addr == CLAIM_M_ADDR) && irq_eligible_m;
wire claim_read_s = read_enable && plic_access && (addr == CLAIM_S_ADDR) && irq_eligible_s;
wire complete_write_m = write_enable && plic_access && (addr == CLAIM_M_ADDR) && (write_data == 32'd1);
wire complete_write_s = write_enable && plic_access && (addr == CLAIM_S_ADDR) && (write_data == 32'd1);
wire claim_event = claim_read_m || claim_read_s;
wire complete_event = complete_write_m || complete_write_s;

assign plic_valid = plic_access;
assign external_interrupt = irq_eligible_m || irq_eligible_s;

always @(posedge clk or posedge rst) begin
    if (rst) begin
        priority_1    <= 3'd1;
        pending_1     <= 1'b0;
        gateway_busy_1 <= 1'b0;
        enable_m_1    <= 1'b0;
        enable_s_1    <= 1'b0;
        threshold_m   <= 3'd0;
        threshold_s   <= 3'd0;
    end else begin
        if (write_enable && plic_access) begin
            case (addr)
                PRIORITY_1_ADDR:  priority_1 <= write_data[2:0];
                ENABLE_M_ADDR:    enable_m_1 <= write_data[1];
                ENABLE_S_ADDR:    enable_s_1 <= write_data[1];
                THRESHOLD_M_ADDR: threshold_m <= write_data[2:0];
                THRESHOLD_S_ADDR: threshold_s <= write_data[2:0];
                default: ;
            endcase
        end

        // Level-triggered gateway behavior from the ratified PLIC spec:
        // only one request per source may be forwarded to the core until
        // software completes it through the claim/complete register.
        if (claim_event) begin
            pending_1 <= 1'b0;
        end

        if (complete_event && gateway_busy_1) begin
            if (source_irq) begin
                pending_1 <= 1'b1;
            end else begin
                gateway_busy_1 <= 1'b0;
            end
        end else if (!gateway_busy_1 && source_irq) begin
            pending_1 <= 1'b1;
            gateway_busy_1 <= 1'b1;
        end
    end
end

always @(*) begin
    read_data = 32'h0;
    if (read_enable && plic_access) begin
        case (addr)
            PRIORITY_1_ADDR:  read_data = {29'h0, priority_1};
            PENDING_ADDR:     read_data = {30'h0, pending_1, 1'b0};
            ENABLE_M_ADDR:    read_data = {30'h0, enable_m_1, 1'b0};
            ENABLE_S_ADDR:    read_data = {30'h0, enable_s_1, 1'b0};
            THRESHOLD_M_ADDR: read_data = {29'h0, threshold_m};
            THRESHOLD_S_ADDR: read_data = {29'h0, threshold_s};
            CLAIM_M_ADDR:     read_data = irq_eligible_m ? 32'd1 : 32'd0;
            CLAIM_S_ADDR:     read_data = irq_eligible_s ? 32'd1 : 32'd0;
            default:          read_data = 32'h0;
        endcase
    end
end

endmodule
