`default_nettype none
`include "instr_defines.vh"
module forwarding_unit (
    // Current instruction registers to check
    input wire [4:0] rs1_addr_ex,
    input wire [4:0] rs2_addr_ex,
    input wire rs1_valid_ex,
    input wire rs2_valid_ex,
    
    // Previous instructions (in MEM stage)
    input wire [4:0] rd_addr_mem,
    input wire rd_valid_mem,
    input wire [5:0] instr_id_mem,
    
    // Two-stages ago instructions (in WB stage)
    input wire [4:0] rd_addr_wb,
    input wire rd_valid_wb,
    input wire wr_en_wb,
    
    // Forwarding control signals
    output reg [1:0] forward_a, // For rs1
    output reg [1:0] forward_b  // For rs2
);

    // Forwarding control values
    localparam NO_FORWARDING = 2'b00;   // Use the value from register file
    localparam FORWARD_FROM_MEM = 2'b01; // Forward from MEM stage
    localparam FORWARD_FROM_WB = 2'b10;  // Forward from WB stage
    
    // Determine if MEM stage contains a load instruction
    wire is_mem_load;
    assign is_mem_load = (instr_id_mem == INSTR_LB) || 
                         (instr_id_mem == INSTR_LH) || 
                         (instr_id_mem == INSTR_LW) || 
                         (instr_id_mem == INSTR_LBU) || 
                         (instr_id_mem == INSTR_LHU);
    
    always @(*) begin
        // Default: no forwarding
        forward_a = NO_FORWARDING;
        forward_b = NO_FORWARDING;
        
        // Forward to RS1 if needed
        if (rs1_valid_ex) begin
            // Check if forwarding from MEM stage is needed
            // Don't forward for a load in MEM stage - wait for it to reach WB
            if (rd_valid_mem && (rd_addr_mem != 5'b0) && (rd_addr_mem == rs1_addr_ex) && !is_mem_load) begin
                forward_a = FORWARD_FROM_MEM;
            end
            // Check if forwarding from WB stage is needed (only if MEM isn't forwarding)
            else if (rd_valid_wb && wr_en_wb && (rd_addr_wb != 5'b0) && (rd_addr_wb == rs1_addr_ex)) begin
                forward_a = FORWARD_FROM_WB;
            end
        end
        
        // Forward to RS2 if needed
        if (rs2_valid_ex) begin
            // Check if forwarding from MEM stage is needed
            // Don't forward for a load in MEM stage - wait for it to reach WB
            if (rd_valid_mem && (rd_addr_mem != 5'b0) && (rd_addr_mem == rs2_addr_ex) && !is_mem_load) begin
                forward_b = FORWARD_FROM_MEM;
            end
            // Check if forwarding from WB stage is needed (only if MEM isn't forwarding)
            else if (rd_valid_wb && wr_en_wb && (rd_addr_wb != 5'b0) && (rd_addr_wb == rs2_addr_ex)) begin
                forward_b = FORWARD_FROM_WB;
            end
        end
    end

endmodule
