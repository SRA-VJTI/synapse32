.section .nop_section, "ax"
.global _start
.type _start, @function

    nop
    nop
    nop

_start:
    call main
    j .
