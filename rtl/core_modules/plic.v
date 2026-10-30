`default_nettype none
`include "memory_map.vh"

// Two contexts per the PLIC spec: context 0 drives the machine external interrupt, context 1 the
// supervisor one. Sources are numbered 1 .. NUM_SOURCES; source 0 does not exist.
module plic #(
    parameter NUM_SOURCES = 2
) (
    input  wire        clk,
    input  wire        rst,
    input  wire [31:0] addr,
    input  wire [31:0] write_data,
    input  wire        write_enable,
    input  wire        read_enable,
    output reg  [31:0] read_data,
    output wire        plic_valid,
    input  wire [NUM_SOURCES:1] source_irq,
    output wire        machine_external_interrupt,
    output wire        supervisor_external_interrupt
);

localparam PRIORITY_BASE     = `PLIC_BASE + 32'h000000;
localparam PENDING_ADDR      = `PLIC_BASE + 32'h001000;
localparam ENABLE_M_ADDR     = `PLIC_BASE + 32'h002000;
localparam ENABLE_S_ADDR     = `PLIC_BASE + 32'h002080;
localparam THRESHOLD_M_ADDR  = `PLIC_BASE + 32'h200000;
localparam CLAIM_M_ADDR      = `PLIC_BASE + 32'h200004;
localparam THRESHOLD_S_ADDR  = `PLIC_BASE + 32'h201000;
localparam CLAIM_S_ADDR      = `PLIC_BASE + 32'h201004;
localparam ID_BITS = 5;

reg [2:0] priority_q [1:NUM_SOURCES];
reg [NUM_SOURCES:1] pending;
reg [NUM_SOURCES:1] gateway_busy;
reg [NUM_SOURCES:1] enable_m;
reg [NUM_SOURCES:1] enable_s;
reg [2:0] threshold_m;
reg [2:0] threshold_s;
integer i, j, k;

// The pending, enabled source with the highest priority above the threshold; ties go to the lower ID.
function [ID_BITS-1:0] best_source;
    input [NUM_SOURCES:1] enabled;
    input [2:0] threshold;
    integer s;
    reg [2:0] best_priority;
    begin
        best_source = {ID_BITS{1'b0}};
        best_priority = threshold;
        for (s = 1; s <= NUM_SOURCES; s = s + 1) begin
            if (pending[s] && enabled[s] && (priority_q[s] > best_priority)) begin
                best_source = s[ID_BITS-1:0];
                best_priority = priority_q[s];
            end
        end
    end
endfunction

wire plic_access = `IS_PLIC_MEM(addr);
wire [ID_BITS-1:0] claim_id_m = best_source(enable_m, threshold_m);
wire [ID_BITS-1:0] claim_id_s = best_source(enable_s, threshold_s);
wire claim_read_m = read_enable && plic_access && (addr == CLAIM_M_ADDR) && (claim_id_m != 0);
wire claim_read_s = read_enable && plic_access && (addr == CLAIM_S_ADDR) && (claim_id_s != 0);
wire complete_write = write_enable && plic_access && ((addr == CLAIM_M_ADDR) || (addr == CLAIM_S_ADDR));

assign plic_valid = plic_access;
assign machine_external_interrupt = (claim_id_m != 0);
assign supervisor_external_interrupt = (claim_id_s != 0);

always @(posedge clk or posedge rst) begin
    if (rst) begin
        for (i = 1; i <= NUM_SOURCES; i = i + 1) begin
            priority_q[i] <= 3'd1;
        end
        pending      <= {NUM_SOURCES{1'b0}};
        gateway_busy <= {NUM_SOURCES{1'b0}};
        enable_m     <= {NUM_SOURCES{1'b0}};
        enable_s     <= {NUM_SOURCES{1'b0}};
        threshold_m  <= 3'd0;
        threshold_s  <= 3'd0;
    end else begin
        if (write_enable && plic_access) begin
            for (i = 1; i <= NUM_SOURCES; i = i + 1) begin
                if (addr == PRIORITY_BASE + 4 * i) begin
                    priority_q[i] <= write_data[2:0];
                end
            end
            case (addr)
                ENABLE_M_ADDR:    enable_m <= write_data[NUM_SOURCES:1];
                ENABLE_S_ADDR:    enable_s <= write_data[NUM_SOURCES:1];
                THRESHOLD_M_ADDR: threshold_m <= write_data[2:0];
                THRESHOLD_S_ADDR: threshold_s <= write_data[2:0];
                default: ;
            endcase
        end

        // Level-triggered gateway (PLIC spec): one request per source is forwarded until software
        // completes it through the claim/complete register.
        for (j = 1; j <= NUM_SOURCES; j = j + 1) begin
            if ((claim_read_m && (claim_id_m == j[ID_BITS-1:0])) || (claim_read_s && (claim_id_s == j[ID_BITS-1:0]))) begin
                pending[j] <= 1'b0;
            end
            if (complete_write && (write_data == j) && gateway_busy[j]) begin
                if (source_irq[j]) begin
                    pending[j] <= 1'b1;
                end else begin
                    gateway_busy[j] <= 1'b0;
                end
            end else if (!gateway_busy[j] && source_irq[j]) begin
                pending[j] <= 1'b1;
                gateway_busy[j] <= 1'b1;
            end
        end
    end
end

always @(*) begin
    read_data = 32'h0;
    if (read_enable && plic_access) begin
        for (k = 1; k <= NUM_SOURCES; k = k + 1) begin
            if (addr == PRIORITY_BASE + 4 * k) begin
                read_data = {29'h0, priority_q[k]};
            end
        end
        case (addr)
            PENDING_ADDR:     read_data = {{(31-NUM_SOURCES){1'b0}}, pending, 1'b0};
            ENABLE_M_ADDR:    read_data = {{(31-NUM_SOURCES){1'b0}}, enable_m, 1'b0};
            ENABLE_S_ADDR:    read_data = {{(31-NUM_SOURCES){1'b0}}, enable_s, 1'b0};
            THRESHOLD_M_ADDR: read_data = {29'h0, threshold_m};
            THRESHOLD_S_ADDR: read_data = {29'h0, threshold_s};
            CLAIM_M_ADDR:     read_data = {{(32-ID_BITS){1'b0}}, claim_id_m};
            CLAIM_S_ADDR:     read_data = {{(32-ID_BITS){1'b0}}, claim_id_s};
            default: ;
        endcase
    end
end

endmodule
