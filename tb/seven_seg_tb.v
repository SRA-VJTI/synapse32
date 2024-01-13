module seven_seg_tb;
reg clk;
reg [31:0] bcd;
reg[6:0] opcode;
wire [6:0] s1;
wire [6:0] s2;
wire [6:0] s3;
wire [6:0] s4;
wire [6:0] s5;
wire [6:0] s6;
wire [6:0] s7;
wire [6:0] s8;

seven_seg seven_seg_1(.bcd(bcd),.opcode(opcode),.s1(s1),.s2(s2),.s3(s3),.s4(s4),
								.s5(s5),.s6(s6),.s7(s7),.s8(s8),.clk(clk));
			
initial clk=0;
always #10 clk = ~clk;			
initial begin 

opcode=7'b0110011;
bcd=32'h66;
#100;
bcd=32'h78;
#100;
bcd=32'h67;
#100;
bcd=32'h91;
#100;

end
endmodule 