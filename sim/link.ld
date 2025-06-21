MEMORY {
    INSTR_MEM (rx)  : ORIGIN = 0x00000000, LENGTH = 512K
    DATA_MEM  (rw)  : ORIGIN = 0x10000000, LENGTH = 1M
}

_stack_top = ORIGIN(DATA_MEM) + LENGTH(DATA_MEM);

SECTIONS {
    .nop_section : {
        KEEP(*(.nop_section))
    } > INSTR_MEM

    .text : {
        *(.text*)
        *(.rodata*)
    } > INSTR_MEM

    .data : {
        *(.data*)
    } > DATA_MEM

    .bss : {
        *(.bss*)
        *(COMMON)
    } > DATA_MEM
}
