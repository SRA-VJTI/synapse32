// RISC-V factorial program to exercise all M extension instructions
#include <stdint.h>
#include <stdbool.h>

#if defined(__linux__) || defined(__APPLE__)
#define HOST
#include <stdio.h>
#endif

#define N 6  // Compute factorial of 6 (6! = 720)
#define DATA_MEM_BASE 0x10000000
#define CPU_DONE_ADDR (DATA_MEM_BASE + 0xFF)
#define FACTORIAL_ADDR (DATA_MEM_BASE + 0x20)

int main() {
#ifdef HOST
    uint32_t CPU_DONE = 0;
#else
    #define CPU_DONE (* (volatile uint8_t *) CPU_DONE_ADDR)
#endif

    uint32_t result = 1;
    uint32_t i;
    volatile int32_t sink32 = 0;
    volatile uint32_t sinku32 = 0;

    // MUL: result = result * i
    for (i = 1; i <= N; i++) {
        result = result * i;
    }

    // MULH: high 32 bits of signed * signed
    int32_t mulh_a = (int32_t)0x80000000;
    int32_t mulh_b = -2;
    int32_t mulh_res = ((int64_t)mulh_a * (int64_t)mulh_b) >> 32;
#ifdef HOST
    printf("MULH: high(0x%08x * %d) = %d\n", (uint32_t)mulh_a, mulh_b, mulh_res);
#endif
    sink32 = mulh_res;

    mulh_a = 0x7FFFFFFF;
    mulh_b = 0x7FFFFFFF;
    mulh_res = ((int64_t)mulh_a * (int64_t)mulh_b) >> 32;
#ifdef HOST
    printf("MULH: high(%d * %d) = %d\n", mulh_a, mulh_b, mulh_res);
#endif
    sink32 = mulh_res;

    // MULHSU: high 32 bits of signed * unsigned
    int32_t mulhsu_a = -1;
    uint32_t mulhsu_b = 2;
    int32_t mulhsu_res = ((int64_t)mulhsu_a * (uint64_t)mulhsu_b) >> 32;
#ifdef HOST
    printf("MULHSU: high(%d * %u) = %d\n", mulhsu_a, mulhsu_b, mulhsu_res);
#endif
    sink32 = mulhsu_res;

    mulhsu_a = 0x80000000;
    mulhsu_b = 2;
    mulhsu_res = ((int64_t)mulhsu_a * (uint64_t)mulhsu_b) >> 32;
#ifdef HOST
    printf("MULHSU: high(%d * %u) = %d\n", mulhsu_a, mulhsu_b, mulhsu_res);
#endif
    sink32 = mulhsu_res;

    // MULHU: high 32 bits of unsigned * unsigned
    uint32_t mulhu_a = 0xFFFFFFFF;
    uint32_t mulhu_b = 0xFFFFFFFF;
    uint32_t mulhu_res = ((uint64_t)mulhu_a * (uint64_t)mulhu_b) >> 32;
#ifdef HOST
    printf("MULHU: high(%u * %u) = %u\n", mulhu_a, mulhu_b, mulhu_res);
#endif
    sinku32 = mulhu_res;

    mulhu_a = 0x12345678;
    mulhu_b = 0x9ABCDEF0;
    mulhu_res = ((uint64_t)mulhu_a * (uint64_t)mulhu_b) >> 32;
#ifdef HOST
    printf("MULHU: high(%u * %u) = %u\n", mulhu_a, mulhu_b, mulhu_res);
#endif
    sinku32 = mulhu_res;

    // DIV: signed division
    int32_t div_a = -2;
    int32_t div_b = 2;
    int32_t div_res = div_a / div_b;
#ifdef HOST
    printf("DIV: %d / %d = %d\n", div_a, div_b, div_res);
#endif
    sink32 = div_res;

    div_a = 10;
    div_b = 0;
    div_res = (div_b == 0) ? -1 : div_a / div_b;
#ifdef HOST
    printf("DIV: %d / %d = %d\n", div_a, div_b, div_res);
#endif
    sink32 = div_res;

    // DIVU: unsigned division
    uint32_t divu_a = 10;
    uint32_t divu_b = 2;
    uint32_t divu_res = divu_a / divu_b;
#ifdef HOST
    printf("DIVU: %u / %u = %u\n", divu_a, divu_b, divu_res);
#endif
    sinku32 = divu_res;

    divu_a = 10;
    divu_b = 0;
    divu_res = (divu_b == 0) ? 0xFFFFFFFF : divu_a / divu_b;
#ifdef HOST
    printf("DIVU: %u / %u = %u\n", divu_a, divu_b, divu_res);
#endif
    sinku32 = divu_res;

    // REM: signed remainder
    int32_t rem_a = -2;
    int32_t rem_b = 3;
    int32_t rem_res = rem_a % rem_b;
#ifdef HOST
    printf("REM: %d %% %d = %d\n", rem_a, rem_b, rem_res);
#endif
    sink32 = rem_res;

    rem_a = 10;
    rem_b = 0;
    rem_res = (rem_b == 0) ? rem_a : rem_a % rem_b;
#ifdef HOST
    printf("REM: %d %% %d = %d\n", rem_a, rem_b, rem_res);
#endif
    sink32 = rem_res;

    // REMU: unsigned remainder
    uint32_t remu_a = 10;
    uint32_t remu_b = 3;
    uint32_t remu_res = remu_a % remu_b;
#ifdef HOST
    printf("REMU: %u %% %u = %u\n", remu_a, remu_b, remu_res);
#endif
    sinku32 = remu_res;

    remu_a = 10;
    remu_b = 0;
    remu_res = (remu_b == 0) ? remu_a : remu_a % remu_b;
#ifdef HOST
    printf("REMU: %u %% %u = %u\n", remu_a, remu_b, remu_res);
#endif
    sinku32 = remu_res;

#ifdef HOST
    printf("Factorial(%d) = %u\n", N, result);
#else
    // Store result to memory
    volatile uint32_t *mem_ptr = (volatile uint32_t *)FACTORIAL_ADDR;
    *mem_ptr = result;
#endif

    CPU_DONE = 1;
    return 0;
}
