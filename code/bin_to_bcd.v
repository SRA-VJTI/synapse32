`timescale 1ns / 1ps
//////////////////////////////////////////////////////////////////////////////////
// Company: 
// Engineer: 
// 
// Create Date: 07.09.2023 12:01:35
// Design Name: 
// Module Name: bin_to_bcd
// Project Name: 
// Target Devices: 
// Tool Versions: 
// Description: 
// 
// Dependencies: 
// 
// Revision:
// Revision 0.01 - File Created
// Additional Comments:
// 
//////////////////////////////////////////////////////////////////////////////////


module bin_to_bcd(
   input clk,
   input [31:0] bin,
   output [31:0] bcd
   
   );
wire[31:0] bcd_data;
function [31:0] division(
input [31:0] in,
input [31:0] d,
input[31:0]r);
begin
d=(in>>1)+(in>>2); //d=3in/4
d=d+(d>>4);  //d=51in/64
d=d+(d>>8);  //d=0.8in approx
d=d>>3;      //d=0.1in
r=in-(((d<<2)+d) << 1); //rounding
division=d+(r>9);
end
endfunction

wire [31:0] start;
wire[31:0] step1,step2,step3,step4,step5,step6,step7,step8,step9,step10,step11,step12,step13,step14,step15 ;

assign start= bin;

assign step1= division(start,0,0);
assign bcd_data[3:0] = start-((step1<<3)+(step1<<1)); // mutliplied by 10 so that when subtracted with original number we get last digit 
assign step2=step1;

assign step3= division(step2,0,0);
assign bcd_data[7:4] = step2-((step3<<3)+(step3<<1));
assign step4=step3;

assign step5= division(step4,0,0);
assign bcd_data[11:8] = step4-((step5<<3)+(step5<<1));
assign step6=step5;

assign step7= division(step6,0,0);
assign bcd_data[15:12] = step6-((step7<<3)+(step7<<1));
assign step8=step7;

assign step9= division(step8,0,0);
assign bcd_data[19:16] = step8-((step9<<3)+(step9<<1));
assign step10=step9;

assign step11= division(step10,0,0);
assign bcd_data[23:20] = step10-((step11<<3)+(step11<<1));
assign step12=step11;

assign step13= division(step12,0,0);
assign bcd_data[27:24] = step12-((step13<<3)+(step13<<1));
assign step14=step13;

assign step15= division(step14,0,0);
assign bcd_data[31:28] = step14-((step15<<3)+(step15<<1));

assign bcd = bcd_data[31:0];

endmodule