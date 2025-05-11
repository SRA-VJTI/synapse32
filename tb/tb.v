`timescale 1 ns/1 ns

module tb;

reg clk, reset, Ext_MemWrite;
reg [31:0] Ext_WriteData, Ext_DataAdr;

wire [31:0] WriteData, DataAdr, ReadData;
wire MemWrite;

reg [4:0] SP = 0, EP = 0;

integer error_count = 0, i = 0;
integer fw = 0, fd = 0, num_values = 16;
reg [4:0] register_array [0:15];
integer value = 0;
wire [31:0] ProgramCounter;

top uut (clk, reset, Ext_MemWrite, Ext_WriteData, Ext_DataAdr, MemWrite, WriteData, DataAdr, ReadData, ProgramCounter);

initial begin
    $dumpfile("tb.vcd");
    $dumpvars(0, tb, uut.rvsingle.b2v_inst4.register_file[2], uut.rvsingle.b2v_inst4.register_file[3]);
    //dump all registers in data_ram of dmem module to vcd file
    for (i = 0; i < 64; i = i + 1) begin
        $dumpvars(0, tb, uut.dmem.data_ram[i]);
    end
    reset <= 0;
    clk <= 0;
end


integer cycles = 0;
integer max_cycles = 10000;
always begin
    #5 clk <= ~clk;
    cycles = cycles + 1;
    //when DataAdr is 0x02000008, log the value of WriteData
    if (DataAdr > 32'h02000010 && MemWrite == 1 && clk == 1) begin
        $display("WriteData = %d", WriteData);
    end
    //end simulation when DataAdr is  0x0200000c and WriteData is 1
    if (DataAdr == 32'h0200000c && WriteData == 55 && clk == 1) begin
        $display("Simulation ended successfully");
        $finish;
    end
end

endmodule

