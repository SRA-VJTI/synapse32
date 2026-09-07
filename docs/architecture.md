## Synapse-32 Architecture

5-stage in-order RISC-V pipeline (RV32IMA + Zicsr + Zifencei + Zihintpause, with machine/supervisor traps and interrupts) with a unified instruction/data RAM, MMIO timer + UART + PLIC, a 1-entry store buffer with store→load byte-merge, and an atomic LSU for LR/SC and AMO.* operations.

### Full system

```mermaid
flowchart TB
    classDef stage fill:#1e293b,stroke:#94a3b8,color:#e2e8f0
    classDef ctrl  fill:#3b0764,stroke:#a78bfa,color:#f5f3ff
    classDef mem   fill:#064e3b,stroke:#34d399,color:#ecfdf5
    classDef mmio  fill:#7c2d12,stroke:#fb923c,color:#fff7ed
    classDef reg   fill:#0c4a6e,stroke:#38bdf8,color:#f0f9ff

    %% ===== IF =====
    subgraph IF["IF — Fetch"]
        PC[pc]:::stage
        IFID[/IF_ID/]:::reg
    end

    %% ===== ID =====
    subgraph ID["ID — Decode"]
        DEC[decoder]:::stage
        RF[registerfile]:::stage
        LUD[load_use_detector]:::ctrl
        IDEX[/ID_EX/]:::reg
    end

    %% ===== EX =====
    subgraph EX["EX — Execute"]
        FWD[forwarding_unit]:::ctrl
        EXU[execution_unit\n• ALU\n• Branch/Jump\n• CSR ops\n• Trap/MRET/WFI]:::stage
        EXMEM[/EX_MEM/]:::reg
    end

    %% ===== MEM =====
    subgraph MEM["MEM — Memory / Atomics"]
        MU[memory_unit\nload/store sizing + BE]:::stage
        ALSU[atomic_lsu\nLR/SC reservation\nAMO.* RMW ALU]:::stage
        SB[(1-entry store buffer\naddr/data/be/valid)]:::mem
        MERGE[store→load\nbyte merge]:::mem
        ARB[mem-port arbiter\nwr_en / rd_en / addr]:::ctrl
        MEMWB[/MEM_WB/]:::reg
    end

    %% ===== WB =====
    subgraph WB["WB — Writeback"]
        WBU[writeback\nALU vs mem mux + sc_result]:::stage
    end

    %% ===== CSR / Interrupts =====
    subgraph SYS["System / Interrupts"]
        CSR[csr_file\nmstatus mie mip\nmtvec mepc mcause]:::ctrl
        INTC[interrupt_controller]:::ctrl
    end

    %% ===== SoC fabric =====
    subgraph SOC["SoC bus (top.v)"]
        DECMAP[address decode\nmemory_map.vh]:::ctrl
        RMUX[read-data mux]:::ctrl
        UMEM[(unified_mem\ndual-port\ninstr port + data port)]:::mem
        TIMER[timer\nmtime / mtimecmp]:::mmio
        UART[uart\nTX/RX]:::mmio
        PLIC[plic]:::mmio
        IRQ_OR[external IRQ OR]:::ctrl
        EXT_IRQ[external_interrupt input]:::ctrl
    end

    %% --- IF flow ---
    PC -- pc --> UMEM
    UMEM -- instr --> IFID
    IFID --> DEC

    %% --- ID flow ---
    DEC --> RF
    DEC --> IDEX
    RF  --> IDEX
    DEC --> LUD
    LUD -. hazard_stall .-> PC
    LUD -. hazard_stall .-> IFID
    LUD -. hazard_stall .-> IDEX

    %% --- EX flow ---
    IDEX --> EXU
    FWD  -. forward_a/b .-> EXU
    EXMEM -- ex_mem_result --> FWD
    MEMWB -- wb_result    --> FWD
    EXU --> EXMEM
    EXU -. jump_signal/addr .-> PC
    EXU -. flush_pipeline   .-> IFID
    EXU -. flush_pipeline   .-> IDEX
    EXU <-->|csr r/w| CSR
    INTC -. interrupt_pending/cause/pc .-> EXU
    CSR  -- mstatus/mie/mip --> INTC

    %% --- MEM flow ---
    EXMEM --> MU
    EXMEM --> ALSU
    MU   --> ARB
    ALSU --> ARB
    MU   -- store data/be/addr --> SB
    SB   -. bypass bytes .-> MERGE
    ARB  -- module_mem_wr_en/rd_en\nmodule_write_addr/data/be\nmodule_read_addr --> DECMAP
    RMUX -- module_read_data_in --> MERGE
    MERGE -- mem_read_data_effective --> ALSU
    MERGE -- mem_read_data_effective --> MEMWB
    EXMEM -- exec_output (or sc_result) --> MEMWB

    %% --- WB flow ---
    MEMWB --> WBU
    WBU   -- rd / value / wr_en --> RF

    %% --- SoC fabric ---
    DECMAP -- ram region  --> UMEM
    DECMAP -- timer region --> TIMER
    DECMAP -- uart region --> UART
    DECMAP -- plic region --> PLIC
    UMEM  -- read --> RMUX
    TIMER -- read --> RMUX
    UART  -- read --> RMUX
    PLIC  -- plic_read_data --> RMUX
    UART -. uart_interrupt .-> PLIC
    PLIC -. plic_interrupt .-> IRQ_OR
    EXT_IRQ --> IRQ_OR
    IRQ_OR -. external_interrupt_combined .-> INTC
    IRQ_OR -. external_interrupt_combined .-> CSR
    TIMER -. timer_interrupt .-> INTC
```

