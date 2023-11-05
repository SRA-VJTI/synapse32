
module blink (

   output reg s1_a,
   output reg s1_b,
   output reg s1_c,
   output reg s1_d,
   output reg s1_e,
   output reg s1_f,
   output reg s1_g,
   output reg led_blue,
   output reg led_red,
   output reg led_green
   
   
   
);

	wire clk;
	SB_HFOSC inthosc (.CLKHFPU(1'b1), .CLKHFEN(1'b1), .CLKHF(clk));
   wire [31:0]final_output;
   reg divided_clk;
   reg [31:0] counter_value;
   parameter div_value = 6000000;
   
	
	wire rst;
	wire	imem_wr_en;
	wire	[31:0] imem_data_in;
	wire	rd_valid;
	wire	imm_valid;
	wire	func3_valid;
	wire	func7_valid;

	wire	[2:0] funct3;
	wire	[6:0] funct7;
	wire	[6:0] s1;
	wire	[6:0] s2;
	wire	[6:0] s3;
	wire	[6:0] s4;
	wire	[6:0] s5;
	wire	[6:0] s6;
	wire	[6:0] s7;
	wire	[6:0] s8;
	

	
   initial begin
      divided_clk=1;
      counter_value = 32'b0;
      led_blue = 1'b1;
      led_green = 1'b1;
      led_red = 1'b1;
      s1_a<=1'b0;
      s1_b<=1'b0;
      s1_c<=1'b0;
      s1_d<=1'b0;
      s1_e<=1'b0;
      s1_f<=1'b0;
      s1_g<=1'b0;
   end

   
   always @ (posedge clk) begin
      
      counter_value <= counter_value == div_value ? 0 : counter_value + 32'b1;
      divided_clk <= counter_value == div_value ? ~divided_clk : divided_clk;
      //led_blue <= divided_clk;
      s1_a <= s1[6];
      s1_b<=s1[5];
      s1_c<=s1[4];
      s1_d<=s1[3];
      s1_e<=s1[2];
      s1_f<=s1[1];
      s1_g<=s1[0];
   end


   
   risc_v risc_v_1 (.clk(divided_clk),.final_output(final_output),.rst(rst),.imem_wr_en(imem_wr_en),
							.imem_data_in(imem_data_in),.rd_valid(rd_valid),.imm_valid(imm_valid),.func3_valid(func3_valid),
							.func7_valid(func7_valid),.funct3(funct3),.funct7(funct7),.s1(s1),.s2(s2),
							.s3(s3),.s4(s4),.s5(s5),.s6(s6),.s7(s7));

  

endmodule 
