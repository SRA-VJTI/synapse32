MEMORY {
    MMIO      (rw)  : ORIGIN = 0x02000000, LENGTH = 0x10
    DATA_MEM  (rw)  : ORIGIN = 0x02000010, LENGTH = 16K - 0x10
    INSTR_MEM (rx)  : ORIGIN = 0x00000000, LENGTH = 16K
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
