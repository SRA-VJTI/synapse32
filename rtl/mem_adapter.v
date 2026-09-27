`default_nettype none
// Request/response port in front of a combinational backing store, one transaction at a time:
// the core holds req, addr, we, be and wdata until gnt, and the response comes on rvalid/rdata.
// RESPONSE_LATENCY 0 answers in the same cycle, as the memory always has; 1 or more registers
// the response, as a BRAM or a DDR bridge does.
module mem_adapter #(
    parameter RESPONSE_LATENCY = 0
) (
    input wire clk,
    input wire rst,

    // Core side
    input wire req,
    input wire [31:0] addr,
    input wire we,
    input wire [3:0] be,
    input wire [31:0] wdata,
    output wire gnt,
    output wire rvalid,
    output wire [31:0] rdata,

    // Storage side
    output wire [31:0] store_addr,
    output wire store_we,
    output wire [3:0] store_be,
    output wire [31:0] store_wdata,
    output wire write_fire,
    output wire read_fire,
    input wire [31:0] store_rdata
);

    generate
        if (RESPONSE_LATENCY == 0) begin : g_combinational
            assign gnt = req;
            assign rvalid = req;
            assign rdata = store_rdata;
            assign store_addr = addr;
            assign store_we = we;
            assign store_be = be;
            assign store_wdata = wdata;
            assign write_fire = req && we;
            assign read_fire = req && !we;
        end else begin : g_registered
            localparam COUNT_WIDTH = (RESPONSE_LATENCY < 3) ? 1 :
                                     (RESPONSE_LATENCY < 5) ? 2 :
                                     (RESPONSE_LATENCY < 9) ? 3 :
                                     (RESPONSE_LATENCY < 17) ? 4 : 8;
            localparam [31:0] LAST_FULL = RESPONSE_LATENCY - 1;
            localparam [COUNT_WIDTH-1:0] LAST = LAST_FULL[COUNT_WIDTH-1:0];

            reg busy;
            reg [COUNT_WIDTH-1:0] count;
            reg [31:0] addr_q;
            reg we_q;
            reg [3:0] be_q;
            reg [31:0] wdata_q;
            reg [31:0] rdata_q;
            reg rvalid_q;

            // Accept only while idle, and not in the cycle a response is presented.
            assign gnt = req && !busy && !rvalid_q;
            // Last wait cycle: sample the read and commit the write; the response follows registered.
            wire accept = gnt;
            wire sample_now = busy && (count == LAST);
            wire sample_on_accept = accept && (RESPONSE_LATENCY == 1);

            always @(posedge clk or posedge rst) begin
                if (rst) begin
                    busy <= 1'b0;
                    count <= {COUNT_WIDTH{1'b0}};
                    addr_q <= 32'b0;
                    we_q <= 1'b0;
                    be_q <= 4'b0;
                    wdata_q <= 32'b0;
                    rdata_q <= 32'b0;
                    rvalid_q <= 1'b0;
                end else begin
                    rvalid_q <= 1'b0;
                    if (accept) begin
                        addr_q <= addr;
                        we_q <= we;
                        be_q <= be;
                        wdata_q <= wdata;
                        if (sample_on_accept) begin
                            rdata_q <= store_rdata;
                            rvalid_q <= 1'b1;
                        end else begin
                            busy <= 1'b1;
                            count <= {{(COUNT_WIDTH-1){1'b0}}, 1'b1};
                        end
                    end else if (sample_now) begin
                        rdata_q <= store_rdata;
                        rvalid_q <= 1'b1;
                        busy <= 1'b0;
                        count <= {COUNT_WIDTH{1'b0}};
                    end else if (busy) begin
                        count <= count + {{(COUNT_WIDTH-1){1'b0}}, 1'b1};
                    end
                end
            end

            assign store_addr = busy ? addr_q : addr;
            assign store_we = busy ? we_q : we;
            assign store_be = busy ? be_q : be;
            assign store_wdata = busy ? wdata_q : wdata;
            assign write_fire = (sample_now && we_q) || (sample_on_accept && we);
            assign read_fire = (sample_now && !we_q) || (sample_on_accept && !we);
            assign rvalid = rvalid_q;
            assign rdata = rdata_q;
        end
    endgenerate

endmodule
