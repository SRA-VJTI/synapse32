While individual wires (or "_bits_") hold one of two values in a digital circuit, we can have a collection of N wires (called a "_vector_") that represent up to 2^N possible values.

We are all used to representing numbers in base ten, or decimal. In decimal, we use ten digits, 0-9, and when we count past the last available digit, 9, we wrap back to 0 and increment the next place value, which is worth ten. Base ten, unfortunately, is very awkward for digital logic. Base two or any power of two (4, 8, 16) is much more natural. In base two, or binary, we have digits 0 and 1. Each digit can be represented by a bit. Base sixteen, or hexadecimal, is also very common. In hexadecimal, the digits are 0-9 and A-F (for ten through fifteen). A single hexadecimal digit can be represented by four bits.


![[Screenshot from 2023-08-19 14-24-58.png]]

## TL-Verilog Syntax
In TL-Verilog, the most common data types are booleans (as you used in the previous lab) and bit vectors. A vector is declared by providing a bit range in its assignment as so:

**$vect[7:0] = ....;**

Bit ranges are generally not required on the right-hand side of an expression. When they are used, they extract a subrange of bits from a vector signal.

In Verilog and TL-Verilog, arithmetic operators, like +, -, *, /, and % (modulo) can be used on vectors.Other vector operators are supported, including comparison operators like ==, !=, >, >=, <, <