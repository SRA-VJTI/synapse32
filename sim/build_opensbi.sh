#!/usr/bin/env bash
# Builds OpenSBI fw_jump for synapse32 inside the devcontainer environment.
# Usage (from repo root, after building the devcontainer image):
#   docker run --rm -v $(pwd):/workspace synapse32-dev bash /workspace/sim/build_opensbi.sh
# Or directly inside the devcontainer:
#   bash sim/build_opensbi.sh

set -euo pipefail

# OpenSBI tags this release as v1.5 rather than v1.5.0.
OPENSBI_VERSION="v1.4"
OPENSBI_DIR="/tmp/opensbi-build"
WORKSPACE="${WORKSPACE:-/workspace}"
SIM_DIR="$WORKSPACE/sim"
OUT_DIR="${SIM_OUT_DIR:-$SIM_DIR/.out/opensbi}"
OUT_ELF="$OUT_DIR/fw_jump.elf"
OUT_BIN="$OUT_DIR/fw_jump.bin"
OUT_HEX="$OUT_DIR/opensbi.hex"
DTB="$OUT_DIR/synapse32.dtb"
# OpenSBI requires a PIE-capable Linux-targeted toolchain.
CROSS_COMPILE="${CROSS_COMPILE:-riscv64-linux-gnu-}"
# Synapse32 does not implement compressed or floating-point instructions.
# OpenSBI defaults include the C extension for RV32 unless overridden.
PLATFORM_RISCV_ISA="${PLATFORM_RISCV_ISA:-rv32ima_zicsr_zifencei}"
PLATFORM_RISCV_ABI="${PLATFORM_RISCV_ABI:-ilp32}"

mkdir -p "$OUT_DIR"

# ---- compile DTB from DTS --------------------------------------------------
echo "==> Compiling device tree..."
dtc -O dtb -o "$DTB" "$SIM_DIR/synapse32.dts"
echo "    $DTB ($(wc -c < "$DTB") bytes)"

# ---- clone / update openSBI ------------------------------------------------
if [ ! -d "$OPENSBI_DIR/.git" ]; then
    echo "==> Cloning openSBI $OPENSBI_VERSION..."
    git clone --depth 1 --branch "$OPENSBI_VERSION" \
        https://github.com/riscv-software-src/opensbi.git "$OPENSBI_DIR"
else
    echo "==> openSBI already cloned at $OPENSBI_DIR"
fi

# ---- build -----------------------------------------------------------------
echo "==> Building openSBI..."
make -C "$OPENSBI_DIR" -j"$(nproc)" \
    PLATFORM=generic \
    FW_JUMP=y \
    FW_JUMP_ADDR=0x80200000 \
    FW_TEXT_START=0x80000000 \
    FW_FDT_PATH="$DTB" \
    FW_JUMP_FDT_ADDR=0x80050000 \
    PLATFORM_RISCV_XLEN=32 \
    PLATFORM_RISCV_ISA="$PLATFORM_RISCV_ISA" \
    PLATFORM_RISCV_ABI="$PLATFORM_RISCV_ABI" \
    CROSS_COMPILE="$CROSS_COMPILE"

ELF="$OPENSBI_DIR/build/platform/generic/firmware/fw_jump.elf"

# ---- copy outputs ----------------------------------------------------------
cp "$ELF" "$OUT_ELF"
echo "==> ELF: $OUT_ELF ($(wc -c < "$OUT_ELF") bytes)"

# Convert to a flat binary and then to 32-bit Verilog words.
# Synapse32 instruction RAM is a 32-bit word array, so plain objcopy -O verilog
# produces the wrong byte-oriented format for $readmemh in this design.
"${CROSS_COMPILE}objcopy" \
    --change-addresses -0x80000000 \
    -O binary \
    "$OUT_ELF" "$OUT_BIN"
echo "==> BIN: $OUT_BIN ($(wc -c < "$OUT_BIN") bytes)"

"${CROSS_COMPILE}objcopy" \
    -I binary \
    -O verilog \
    --verilog-data-width=4 \
    --reverse-bytes=4 \
    "$OUT_BIN" "$OUT_HEX"
echo "==> HEX: $OUT_HEX"

echo ""
echo "Done. Load $OUT_HEX into the simulator."
