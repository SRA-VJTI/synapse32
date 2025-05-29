.section .nop_section, "ax"
.global _start
.type _start, @function

    nop
    nop
    nop

_start:
    la sp, _stack_top
    call main
    j .
