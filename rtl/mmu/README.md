MMU-specific RTL lives here.

Current contents:
- `sv32_mmu.v`: top-level Sv32 translation and fault/update wiring
- `sv32_page_walker.v`: leaf-PTE resolution for Sv32 walks
- `sv32_instr_check.v`: instruction-side permission and accessed-bit checks
- `sv32_data_check.v`: data-side permission and accessed/dirty-bit checks
- `unified_mem.v`: unified physical backing RAM plus page-table read/write side ports

Keep future MMU/TLB/page-walker modules in this directory so virtual-memory work stays isolated from the rest of the core.
