# Bare-metal machine-mode timer interrupt demo.
#
# Flow:
#   1. Install trap_handler in mtvec.
#   2. Program mtimecmp to fire after TIMER_TIMEOUT ticks.
#   3. Enable MTIE (mie[7]) and global MIE (mstatus[3]).
#   4. Poll HANDLER_MARKER until the handler writes the sentinel.
#   5. Signal CPU_DONE and spin.
#
# The handler writes the sentinel + increments a counter, then pushes
# mtimecmp to its max to prevent re-firing, and returns via mret.

.equ HANDLER_MARKER,  0x10000000
.equ HANDLER_COUNT,   0x10000004
.equ CPU_DONE_ADDR,   0x100000FF
.equ SENTINEL,        0xDEADBEEF

.equ MTIMECMP_LO,     0x02004000
.equ MTIMECMP_HI,     0x02004004

.equ TIMER_TIMEOUT,   100

    .section .text
    .global main
    .type main, @function
main:
    # Clear state so the poll below sees a real handler write.
    li    t0, HANDLER_MARKER
    sw    zero, 0(t0)
    li    t0, HANDLER_COUNT
    sw    zero, 0(t0)

    # Install trap vector (direct mode, low 2 bits of mtvec = 0).
    la    t0, trap_handler
    csrw  mtvec, t0

    # Program mtimecmp. Write HI=all-ones first so the 64-bit compare
    # can't transiently match while we're mid-update.
    li    t0, MTIMECMP_HI
    li    t1, -1
    sw    t1, 0(t0)
    li    t0, MTIMECMP_LO
    li    t1, TIMER_TIMEOUT
    sw    t1, 0(t0)
    li    t0, MTIMECMP_HI
    sw    zero, 0(t0)

    # Enable machine timer interrupt, then global interrupts.
    li    t0, (1 << 7)
    csrs  mie, t0
    li    t0, (1 << 3)
    csrs  mstatus, t0

    # Wait for the handler to publish the sentinel.
    li    t0, HANDLER_MARKER
    li    t1, SENTINEL
wait_loop:
    lw    t2, 0(t0)
    bne   t2, t1, wait_loop

    # Handler ran - tell the testbench we're done.
    li    t0, CPU_DONE_ADDR
    li    t1, 1
    sb    t1, 0(t0)

hang:
    j     hang

    .align 2
    .global trap_handler
    .type trap_handler, @function
trap_handler:
    addi  sp, sp, -8
    sw    t0, 0(sp)
    sw    t1, 4(sp)

    # Publish sentinel.
    li    t0, HANDLER_MARKER
    li    t1, SENTINEL
    sw    t1, 0(t0)

    # Bump call count.
    li    t0, HANDLER_COUNT
    lw    t1, 0(t0)
    addi  t1, t1, 1
    sw    t1, 0(t0)

    # Disarm the timer: push mtimecmp to its 64-bit max.
    li    t0, MTIMECMP_HI
    li    t1, -1
    sw    t1, 0(t0)
    li    t0, MTIMECMP_LO
    sw    t1, 0(t0)

    lw    t0, 0(sp)
    lw    t1, 4(sp)
    addi  sp, sp, 8
    mret
