
# Clock and Flip-Flops

Sequential Logic introduces a clock signal 

![](https://learn.circuitverse.org/assets/images/clock_signal.jpg)

The clock is driven throughout the circuit to "flip-flops" which sequence the logic. Flip-flops come in various flavors, but the simplest and most common type of flip-flop, and the only one we will concern ourselves with, is called a "positive-edge-triggered D-type flip-flop". These drive the value at their input to their output, but only when the clock rises. They hold their output value until the next rising edge of their clock input.

Although there are also flip-flops that act on the falling edge of the clock, our circuits will operate only on the rising edge. Additionally, there are flip-flops that incorporate logic functions. Tools can choose to implement our designs using these flip-flops even though we will not be explicit about doing so in our source code. Since we will use only D flip-flops, we will henceforth refer to them simply as flip-flops, or even just "flops".

## TL-Verilog Syntax

In TL-Verilog, we can reference the previous and previous-previous versions of $num as ">>1 $num" and ">>2 $num"   .Unlike RTL, in TL design we need not assign these explicitly. They are implicitly available for use, and the need for flip-flops is implied.