### Memory map (`rtl/include/memory_map.vh`)

```mermaid
flowchart LR
    A["0x8000_0000 – 0x83FF_FFFF<br/>Instruction RAM (64 MB)"]:::mem
    B["0x1000_0000 – 0x100F_FFFF<br/>Data RAM (1 MB)"]:::mem
    C["0x0200_4000 – 0x0200_BFFF<br/>Timer (mtime, mtimecmp)"]:::mmio
    D["0x2000_0000 – 0x2000_0FFF<br/>UART"]:::mmio
    E["0x0C00_0000 – 0x0C3F_FFFF<br/>PLIC"]:::mmio
    classDef mem  fill:#064e3b,stroke:#34d399,color:#ecfdf5
    classDef mmio fill:#7c2d12,stroke:#fb923c,color:#fff7ed
```

Both RAM regions are backed by a single `unified_mem`, instantiated in `rtl/top.v` with `MEM_SIZE(17039360)`: 17,039,360 × 32-bit words, or 64 MB of instruction RAM plus 1 MB of data RAM. The instruction port serves fetches; the data port serves loads/stores after address translation. `rtl/mmu/unified_mem.v` maps the instruction region to local byte offsets `[0 .. INSTR_MEM_SIZE-1]` and the data region to `[INSTR_MEM_SIZE .. INSTR_MEM_SIZE+DATA_MEM_SIZE-1]`. Dividing these byte offsets by four gives instruction word indices `0..16,777,215` and data word indices `16,777,216..17,039,359`.

### Memory-port arbitration (MEM stage)

```mermaid
flowchart LR
    classDef ctrl fill:#3b0764,stroke:#a78bfa,color:#f5f3ff
    classDef mem  fill:#064e3b,stroke:#34d399,color:#ecfdf5

    REQ{request type}:::ctrl
    REQ -- "AMO/SC write\n(atomic_write_enable)" --> DIRW[direct write\naddr = mem_addr\ndata = atomic_new_word / rs2\nbe = 1111]:::mem
    REQ -- "MMIO store\n(direct_req)" --> DIRS[direct write\nbypass store buffer]:::mem
    REQ -- "RAM store" --> CAP[capture into\n1-entry store buffer]:::mem
    REQ -- "load / LR / AMO read" --> COVER{store-buffer\ncovers all bytes?}:::ctrl
    COVER -- yes --> BYP[bypass-only,\nno mem read]:::mem
    COVER -- no  --> RD[module_mem_rd_en = 1\nthen byte-merge with SB]:::mem
    CAP -.->|when port idle| COMMIT[store_buf_commit_fire\n→ module_mem_wr_en]:::mem
```

A standard RAM store is parked in the 1-entry store buffer for one cycle and committed when the memory port isn't otherwise busy. AMO/SC writes and MMIO stores are driven directly. Loads (and LR/AMO reads) check the store buffer per byte; if all required bytes are covered they're served from the buffer, otherwise the memory read happens and pending bytes are merged on top.

### Notes on the atomic path
- `atomic_lsu` (`rtl/core_modules/atomic_lsu.v`) holds the LR reservation (`lr_valid`, `lr_addr`) and computes the AMO read-modify-write value combinationally from `mem_read_data_effective` and `rs2`.
- The reservation is killed by any `SC.W`, any `AMO.*`, or by another store hitting `lr_addr`.
- `SC.W` writes `0` (success) or `1` (failure) into `rd` via `sc_result`, which is muxed into the `MEM_WB` `exec_output` field.

### File map
| Block | File |
| --- | --- |
| Top SoC | `rtl/top.v` |
| CPU core | `rtl/riscv_cpu.v` |
| Pipeline regs | `rtl/pipeline_stages/{IF_ID,ID_EX,EX_MEM,MEM_WB}.v` |
| Hazard / forwarding | `rtl/pipeline_stages/{load_use_detector,forwarding_unit,store_load_detector}.v` |
| ALU / decode / RF / PC | `rtl/core_modules/{alu,decoder,registerfile,pc}.v` |
| Execute wrapper | `rtl/execution_unit.v` |
| LSU | `rtl/memory_unit.v`, `rtl/core_modules/atomic_lsu.v` |
| Writeback | `rtl/writeback.v` |
| CSR / IRQ | `rtl/core_modules/{csr_file,csr_exec,interrupt_controller}.v` |
| MMIO | `rtl/core_modules/{timer,uart,plic}.v` |
| Memory | `rtl/mmu/unified_mem.v` (17,039,360 × 32-bit words) |
| Address map | `rtl/include/memory_map.vh` |
