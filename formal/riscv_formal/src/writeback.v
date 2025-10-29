// Module for the write-back stage to select correct data to write to register file
`default_nettype none
`include "instr_defines.vh"
module writeback (
    input wire rd_valid_in,
    input wire [4:0] rd_addr_in,
    input wire [31:0] rd_value_in,        // ALU result
    input wire [31:0] mem_data_in,        // Data from memory load
    input wire [5:0] instr_id_in,         // To identify load instructions
    output wire [4:0] rd_addr_out,
    output wire [31:0] rd_value_out,
    output wire wr_en_out
);
    wire is_load_instr;
    assign is_load_instr = (instr_id_in == INSTR_LB) || 
                           (instr_id_in == INSTR_LH) || 
                           (instr_id_in == INSTR_LW) || 
                           (instr_id_in == INSTR_LBU) || 
                           (instr_id_in == INSTR_LHU);
    
    // Select appropriate data to write back
    assign rd_addr_out = rd_addr_in;
    assign rd_value_out = is_load_instr ? mem_data_in : rd_value_in;
    assign wr_en_out = rd_valid_in;
    
endmodule