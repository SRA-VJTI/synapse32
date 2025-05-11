//very simple fibonacci sequence generator
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>

#if defined(__linux__) || defined(__APPLE__)
#define HOST
#include <stdio.h>
#endif

#define N 10

int main() {

    uint8_t elements[N] = {0};
    #ifdef HOST // for host pc
        uint8_t final_location = 0;
        uint8_t CPU_DONE = 0;
    #else // for the test device
        #define final_location (* (volatile uint8_t * ) 0x02000004)
        #define CPU_DONE (* (volatile uint8_t * ) 0x0200000c)
    #endif

    uint8_t k = 0;
    for (uint8_t j = 0; j < N/10; j++){
        uint8_t a = 0;
        uint8_t b = 1;
        uint8_t c = 0;
        for (uint8_t i = 0; i < 10; i++) {
            c = a + b;
            a = b;
            b = c;
            elements[k] = a;
            k++;
        }
    }

    #ifdef HOST // for host pc
        //print elements array
        for (uint8_t i = 0; i < N; i++) {
            printf("%d",elements[i]);
        }
        printf("\n");
        //print size of elements array
        printf("Size of elements array: ");
        printf("%d", k);
        printf("\n");
    #else
        uint8_t index = 0;
        //start writing elements to memory from 0x02000010
        uint8_t *mem_ptr = (uint8_t *) 0x02000010;
        for (uint8_t i = 0; i < N; i++) {
            *mem_ptr = elements[index];
            mem_ptr+=0x1;
            index++;
        }
    #endif
    // Signal that the CPU has completed its task by setting CPU_DONE to 1.
    CPU_DONE = 1;
    #ifdef HOST // for host pc
        printf("N: ");
        printf("%d", N);
        printf(" = ");
        printf("%d", CPU_DONE);
        printf("\n");
    #endif
    return 0;
}
