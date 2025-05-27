ENTRY(_start)

MEMORY {
    RAM (rwx) : ORIGIN = 0x00000000, LENGTH = 16K
}

SECTIONS {
    .nop_section : {
        KEEP(*(.nop_section))  /* Ensure linker retains the NOPs */
    } > RAM

    .text : {
        *(.text*)
        *(.rodata*)
    } > RAM

    .data : {
        *(.data*)
    } > RAM

    .bss : {
        *(.bss*)
        *(COMMON)
    } > RAM
}
