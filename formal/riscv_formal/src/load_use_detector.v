`default_nettype none
// Include module for load-use hazard detection
// This detects when an instruction immediately after a load is using the loaded value
module load_use_detector (
    // Current instruction in ID stage
    input wire [4:0] rs1_id,
    input wire [4:0] rs2_id,
    input wire rs1_valid_id,
    input wire rs2_valid_id,
    
    // Previous instruction in EX stage
    input wire [5:0] instr_id_ex,
    input wire [4:0] rd_ex,
    input wire rd_valid_ex,
    
    // Control signal output
    output reg stall_pipeline
);

    // Import instruction defines
    `include "instr_defines.vh"
    
    // Detect if instruction in EX is a load
    wire is_load_in_ex;
    assign is_load_in_ex = (instr_id_ex == INSTR_LB) || 
                           (instr_id_ex == INSTR_LH) || 
                           (instr_id_ex == INSTR_LW) || 
                           (instr_id_ex == INSTR_LBU) || 
                           (instr_id_ex == INSTR_LHU);
    
    // Detect if current instruction depends on loaded value
    always @(*) begin
        stall_pipeline = 1'b0;
        
        if (is_load_in_ex && rd_valid_ex && (rd_ex != 5'b0)) begin
            if ((rs1_valid_id && (rs1_id == rd_ex)) || 
                (rs2_valid_id && (rs2_id == rd_ex))) begin
                stall_pipeline = 1'b1;
            end
        end
    end
    
endmodule
