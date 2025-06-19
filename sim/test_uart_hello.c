// Memory mapped addresses
#define UART_BASE       0x20000000
#define UART_DATA       (UART_BASE + 0x00)
#define UART_STATUS     (UART_BASE + 0x04)
#define UART_CONTROL    (UART_BASE + 0x08)
#define UART_BAUD       (UART_BASE + 0x0C)

#define DATA_MEM_BASE   0x10000000
#define CPU_DONE_ADDR   0x100000FF

// UART status bits
#define UART_STATUS_TX_EMPTY    (1 << 1)
#define UART_STATUS_TX_BUSY     (1 << 2)

// Simple register access functions
static inline void write_reg(unsigned int addr, unsigned int value) {
    *((volatile unsigned int*)addr) = value;
}

static inline unsigned int read_reg(unsigned int addr) {
    return *((volatile unsigned int*)addr);
}

// Initialize UART with 9600 baud rate
void uart_init() {
    // Set baud rate: 50MHz / 9600 = 5208
    write_reg(UART_BAUD, 5208);
    
    // Enable UART
    write_reg(UART_CONTROL, 1);
    
    // Small delay for initialization
    for (int i = 0; i < 100; i++) {
        asm volatile("nop");
    }
}

// Send a character via UART
void uart_putc(char c) {
    // Wait until not busy
    while (read_reg(UART_STATUS) & UART_STATUS_TX_BUSY) {
        // busy wait
    }
    
    // Send character
    write_reg(UART_DATA, (unsigned int)c);
}

// Send a string via UART
void uart_puts(const char* str) {
    while (*str) {
        uart_putc(*str);
        str++;
    }
}

int main() {
    // Initialize UART
    uart_init();
    
    // Send hello message
    uart_puts("Hello from RISC-V CPU!\r\n");
    uart_puts("The answer is 42.\r\n");
    
    // Signal completion
    write_reg(CPU_DONE_ADDR, 1);
    
    while (1) {
        asm volatile("nop");
    }
    
    return 0;
}
