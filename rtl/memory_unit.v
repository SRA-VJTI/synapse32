`default_nettype none
`include "instr_defines.vh"
module memory_unit (
    input wire [5:0] instr_id,
    input wire [31:0] rs2_value,
    input wire [31:0] mem_addr,
    output wire wr_enable,
    output wire read_enable,
    output wire [31:0] wr_data,
    output wire [31:0] read_addr,
    output wire [31:0] wr_addr
);

//Based on the instruction ID, set the wr_enable and read_enable signals
assign read_enable = (instr_id == INSTR_LB) || (instr_id == INSTR_LH) || (instr_id == INSTR_LW) || (instr_id == INSTR_LBU) || (instr_id == INSTR_LHU) ? 1'b1 : 1'b0;
assign wr_enable = (instr_id == INSTR_SB) || (instr_id == INSTR_SH) || (instr_id == INSTR_SW) ? 1'b1 : 1'b0;
assign wr_addr = mem_addr;
assign read_addr = mem_addr;
assign wr_data = rs2_value;

endmodule