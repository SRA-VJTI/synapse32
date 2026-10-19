`default_nettype none
// FIFO of translated writes waiting for the data port. Entry 0 is the oldest; it leaves when its
// write's response arrives. A load compares its word against every entry before it may go to memory.
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
    output reg match
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
    reg [DEPTH-1:0] valid_q;
    reg [COUNT_WIDTH-1:0] count;

    wire [COUNT_WIDTH-1:0] tail = pop ? count - 1'b1 : count;
    integer i;

    assign empty = (count == {COUNT_WIDTH{1'b0}});
    assign full = (count == DEPTH_COUNT);
    assign drained = (tail == {COUNT_WIDTH{1'b0}}) && !push;
    assign head_addr = addr_q[0];
    assign head_be = be_q[0];
    assign head_data = data_q[0];
    assign head_ram = ram_q[0];

    always @(*) begin
        match = 1'b0;
        for (i = 0; i < DEPTH; i = i + 1) begin
            if (valid_q[i] && (addr_q[i][31:2] == match_addr[31:2])) begin
                match = 1'b1;
            end
        end
    end

    always @(posedge clk or posedge rst) begin
        if (rst) begin
            for (i = 0; i < DEPTH; i = i + 1) begin
                addr_q[i] <= 32'b0;
                be_q[i] <= 4'b0;
                data_q[i] <= 32'b0;
            end
            ram_q <= {DEPTH{1'b0}};
            valid_q <= {DEPTH{1'b0}};
            count <= {COUNT_WIDTH{1'b0}};
        end else begin
            for (i = 0; i < DEPTH; i = i + 1) begin
                if (push && (i == {{(32-COUNT_WIDTH){1'b0}}, tail})) begin
                    addr_q[i] <= push_addr;
                    be_q[i] <= push_be;
                    data_q[i] <= push_data;
                    ram_q[i] <= push_ram;
                    valid_q[i] <= 1'b1;
                end else if (pop) begin
                    if (i < DEPTH - 1) begin
                        addr_q[i] <= addr_q[i + 1];
                        be_q[i] <= be_q[i + 1];
                        data_q[i] <= data_q[i + 1];
                        ram_q[i] <= ram_q[i + 1];
                        valid_q[i] <= valid_q[i + 1];
                    end else begin
                        valid_q[i] <= 1'b0;
                    end
                end
            end
            count <= tail + {{(COUNT_WIDTH-1){1'b0}}, push};
        end
    end
endmodule
