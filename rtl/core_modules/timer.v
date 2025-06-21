`default_nettype none
`include "memory_map.vh"

module timer (
    input wire clk,
    input wire rst,
    
    // Memory interface for timer registers
    input wire [31:0] addr,
    input wire [31:0] write_data,
    input wire write_enable,
    input wire read_enable,
    output reg [31:0] read_data,
    output wire timer_valid,
    
    // Timer interrupt output
    output wire timer_interrupt
);

    // Timer registers
    reg [63:0] mtime;        // Machine time counter
    reg [63:0] mtimecmp;     // Machine time compare register
    
    // Address validation using memory map
    assign timer_valid = (addr == `MTIMECMP_LO) || (addr == `MTIMECMP_HI) ||
                        (addr == `MTIME_LO) || (addr == `MTIME_HI);
    
    // Timer interrupt generation
    assign timer_interrupt = (mtime >= mtimecmp);
    
    // Timer counter - increments every clock cycle
    always @(posedge clk or posedge rst) begin
        if (rst) begin
            mtime <= 64'h0;
            mtimecmp <= 64'hFFFFFFFFFFFFFFFF;
        end else begin
            mtime <= mtime + 1;
            
            if (write_enable && timer_valid) begin
                case (addr)
                    `MTIMECMP_LO: mtimecmp[31:0] <= write_data;
                    `MTIMECMP_HI: mtimecmp[63:32] <= write_data;
                    `MTIME_LO:    mtime[31:0] <= write_data;
                    `MTIME_HI:    mtime[63:32] <= write_data;
                    default: ;
                endcase
            end
        end
    end
    
    // Read logic
    always @(*) begin
        read_data = 32'h0;
        
        if (read_enable && timer_valid) begin
            case (addr)
                `MTIMECMP_LO: read_data = mtimecmp[31:0];
                `MTIMECMP_HI: read_data = mtimecmp[63:32];
                `MTIME_LO:    read_data = mtime[31:0];
                `MTIME_HI:    read_data = mtime[63:32];
                default:      read_data = 32'h0;
            endcase
        end
    end

endmodule