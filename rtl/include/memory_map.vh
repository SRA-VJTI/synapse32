`ifndef MEMORY_MAP_VH
`define MEMORY_MAP_VH

// ============================================================================
// SYNAPSE32 RISC-V CPU MEMORY MAP
// ============================================================================

// Program Memory (Instruction Memory)
// 512KB - Should be enough for most programs
`define INSTR_MEM_BASE      32'h00000000
`define INSTR_MEM_SIZE      32'h00080000  // 512KB
`define INSTR_MEM_END       32'h0007FFFF

// Machine-mode Timer (RISC-V Standard)
// Standard RISC-V timer addresses
`define TIMER_BASE          32'h02004000
`define TIMER_SIZE          32'h00008000  // 32KB region
`define TIMER_END           32'h0200BFFF

// Timer Register Offsets
`define MTIMECMP_LO         32'h02004000  // mtimecmp[31:0]
`define MTIMECMP_HI         32'h02004004  // mtimecmp[63:32]
`define MTIME_LO            32'h0200BFF8  // mtime[31:0]
`define MTIME_HI            32'h0200BFFC  // mtime[63:32]

// Data Memory 
// 1MB - Plenty for data and stack
`define DATA_MEM_BASE       32'h10000000
`define DATA_MEM_SIZE       32'h00100000  // 1MB
`define DATA_MEM_END        32'h100FFFFF

// Stack grows down from top of data memory
`define STACK_TOP           32'h100FFFFF

// Reserved regions for future peripherals
`define PERIPH_BASE         32'h20000000
`define PERIPH_SIZE         32'h10000000  // 256MB region
`define PERIPH_END          32'h2FFFFFFF

// Memory access helper macros
`define IS_INSTR_MEM(addr)  ((addr) >= `INSTR_MEM_BASE && (addr) <= `INSTR_MEM_END)
`define IS_TIMER_MEM(addr)  ((addr) >= `TIMER_BASE && (addr) <= `TIMER_END)
`define IS_DATA_MEM(addr)   ((addr) >= `DATA_MEM_BASE && (addr) <= `DATA_MEM_END)
`define IS_PERIPH_MEM(addr) ((addr) >= `PERIPH_BASE && (addr) <= `PERIPH_END)

`endif // MEMORY_MAP_VH