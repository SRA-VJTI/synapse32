`default_nettype none
// FIFO of translated writes waiting for the data port; entry 0 is the oldest and drains first.
module store_buffer #(
    parameter DEPTH = 4
) (
    input wire clk,
    input wire rst,
    input wire push,
    input wire [31:0] push_addr,
    input wire [3:0] push_be,
    input wire [31:0] push_data,
    input wire push_ram,
    input wire pop,
    output wire empty,
    output wire full,
    output wire drained,  // Empty once this cycle's push and pop are done
    output wire [31:0] head_addr,
    output wire [3:0] head_be,
    output wire [31:0] head_data,
    output wire head_ram,
    input wire [31:0] match_addr,
    input wire [2:0] match_type,
    output reg match,
    // The last write to the word is RAM and holds every byte the load reads.
    output wire forward,
    output wire [31:0] forward_data
);
    // Wide enough to hold DEPTH itself.
    localparam COUNT_WIDTH = (DEPTH < 2) ? 1 :
                             (DEPTH < 4) ? 2 :
                             (DEPTH < 8) ? 3 :
                             (DEPTH < 16) ? 4 : 8;
    localparam [31:0] DEPTH_FULL = DEPTH;
    localparam [COUNT_WIDTH-1:0] DEPTH_COUNT = DEPTH_FULL[COUNT_WIDTH-1:0];

    reg [31:0] addr_q [0:DEPTH-1];
    reg [3:0] be_q [0:DEPTH-1];
    reg [31:0] data_q [0:DEPTH-1];
    reg [DEPTH-1:0] ram_q;
    reg [COUNT_WIDTH-1:0] count;

    wire [COUNT_WIDTH-1:0] tail = pop ? count - 1'b1 : count;
    integer i, j;

    // The last write to the word, in byte lanes (entries hold be and data relative to their address).
    reg [3:0] last_be;
    reg [31:0] last_data;
    reg last_ram;
    wire [3:0] load_be = (match_type[1:0] == 2'b00) ? (4'b0001 << match_addr[1:0]) :
                         (match_type[1:0] == 2'b01) ? (4'b0011 << match_addr[1:0]) : 4'b1111;
    wire [31:0] last_lanes = last_data >> {match_addr[1:0], 3'b000};

    assign forward = match && last_ram && ((load_be & ~last_be) == 4'b0);
    assign forward_data = (match_type == 3'b000) ? {{24{last_lanes[7]}}, last_lanes[7:0]} :
                          (match_type == 3'b100) ? {24'b0, last_lanes[7:0]} :
                          (match_type == 3'b001) ? {{16{last_lanes[15]}}, last_lanes[15:0]} :
                          (match_type == 3'b101) ? {16'b0, last_lanes[15:0]} : last_data;

    assign empty = (count == {COUNT_WIDTH{1'b0}});
    assign full = (count == DEPTH_COUNT);
    assign drained = (tail == {COUNT_WIDTH{1'b0}}) && !push;
    assign head_addr = addr_q[0];
    assign head_be = be_q[0];
    assign head_data = data_q[0];
    assign head_ram = ram_q[0];

    always @(*) begin
        match = 1'b0;
        last_be = 4'b0;
        last_data = 32'b0;
        last_ram = 1'b0;
        for (i = 0; i < DEPTH; i = i + 1) begin
            if (({{(32-COUNT_WIDTH){1'b0}}, count} > i) && (addr_q[i][31:2] == match_addr[31:2])) begin
                match = 1'b1;
                last_be = be_q[i] << addr_q[i][1:0];
                last_data = data_q[i] << {addr_q[i][1:0], 3'b000};
                last_ram = ram_q[i];
            end
        end
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            for (j = 0; j < DEPTH; j = j + 1) begin
                addr_q[j] <= 32'b0;
                be_q[j] <= 4'b0;
                data_q[j] <= 32'b0;
            end
            ram_q <= {DEPTH{1'b0}};
            count <= {COUNT_WIDTH{1'b0}};
        end else begin
            for (j = 0; j < DEPTH - 1; j = j + 1) begin
                if (push && (j == {{(32-COUNT_WIDTH){1'b0}}, tail})) begin
                    addr_q[j] <= push_addr;
                    be_q[j] <= push_be;
                    data_q[j] <= push_data;
                    ram_q[j] <= push_ram;
                end else if (pop) begin
                    addr_q[j] <= addr_q[j + 1];
                    be_q[j] <= be_q[j + 1];
                    data_q[j] <= data_q[j + 1];
                    ram_q[j] <= ram_q[j + 1];
                end
            end
            // The last entry has nothing behind it to shift in.
            if (push && (tail == DEPTH_COUNT - 1'b1)) begin
                addr_q[DEPTH-1] <= push_addr;
                be_q[DEPTH-1] <= push_be;
                data_q[DEPTH-1] <= push_data;
                ram_q[DEPTH-1] <= push_ram;
            end
            count <= tail + {{(COUNT_WIDTH-1){1'b0}}, push};
        end
    end
endmodule
