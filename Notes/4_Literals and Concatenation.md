
# Literals

This expression:

**$foo[7:0] = 6;**

defines **$foo** to hold a constant value of 6. In this case, the 6 is coerced to eight bits by the assignment. Often, it is necessary to be explicit about the width of a literal:

**$foo[7:0] = 8'd6;**

explicitly assigns **$foo** to an 8-bit decimal ("d") value of 6. (To be clear, the "**’**" is the single-quote character.) Equivalently, we could have written:

**$foo[7:0] = 8'b110;   // 8-bit binary six**

or

**$foo[7:0] = 8'h6;     // 8-bit hexadecimal**

# Concatenation

Concatenation of bit vectors is simply the combining of two bit vectors one after the other to form a wider bit vector. 



