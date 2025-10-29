`default_nettype none
module store_load_forward (
    // Load instruction in MEM stage
    input wire [5:0] load_instr_id,
    input wire [31:0] load_mem_addr,
    input wire load_mem_read_en,
    
    // Store instruction in WB stage (previous instruction)
    input wire [5:0] store_instr_id_wb,
    input wire [31:0] store_mem_addr_wb,
    input wire [31:0] store_data_wb,
    
    // Store instruction in MEM stage (concurrent instruction)
    input wire [5:0] store_instr_id_mem,
    input wire [31:0] store_mem_addr_mem,
    input wire store_mem_write_en,
    input wire [31:0] store_data_mem,
    
    // Outputs
    output reg forward_needed,
    output reg [31:0] forwarded_data
);

    // Constants for instruction types
    localparam LB    = 6'd8;  // Load Byte
    localparam LH    = 6'd9;  // Load Halfword
    localparam LW    = 6'd10; // Load Word
    localparam LBU   = 6'd11; // Load Byte Unsigned
    localparam LHU   = 6'd12; // Load Halfword Unsigned
    
    localparam SB    = 6'd13; // Store Byte
    localparam SH    = 6'd14; // Store Halfword
    localparam SW    = 6'd15; // Store Word

    // Check if current instruction is a load
    wire is_load = (load_instr_id == LB || load_instr_id == LH || 
                   load_instr_id == LW || load_instr_id == LBU || 
                   load_instr_id == LHU) && load_mem_read_en;
                   
    // Check if previous instruction was a store
    wire is_store_mem = (store_instr_id_mem == SB || store_instr_id_mem == SH || 
                        store_instr_id_mem == SW) && store_mem_write_en;
                        
    // Check for address match between load and store
    wire addr_match_mem = (load_mem_addr == store_mem_addr_mem) && is_load && is_store_mem;
    
    always @(*) begin
        if (addr_match_mem) begin
            forward_needed = 1'b1;
            forwarded_data = store_data_mem;
        end else begin
            forward_needed = 1'b0;
            forwarded_data = 32'b0;
        end
    end
endmodule