//very simple fibonacci sequence generator
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>

#if defined(__linux__) || defined(__APPLE__)
#define HOST
#include <stdio.h>
#endif

#define N 10
static uint8_t elements[N] = {0};
// Use new memory map addresses
#define DATA_MEM_BASE 0x10000000
#define CPU_DONE_ADDR (DATA_MEM_BASE + 0xFF)      // 0x10000000
#define FIBONACCI_START_ADDR (DATA_MEM_BASE + 0x10) // 0x10000010

int main() {
    
    #ifdef HOST // for host pc
        uint8_t CPU_DONE = 0;
    #else // for the test device
        #define CPU_DONE (* (volatile uint8_t *) CPU_DONE_ADDR)
    #endif

    uint8_t a = 0;
    uint8_t b = 1;
    for (uint8_t i = 0; i < N; i++) {
        elements[i] = b;
        uint8_t next = a + b;
        a = b;
        b = next;
    }

    #ifdef HOST // for host pc
        //print elements array
        for (uint8_t i = 0; i < N; i++) {
            printf("%d ",elements[i]);
        }
        printf("\n");
        //print size of elements array
        printf("Size of elements array: %zu\n", sizeof(elements));
    #else
        uint8_t index = 0;
        //start writing elements to data memory from FIBONACCI_START_ADDR
        volatile uint8_t *mem_ptr = (volatile uint8_t *)FIBONACCI_START_ADDR;
        for (uint8_t i = 0; i < N; i++) {
            *mem_ptr = elements[index];
            mem_ptr += 0x1;
            index++;
        }
    #endif
    
    // Signal that the CPU has completed its task by setting CPU_DONE to 1.
    CPU_DONE = 1;
    
    #ifdef HOST // for host pc
        printf("N: %d = %d\n", N, CPU_DONE);
    #endif
    
    return 0;
}
