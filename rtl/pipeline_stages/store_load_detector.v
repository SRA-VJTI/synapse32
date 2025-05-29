`default_nettype none
`include "instr_defines.vh"
module store_load_detector (
    // Current load instruction
    input wire [5:0] load_instr_id,
    input wire [31:0] load_addr,
    
    // Previous store instructions
    input wire [5:0] prev_store_instr_id,
    input wire [31:0] prev_store_addr,
    input wire [31:0] rs2_value, // Value to be stored in case of hazard
    
    // Output signals
    output wire store_load_hazard,
    output wire [31:0] forwarded_data
);
    
    // Detect if current instruction is a load
    wire is_load = (load_instr_id == INSTR_LB) || (load_instr_id == INSTR_LH) || 
                   (load_instr_id == INSTR_LW) || (load_instr_id == INSTR_LBU) || 
                   (load_instr_id == INSTR_LHU);
                   
    // Detect if previous instruction was a store
    wire is_store = (prev_store_instr_id == INSTR_SB) || (prev_store_instr_id == INSTR_SH) || 
                    (prev_store_instr_id == INSTR_SW);
                    
    // Check if addresses match
    wire addr_match = (load_addr == prev_store_addr);
    
    // Signal hazard when we have a load following a store to the same address
    assign store_load_hazard = is_load && is_store && addr_match;
    
    // Forward data from store if hazard exists
    assign forwarded_data = store_load_hazard ? rs2_value : 32'b0;
    
endmodule