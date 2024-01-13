//very simple fibonacci sequence generator

#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>

#if defined(__linux__) || defined(__APPLE__) // for host pc

    #include <stdio.h>

    void _put_byte(char c) { putchar(c); }

    void _put_str(char *str) {
        while (*str) {
            _put_byte(*str++);
        }
    }

    void print_output(uint8_t num) {
        if (num == 0) {
            putchar('0'); // if the number is 0, directly print '0'
            _put_byte('\n');
            return;
        }

        if (num < 0) {
            putchar('-'); // print the negative sign for negative numbers
            num = -num;   // make the number positive for easier processing
        }

        // convert the integer to a string
        char buffer[20]; // assuming a 32-bit integer, the maximum number of digits is 10 (plus sign and null terminator)
        uint8_t index = 0;

        while (num > 0) {
            buffer[index++] = '0' + num % 10; // convert the last digit to its character representation
            num /= 10;                        // move to the next digit
        }

        // print the characters in reverse order (from right to left)
        while (index > 0) { putchar(buffer[--index]); }
        _put_byte('\n');
    }

    void _put_value(uint8_t val) { print_output(val); }

#else  // for the test device

    void _put_value(uint8_t val) { }
    void _put_str(char *str) { }

#endif

int main() {

    const uint8_t n = 150;

    uint8_t elements[150] = {0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0};

    #if defined(__linux__) || defined(__APPLE__) // for host pc

        uint8_t final_location = 0;
        uint8_t CPU_DONE = 0;
    #else // for the test device

        #define final_location (* (volatile uint8_t * ) 0x02000004)
        #define CPU_DONE (* (volatile uint8_t * ) 0x0200000c)
        
    #endif
    uint8_t k = 0;
    for (uint8_t j = 0; j < 15; j++){
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

    #if defined(__linux__) || defined(__APPLE__) // for host pc

        //print elements array
        for (uint8_t i = 0; i < n; i++) {
            _put_value(elements[i]);
        }
        _put_byte('\n');
        //print size of elements array
        _put_str("Size of elements array: ");
        _put_value(k);
        _put_byte('\n');

    #else
        uint8_t index = 0;
        //start writing elements to memory from 0x02000010
        uint8_t *mem_ptr = (uint8_t *) 0x02000010;
        for (uint8_t i = 0; i < n; i++) {
            *mem_ptr = elements[index];
            mem_ptr+=0x1;
            index++;
        }
    #endif
    CPU_DONE = elements[n - 1];
    #if defined(__linux__) || defined(__APPLE__) // for host pc
        _put_str("N: ");
        _put_value(n);
        _put_str(" = ");
        _put_value(CPU_DONE);
        _put_byte('\n');
    #endif

    return 0;
}