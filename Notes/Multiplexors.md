
One of the most important logic functions is a multiplexer (or MUX), depicted below.

![[Screenshot from 2023-08-19 14-32-47.png]]

A multiplexer selects between two or more inputs (which can be binary values, vectors, or any other data type). The select line(s) identify the input to drive to the output. Most often, the select will be either a binary-encoded input index or a "one-hot" vector in which each bit of the vector corresponds to an input. One and only one of the bits will be asserted to select the corresponding input value.

The MUX depicted in the "Two-way single-bit multiplexer" graphic above can be constructed from basic logic gates, as seen below. We might read this implementation as "assert the output if X1 is asserted and selected (by **S == 1**) OR X2 is asserted and selected (by **S == 0**)".

![[Screenshot from 2023-08-19 14-33-56.png]]

## TL-Verilog Syntax

We will use  the Ternary Operator (? :) for coding a multiplexor. In its simplest form, the ternary operator is:
**$out = $sel ? $in1 : $in0;**

This can be read, "**$out** is**:** if **$sel** then **$in1** otherwise **$in0**."

The ternary operator can be chained to implement multiplexers with more than two input values from which to select. And these inputs can be vectors. We will use very specific code formatting for consistency, illustrated below for a four-way, 8-bit wide multiplexer with a one-hot select. (Here, **$in0-3** must be 8-bit vectors.)

**$out[7:0] =  
   $sel[3]  
      ? $in3 :  
   $sel[2]  
      ? $in2 :   $sel[1]  
      ? $in1 :  
   //default  
        $in0;**

This expression prioritizes top-to-bottom. So, if $sel[3] is asserted, $in3 will be driven on the output regardless of the other $sel bits. Its literal interpretation is depicted below, along with its single-gate representation (which is ambiguous about the priority).


![[Screenshot from 2023-08-19 14-40-33.png]]