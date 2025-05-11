module top (
    input clk,
    input reset,
    input Ext_MemWrite,
    input [31:0] Ext_WriteData, Ext_DataAdr,
    output MemWrite,
    output [31:0] WriteData, DataAdr, ReadData,
    output [31:0] ProgramCounter
);

// wire lines from other modules
wire [31:0] PC;
assign ProgramCounter = PC;
wire [31:0] Instr;
wire MemWrite_rv32;
wire [31:0] DataAdr_rv32, WriteData_rv32;

// instantiate processor and memories
riscv_cpu rvsingle (
    .clk(clk), .reset(reset), .PC(PC), .Instr(Instr),
    .MemWrite(MemWrite_rv32), .Mem_WrAddr(DataAdr_rv32), .Mem_WrData(WriteData_rv32),
    .ReadData(ReadData)
);
instr_mem imem (
    .instr_addr(PC), .instr(Instr)
);
data_mem dmem (
    .clk(clk), .wr_en(MemWrite), .wr_addr(DataAdr), .wr_data(WriteData), .rd_data_mem(ReadData)
);

// output assignments
assign MemWrite = (Ext_MemWrite && reset) ? 1 : MemWrite_rv32;
assign WriteData = (Ext_MemWrite && reset) ? Ext_WriteData : WriteData_rv32;
assign DataAdr = (reset) ? Ext_DataAdr : DataAdr_rv32;

endmodule
