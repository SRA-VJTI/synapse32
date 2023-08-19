
# Logic gates

Logic gates are the basic building blocks for implementing logic functions. The table below shows basic logic gates. Their function is defined by the _"truth tables"_, which show, for each combination of input values (A & B), what the output value (X) will be. Be sure to understand the behavior of each gate.

![](https://instrumentationtools.com/wp-content/uploads/2017/07/instrumentationtools.com_digital-logic-gates-truthtables.png)



**Note**.
- **AND** and **OR** gates follow their English meanings.
- The small circle (or "bubble") on the output of some gates indicates an inverted output.
- **XOR** and **XNOR** are "exclusive" **OR** and **NOR**, where "exclusive" means _"but not both"_.

## TL-Verilog syntax for Logic expressions

Boolean logic has taken on various notations in different fields of study. The following chart shows some of these mathematical notations, as well as TL-Verilog operators (which are the same as Verilog) for basic logic gates.

![[syntax_logic.png]]

You can use parentheses to group expressions to form more complex logic functions. If a statement is extended to multiple lines, these lines must have greater indentation than the first line. Statements must always end with a semicolon.