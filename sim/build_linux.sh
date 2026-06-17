#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
LINUX_REPO="${LINUX_REPO:-https://github.com/gregkh/linux.git}"
LINUX_VERSION="${LINUX_VERSION:-v6.6.32}"
OPENSBI_VERSION="${OPENSBI_VERSION:-v1.4}"
LINUX_DIR="${LINUX_DIR:-/tmp/synapse32-linux}"
OPENSBI_REPO="${OPENSBI_REPO:-https://github.com/riscv-software-src/opensbi.git}"
OPENSBI_DIR="${OPENSBI_DIR:-/tmp/opensbi-build}"
BUSYBOX_REPO="${BUSYBOX_REPO:-https://github.com/mirror/busybox.git}"
BUSYBOX_VERSION="${BUSYBOX_VERSION:-1_36_1}"
BUSYBOX_DIR="${BUSYBOX_DIR:-/tmp/busybox-build}"
LINUX_OUT_DIR="${LINUX_OUT_DIR:-$script_dir/.out/linux}"
ROOTFS_DIR="$LINUX_OUT_DIR/rootfs"
CONFIG_FRAGMENT="$LINUX_OUT_DIR/synapse32.config"
CONFIG_FORCE_OFF_FRAGMENT="$LINUX_OUT_DIR/synapse32-force-off.config"
DTB="$LINUX_OUT_DIR/synapse32.dtb"
LINUX_IMAGE="$LINUX_OUT_DIR/Image"
LINUX_VMLINUX="$LINUX_OUT_DIR/vmlinux"
LINUX_SYSTEM_MAP="$LINUX_OUT_DIR/System.map"
LINUX_ELF="$LINUX_OUT_DIR/fw_payload.elf"
LINUX_BIN="$LINUX_OUT_DIR/fw_payload.bin"
LINUX_HEX="$LINUX_OUT_DIR/synapse32.hex"
INIT_SRC="$LINUX_OUT_DIR/init.c"
INIT_BIN="$ROOTFS_DIR/init"
BUSYBOX_OUT_DIR="${BUSYBOX_OUT_DIR:-$LINUX_OUT_DIR/busybox-build}"
BUSYBOX_CONFIG="$BUSYBOX_OUT_DIR/.config"
BUSYBOX_BIN="$ROOTFS_DIR/bin/busybox"
INITRAMFS_LIST="$LINUX_OUT_DIR/initramfs.list"
INITRAMFS_CPIO="$LINUX_OUT_DIR/initramfs.cpio"
GEN_INIT_CPIO_BIN="$LINUX_OUT_DIR/gen_init_cpio"

KERNEL_CROSS_COMPILE="${KERNEL_CROSS_COMPILE:-riscv32-unknown-linux-gnu-}"
OPENSBI_CROSS_COMPILE="${OPENSBI_CROSS_COMPILE:-riscv64-linux-gnu-}"
PLATFORM_RISCV_ISA="${PLATFORM_RISCV_ISA:-rv32ima_zicsr_zifencei_zihintpause}"
PLATFORM_RISCV_ABI="${PLATFORM_RISCV_ABI:-ilp32}"
KERNEL_MARCH="${KERNEL_MARCH:-rv32ima_zicsr_zifencei_zihintpause}"
KERNEL_MABI="${KERNEL_MABI:-ilp32}"

num_jobs() {
    if command -v nproc >/dev/null 2>&1; then
        nproc
        return
    fi
    if command -v getconf >/dev/null 2>&1; then
        getconf _NPROCESSORS_ONLN
        return
    fi
    if command -v sysctl >/dev/null 2>&1; then
        sysctl -n hw.ncpu
        return
    fi
    echo 4
}

require_tool() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "Missing required tool: $1" >&2
        exit 1
    fi
}

set_kconfig_bool() {
    local config_file="$1"
    local symbol="$2"
    local value="$3"

    if grep -q "^${symbol}=" "$config_file"; then
        sed -i "s/^${symbol}=.*/${symbol}=${value}/" "$config_file"
        return
    fi
    if grep -q "^# ${symbol} is not set" "$config_file"; then
        sed -i "s/^# ${symbol} is not set$/${symbol}=${value}/" "$config_file"
        return
    fi
    printf '%s=%s\n' "$symbol" "$value" >> "$config_file"
}

set_kconfig_disabled() {
    local config_file="$1"
    local symbol="$2"

    if grep -q "^${symbol}=" "$config_file"; then
        sed -i "s/^${symbol}=.*/# ${symbol} is not set/" "$config_file"
        return
    fi
    if ! grep -q "^# ${symbol} is not set" "$config_file"; then
        printf '# %s is not set\n' "$symbol" >> "$config_file"
    fi
}

set_kconfig_string() {
    local config_file="$1"
    local symbol="$2"
    local value="$3"

    if grep -q "^${symbol}=" "$config_file"; then
        sed -i "s|^${symbol}=.*|${symbol}=\"${value}\"|" "$config_file"
        return
    fi
    if grep -q "^# ${symbol} is not set" "$config_file"; then
        sed -i "s|^# ${symbol} is not set$|${symbol}=\"${value}\"|" "$config_file"
        return
    fi
    printf '%s="%s"\n' "$symbol" "$value" >> "$config_file"
}

write_config_bool() {
    local config_file="$1"
    local symbol="$2"
    local value="$3"
    printf '%s=%s\n' "$symbol" "$value" >> "$config_file"
}

write_config_disabled() {
    local config_file="$1"
    local symbol="$2"
    printf '# %s is not set\n' "$symbol" >> "$config_file"
}

write_config_string() {
    local config_file="$1"
    local symbol="$2"
    local value="$3"
    printf '%s="%s"\n' "$symbol" "$value" >> "$config_file"
}

apply_disable_list() {
    local config_file="$1"
    shift
    local symbol

    for symbol in "$@"; do
        set_kconfig_disabled "$config_file" "$symbol"
    done
}

clone_or_update() {
    local repo_url="$1"
    local git_ref="$2"
    local dest="$3"

    if [ ! -d "$dest/.git" ]; then
        echo "==> Cloning $(basename "$dest") @ $git_ref..."
        git clone --depth 1 --branch "$git_ref" "$repo_url" "$dest"
        return
    fi

    echo "==> Reusing existing checkout at $dest"
}

patch_linux_source() {
    local vdso_processor="$LINUX_DIR/arch/riscv/include/asm/vdso/processor.h"

    if [ -f "$vdso_processor" ]; then
        perl -0pi -e 's/__asm__ __volatile__ \("pause"\);/__asm__ __volatile__ \(".4byte 0x100000F"\);/' "$vdso_processor"
    fi
}

pick_linux_defconfig() {
    if [ -f "$LINUX_DIR/arch/riscv/configs/rv32_defconfig" ]; then
        echo "rv32_defconfig"
        return
    fi
    echo "defconfig"
}

mkdir -p "$LINUX_OUT_DIR"

require_tool dtc
require_tool git
require_tool make
require_tool cc
require_tool gzip
require_tool "${KERNEL_CROSS_COMPILE}gcc"
require_tool "${KERNEL_CROSS_COMPILE}objcopy"
require_tool "${OPENSBI_CROSS_COMPILE}gcc"
require_tool "${OPENSBI_CROSS_COMPILE}objcopy"

echo "==> Compiling device tree..."
dtc -O dtb -o "$DTB" "$script_dir/synapse32.dts"

clone_or_update "$LINUX_REPO" "$LINUX_VERSION" "$LINUX_DIR"
clone_or_update "$OPENSBI_REPO" "$OPENSBI_VERSION" "$OPENSBI_DIR"
clone_or_update "$BUSYBOX_REPO" "$BUSYBOX_VERSION" "$BUSYBOX_DIR"
patch_linux_source

echo "==> Preparing initramfs root..."
rm -rf "$ROOTFS_DIR"
mkdir -p "$ROOTFS_DIR"/{bin,dev,proc,sys,tmp}

echo "==> Building BusyBox userspace..."
rm -rf "$BUSYBOX_OUT_DIR"
mkdir -p "$BUSYBOX_OUT_DIR"
make -C "$BUSYBOX_DIR" ARCH=riscv CROSS_COMPILE="$KERNEL_CROSS_COMPILE" distclean
(
    set +o pipefail
    yes "" | make -C "$BUSYBOX_DIR" O="$BUSYBOX_OUT_DIR" ARCH=riscv CROSS_COMPILE="$KERNEL_CROSS_COMPILE" defconfig >/dev/null
)
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_STATIC y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_INIT y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_FEATURE_USE_INITTAB y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_CTTYHACK y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_FEATURE_PREFER_APPLETS y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_FEATURE_EDITING y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_FEATURE_TAB_COMPLETION y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_FEATURE_SH_STANDALONE y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_LS y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_MOUNT y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_PS y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_SETSID y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_UNAME y
set_kconfig_bool "$BUSYBOX_CONFIG" CONFIG_STTY y
set_kconfig_disabled "$BUSYBOX_CONFIG" CONFIG_TC
set_kconfig_disabled "$BUSYBOX_CONFIG" CONFIG_IP
set_kconfig_disabled "$BUSYBOX_CONFIG" CONFIG_IFCONFIG
set_kconfig_disabled "$BUSYBOX_CONFIG" CONFIG_ROUTE
make -C "$BUSYBOX_DIR" O="$BUSYBOX_OUT_DIR" -j"$(num_jobs)" ARCH=riscv CROSS_COMPILE="$KERNEL_CROSS_COMPILE" busybox
cp "$BUSYBOX_OUT_DIR/busybox" "$BUSYBOX_BIN"
chmod 0755 "$BUSYBOX_BIN"

cat > "$INIT_SRC" <<'EOF'
#include <asm/unistd.h>

#define AT_FDCWD -100
#define O_RDWR 02
#define O_CLOEXEC 02000000

static inline long syscall0(long nr)
{
    register long a0 asm("a0");
    register long a7 asm("a7") = nr;

    asm volatile("ecall" : "=r"(a0) : "r"(a7) : "memory");
    return a0;
}

static inline long syscall1(long nr, long arg0)
{
    register long a0 asm("a0") = arg0;
    register long a7 asm("a7") = nr;

    asm volatile("ecall" : "+r"(a0) : "r"(a7) : "memory");
    return a0;
}

static inline long syscall2(long nr, long arg0, long arg1)
{
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a7 asm("a7") = nr;

    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a7)
                 : "memory");
    return a0;
}

static inline long syscall3(long nr, long arg0, long arg1, long arg2)
{
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a7 asm("a7") = nr;

    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a2), "r"(a7)
                 : "memory");
    return a0;
}

static inline long syscall4(long nr, long arg0, long arg1, long arg2, long arg3)
{
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a3 asm("a3") = arg3;
    register long a7 asm("a7") = nr;

    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a2), "r"(a3), "r"(a7)
                 : "memory");
    return a0;
}

static inline long syscall5(long nr, long arg0, long arg1, long arg2, long arg3, long arg4)
{
    register long a0 asm("a0") = arg0;
    register long a1 asm("a1") = arg1;
    register long a2 asm("a2") = arg2;
    register long a3 asm("a3") = arg3;
    register long a4 asm("a4") = arg4;
    register long a7 asm("a7") = nr;

    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a1), "r"(a2), "r"(a3), "r"(a4), "r"(a7)
                 : "memory");
    return a0;
}

static unsigned long str_len(const char *text)
{
    unsigned long len = 0;

    while (text[len] != '\0') {
        len++;
    }
    return len;
}

static void write_all(long fd, const char *text, unsigned long len)
{
    while (len > 0) {
        unsigned long chunk = len;
        if (chunk > 8) {
            chunk = 8;
        }
        long written = syscall3(__NR_write, fd, (long)text, chunk);
        if (written <= 0) {
            return;
        }
        text += written;
        len -= (unsigned long)written;
    }
}

static void write_str(long fd, const char *text)
{
    write_all(fd, text, str_len(text));
}

static void ensure_console(void)
{
    long fd = syscall4(__NR_openat, AT_FDCWD, (long)"/dev/console", O_RDWR | O_CLOEXEC, 0);
    if (fd < 0) {
        return;
    }

    if (fd != 0) {
        syscall3(__NR_dup3, fd, 0, 0);
    }
    if (fd != 1) {
        syscall3(__NR_dup3, fd, 1, 0);
    }
    if (fd != 2) {
        syscall3(__NR_dup3, fd, 2, 0);
    }
    if (fd > 2) {
        syscall1(__NR_close, fd);
    }
}

static void maybe_mount(const char *source, const char *target, const char *fstype)
{
    syscall5(__NR_mount, (long)source, (long)target, (long)fstype, 0, 0);
}

void _start(void)
{
    static char *const init_argv[] = { "init", 0 };
    static char *const init_envp[] = {
        "HOME=/",
        "TERM=linux",
        "PATH=/bin:/sbin",
        0,
    };

    ensure_console();
    maybe_mount("proc", "/proc", "proc");
    maybe_mount("sysfs", "/sys", "sysfs");

    write_str(1, "\n");
    write_str(1, "Synapse32 Linux userspace is up.\n");
    write_str(1, "uname: Linux synapse32\n");
    write_str(1, "Launching /sbin/init...\n");

    syscall3(__NR_execve, (long)"/sbin/init", (long)init_argv, (long)init_envp);
    write_str(2, "execve /sbin/init failed\n");

    for (;;) {
        syscall0(__NR_sched_yield);
    }
}
EOF
"${KERNEL_CROSS_COMPILE}gcc" \
    -nostdlib \
    -static \
    -Os \
    -s \
    -ffreestanding \
    -fno-stack-protector \
    -fdata-sections \
    -ffunction-sections \
    -Wl,--gc-sections \
    -Wl,--build-id=none \
    -Wl,-e,_start \
    -march="${KERNEL_MARCH}" \
    -mabi=ilp32 \
    "$INIT_SRC" \
    -o "$INIT_BIN"
chmod 0755 "$INIT_BIN"

mkdir -p "$ROOTFS_DIR/etc"
cat > "$ROOTFS_DIR/etc/inittab" <<'EOF'
ttyS0::respawn:/bin/cttyhack /bin/sh
::ctrlaltdel:/bin/echo "Ctrl-Alt-Del pressed"
::shutdown:/bin/echo "Shutting down"
EOF

if [ ! -e "$ROOTFS_DIR/dev/console" ]; then
    mknod -m 600 "$ROOTFS_DIR/dev/console" c 5 1 2>/dev/null || true
fi
if [ ! -e "$ROOTFS_DIR/dev/null" ]; then
    mknod -m 666 "$ROOTFS_DIR/dev/null" c 1 3 2>/dev/null || true
fi
if [ ! -e "$ROOTFS_DIR/dev/ttyS0" ]; then
    mknod -m 600 "$ROOTFS_DIR/dev/ttyS0" c 4 64 2>/dev/null || true
fi

cat > "$INITRAMFS_LIST" <<EOF
dir /bin 0755 0 0
dir /sbin 0755 0 0
dir /etc 0755 0 0
file /bin/busybox $BUSYBOX_BIN 0755 0 0
slink /bin/cttyhack busybox 0777 0 0
slink /bin/setsid busybox 0777 0 0
slink /bin/sh busybox 0777 0 0
slink /bin/cat busybox 0777 0 0
slink /bin/clear busybox 0777 0 0
slink /bin/dmesg busybox 0777 0 0
slink /bin/echo busybox 0777 0 0
slink /bin/ls busybox 0777 0 0
slink /bin/mkdir busybox 0777 0 0
slink /bin/mount busybox 0777 0 0
slink /bin/ps busybox 0777 0 0
slink /bin/stty busybox 0777 0 0
slink /bin/uname busybox 0777 0 0
slink /sbin/init ../bin/busybox 0777 0 0
file /etc/inittab $ROOTFS_DIR/etc/inittab 0644 0 0
dir /dev 0755 0 0
nod /dev/console 0600 0 0 c 5 1
nod /dev/null 0666 0 0 c 1 3
nod /dev/ttyS0 0600 0 0 c 4 64
dir /proc 0755 0 0
dir /sys 0755 0 0
dir /tmp 1777 0 0
file /init $INIT_BIN 0755 0 0
EOF

common_disable_symbols=(
    CONFIG_EFI
    CONFIG_EFI_STUB
    CONFIG_MODULES
    CONFIG_HZ_250
    CONFIG_HZ_300
    CONFIG_HZ_1000
    CONFIG_SMP
    CONFIG_NUMA
    CONFIG_FPU
    CONFIG_BPF
    CONFIG_BPF_SYSCALL
    CONFIG_CGROUPS
    CONFIG_CGROUP_PERF
    CONFIG_FUTEX_PI
    CONFIG_KALLSYMS
    CONFIG_PROFILING
    CONFIG_PERF_EVENTS
    CONFIG_DEBUG_KERNEL
    CONFIG_DEBUG_MISC
    CONFIG_DEBUG_LIST
    CONFIG_DEBUG_PLIST
    CONFIG_DEBUG_VM_PGTABLE
    CONFIG_DEBUG_FS
    CONFIG_TEST_KSTRTOX
    CONFIG_TEST_PRINTF
    CONFIG_KUNIT
    CONFIG_ARCH_RENESAS
    CONFIG_ARCH_STARFIVE
    CONFIG_ARCH_SUNXI
    CONFIG_ARCH_THEAD
    CONFIG_ARCH_VIRT
    CONFIG_ARCH_CANAAN
    CONFIG_ARCH_SIFIVE
    CONFIG_SOC_STARFIVE
    CONFIG_SOC_CANAAN
    CONFIG_SOC_SIFIVE
    CONFIG_SOC_MICROCHIP_POLARFIRE
    CONFIG_PINCTRL
    CONFIG_UNIX
    CONFIG_UNIX98_PTYS
    CONFIG_INET
    CONFIG_IPV6
    CONFIG_PACKET
    CONFIG_INET_DIAG
    CONFIG_INET_TCP_DIAG
    CONFIG_INET_UDP_DIAG
    CONFIG_IPV6_SIT
    CONFIG_DNS_RESOLVER
    CONFIG_NET
    CONFIG_SCSI
    CONFIG_SCSI_MOD
    CONFIG_BLK_DEV
    CONFIG_BTRFS_FS
    CONFIG_ATA
    CONFIG_MD
    CONFIG_BLK_DEV_MD
    CONFIG_MD_AUTODETECT
    CONFIG_MD_RAID0
    CONFIG_MD_RAID1
    CONFIG_MD_RAID10
    CONFIG_MD_RAID456
    CONFIG_RAID6_PQ
    CONFIG_RAID6_PQ_BENCHMARK
    CONFIG_ASYNC_RAID6_RECOV
    CONFIG_ASYNC_TX
    CONFIG_XOR_BLOCKS
    CONFIG_ASYNC_XOR
    CONFIG_ASYNC_MEMCPY
    CONFIG_ASYNC_TX_ENABLE_CHANNEL_SWITCH
    CONFIG_USB_SUPPORT
    CONFIG_USB
    CONFIG_USB_UAS
    CONFIG_USB_STORAGE
    CONFIG_USB_HID
    CONFIG_USB_OHCI_LITTLE_ENDIAN
    CONFIG_PCI
    CONFIG_PCI_DOMAINS
    CONFIG_OF_PCI
    CONFIG_VGA_ARB
    CONFIG_E1000E
    CONFIG_NFS_FS
    CONFIG_NFSD
    CONFIG_SUNRPC
    CONFIG_CEPH_FS
    CONFIG_9P_FS
    CONFIG_NET_9P
    CONFIG_INPUT
    CONFIG_INPUT_MOUSE
    CONFIG_INPUT_MOUSEDEV
    CONFIG_MOUSE_PS2
    CONFIG_MOUSE_PS2_ALPS
    CONFIG_MOUSE_PS2_BYD
    CONFIG_MOUSE_PS2_CYPRESS
    CONFIG_MOUSE_PS2_ELANTECH
    CONFIG_MOUSE_PS2_FOCALTECH
    CONFIG_MOUSE_PS2_LOGIPS2PP
    CONFIG_MOUSE_PS2_SYNAPTICS
    CONFIG_MOUSE_PS2_SYNAPTICS_SMBUS
    CONFIG_MOUSE_PS2_TRACKPOINT
    CONFIG_HID
    CONFIG_HID_GENERIC
    CONFIG_MMC
    CONFIG_MMC_SDHCI
    CONFIG_MMC_SDHCI_PLTFM
    CONFIG_CRYPTO_ECC
    CONFIG_CRYPTO_ECDH
    CONFIG_CRYPTO_DH
    CONFIG_CRYPTO_DH_RFC7919_GROUPS
    CONFIG_CRYPTO_AUTHENC
    CONFIG_CRYPTO_AEAD
    CONFIG_CRYPTO_AKCIPHER
    CONFIG_CRYPTO_SKCIPHER
    CONFIG_CRYPTO_HASH
    CONFIG_CRYPTO_RNG
    CONFIG_CRYPTO_NULL
    CONFIG_CRYPTO_MANAGER
    CONFIG_CRYPTO_MANAGER2
    CONFIG_CRYPTO_ALGAPI
    CONFIG_CRYPTO_ALGAPI2
    CONFIG_CRYPTO_AEAD2
    CONFIG_CRYPTO_RNG2
    CONFIG_CRYPTO_NULL2
    CONFIG_CRYPTO_HASH2
    CONFIG_CRYPTO_AES
    CONFIG_CRYPTO_LIB_AES
    CONFIG_CRYPTO_GHASH
    CONFIG_CRYPTO_GENIV
    CONFIG_CRYPTO_ECHAINIV
    CONFIG_CRYPTO_SEQIV
    CONFIG_CRYPTO_GCM
    CONFIG_CRYPTO_HMAC
    CONFIG_CRYPTO_CBC
    CONFIG_CRYPTO_CTR
    CONFIG_CRYPTO_USER_API
    CONFIG_CRYPTO_USER_API_HASH
    CONFIG_CRYPTO_USER_API_SKCIPHER
    CONFIG_CRYPTO_USER_API_AEAD
    CONFIG_CRYPTO
    CONFIG_CRYPTO_DEV_ALLWINNER
    CONFIG_CRYPTO_DEV_VIRTIO
    CONFIG_CRYPTO_ENGINE
    CONFIG_CRYPTO_DRBG_MENU
    CONFIG_CRYPTO_DRBG
    CONFIG_CRYPTO_RNG_DEFAULT
    CONFIG_CRYPTO_SHA3
    CONFIG_CRYPTO_BLAKE2B
    CONFIG_CRYPTO_JITTERENTROPY
    CONFIG_KEYS
    CONFIG_INTEGRITY
    CONFIG_SECURITY
    CONFIG_SECURITYFS
    CONFIG_SECURITY_NETWORK
    CONFIG_SECURITY_PATH
    CONFIG_HUGETLBFS
    CONFIG_HUGETLB_PAGE
    CONFIG_AUDIT
    CONFIG_THERMAL
    CONFIG_CPU_IDLE
    CONFIG_KVM
    CONFIG_VIRTUALIZATION
    CONFIG_IOMMU_SUPPORT
    CONFIG_DMA_COHERENT_POOL
    CONFIG_DMA_DECLARE_COHERENT
    CONFIG_DMA_DIRECT_REMAP
    CONFIG_DMA_NONCOHERENT_MMAP
    CONFIG_DMA_SHARED_BUFFER
    CONFIG_DMADEVICES
    CONFIG_HW_RANDOM
    CONFIG_64BIT_TIME
    CONFIG_ERRATA_THEAD
    CONFIG_RISCV_ALTERNATIVE
    CONFIG_RISCV_ISA_C
    CONFIG_RISCV_ISA_F
    CONFIG_RISCV_ISA_D
    CONFIG_RISCV_ISA_V
    CONFIG_RISCV_SBI_V01
    CONFIG_VT
)

force_off_symbols=(
    CONFIG_EFI
    CONFIG_EFI_STUB
    CONFIG_FPU
    CONFIG_CGROUP_PERF
    CONFIG_PROFILING
    CONFIG_PERF_EVENTS
    CONFIG_DEBUG_KERNEL
    CONFIG_DEBUG_MISC
    CONFIG_DEBUG_LIST
    CONFIG_DEBUG_PLIST
    CONFIG_DEBUG_VM_PGTABLE
    CONFIG_DEBUG_FS
    CONFIG_TEST_KSTRTOX
    CONFIG_TEST_PRINTF
    CONFIG_KUNIT
    CONFIG_CRYPTO_RNG_DEFAULT
    CONFIG_CRYPTO_DRBG_MENU
    CONFIG_CRYPTO_DRBG
    CONFIG_CRYPTO_JITTERENTROPY
    CONFIG_CRYPTO
    CONFIG_PACKET
    CONFIG_INET_DIAG
    CONFIG_INET_TCP_DIAG
    CONFIG_INET_UDP_DIAG
    CONFIG_IPV6_SIT
    CONFIG_DNS_RESOLVER
    CONFIG_USB_UAS
    CONFIG_USB_STORAGE
    CONFIG_USB_HID
    CONFIG_E1000E
    CONFIG_INPUT
    CONFIG_INPUT_MOUSE
    CONFIG_INPUT_MOUSEDEV
    CONFIG_MOUSE_PS2
    CONFIG_MOUSE_PS2_ALPS
    CONFIG_MOUSE_PS2_BYD
    CONFIG_MOUSE_PS2_CYPRESS
    CONFIG_MOUSE_PS2_ELANTECH
    CONFIG_MOUSE_PS2_FOCALTECH
    CONFIG_MOUSE_PS2_LOGIPS2PP
    CONFIG_MOUSE_PS2_SYNAPTICS
    CONFIG_MOUSE_PS2_SYNAPTICS_SMBUS
    CONFIG_MOUSE_PS2_TRACKPOINT
    CONFIG_HID
    CONFIG_HID_GENERIC
    CONFIG_MMC
    CONFIG_MMC_SDHCI
    CONFIG_MMC_SDHCI_PLTFM
    CONFIG_CRYPTO_AUTHENC
    CONFIG_CRYPTO_AEAD
    CONFIG_CRYPTO_AKCIPHER
    CONFIG_CRYPTO_SKCIPHER
    CONFIG_CRYPTO_HASH
    CONFIG_CRYPTO_RNG
    CONFIG_CRYPTO_NULL
    CONFIG_CRYPTO_MANAGER
    CONFIG_CRYPTO_MANAGER2
    CONFIG_CRYPTO_ALGAPI
    CONFIG_CRYPTO_ALGAPI2
    CONFIG_CRYPTO_AEAD2
    CONFIG_CRYPTO_RNG2
    CONFIG_CRYPTO_NULL2
    CONFIG_CRYPTO_HASH2
    CONFIG_CRYPTO_AES
    CONFIG_CRYPTO_LIB_AES
    CONFIG_CRYPTO_GHASH
    CONFIG_CRYPTO_SHA3
    CONFIG_CRYPTO_BLAKE2B
    CONFIG_CRYPTO_GENIV
    CONFIG_CRYPTO_ECHAINIV
    CONFIG_CRYPTO_GCM
    CONFIG_CRYPTO_HMAC
    CONFIG_CRYPTO_CBC
    CONFIG_CRYPTO_CTR
    CONFIG_RAID6_PQ
    CONFIG_RAID6_PQ_BENCHMARK
    CONFIG_XOR_BLOCKS
    CONFIG_ASYNC_TX
    CONFIG_PINCTRL
    CONFIG_DMA_COHERENT_POOL
    CONFIG_DMA_SHARED_BUFFER
    CONFIG_RISCV_ISA_C
    CONFIG_RISCV_ISA_F
    CONFIG_RISCV_ISA_D
    CONFIG_RISCV_ISA_V
)

echo "==> Configuring Linux kernel..."
make -C "$LINUX_DIR" ARCH=riscv CROSS_COMPILE="$KERNEL_CROSS_COMPILE" mrproper
make -C "$LINUX_DIR" ARCH=riscv CROSS_COMPILE="$KERNEL_CROSS_COMPILE" "$(pick_linux_defconfig)"
cc -O2 -Wall -Wextra -o "$GEN_INIT_CPIO_BIN" "$LINUX_DIR/usr/gen_init_cpio.c"
"$GEN_INIT_CPIO_BIN" "$INITRAMFS_LIST" > "$INITRAMFS_CPIO"
INITRAMFS_CONTENTS="$LINUX_OUT_DIR/initramfs.contents"
cpio -it < "$INITRAMFS_CPIO" | sed -e 's#^\./##' -e 's#^/##' > "$INITRAMFS_CONTENTS"
for required_entry in init dev/console dev/null; do
    if ! grep -qx "$required_entry" "$INITRAMFS_CONTENTS"; then
        echo "Generated initramfs is missing $required_entry" >&2
        exit 1
    fi
done
cat > "$CONFIG_FRAGMENT" <<EOF
CONFIG_EXPERT=y
CONFIG_32BIT=y
# CONFIG_64BIT is not set
CONFIG_MMU=y
CONFIG_OF=y
CONFIG_BLK_DEV_INITRD=y
CONFIG_BINFMT_ELF=y
CONFIG_TTY=y
CONFIG_DEVTMPFS=y
CONFIG_DEVTMPFS_MOUNT=y
CONFIG_SERIAL_8250=y
CONFIG_SERIAL_8250_CONSOLE=y
CONFIG_SERIAL_OF_PLATFORM=y
CONFIG_SERIAL_EARLYCON=y
CONFIG_PRINTK=y
CONFIG_RISCV_SBI=y
CONFIG_RISCV_TIMER=y
CONFIG_CMDLINE_BOOL=y
CONFIG_CMDLINE="console=ttyS0,115200 earlycon=uart8250,mmio32,0x20000000 loglevel=8 rdinit=/init cpuidle.off=1"
CONFIG_CMDLINE_FORCE=y
CONFIG_HZ_100=y
CONFIG_LSM="capability"
CONFIG_INITRAMFS_SOURCE="$INITRAMFS_CPIO"
CONFIG_INITRAMFS_COMPRESSION_NONE=y
CONFIG_SERIAL_8250_RUNTIME_UARTS=1
EOF

for symbol in "${common_disable_symbols[@]}"; do
    write_config_disabled "$CONFIG_FRAGMENT" "$symbol"
done

cat > "$CONFIG_FORCE_OFF_FRAGMENT" <<EOF
# Forced-off symbols after olddefconfig rewrites leaf choices via select chains.
EOF

for symbol in "${force_off_symbols[@]}"; do
    write_config_disabled "$CONFIG_FORCE_OFF_FRAGMENT" "$symbol"
done

sh "$LINUX_DIR/scripts/kconfig/merge_config.sh" -m -r \
    "$LINUX_DIR/.config" "$CONFIG_FRAGMENT"
make -C "$LINUX_DIR" ARCH=riscv CROSS_COMPILE="$KERNEL_CROSS_COMPILE" \
    olddefconfig

apply_disable_list "$LINUX_DIR/.config" "${force_off_symbols[@]}"
set_kconfig_string "$LINUX_DIR/.config" CONFIG_INITRAMFS_SOURCE "$INITRAMFS_CPIO"

make -C "$LINUX_DIR" ARCH=riscv CROSS_COMPILE="$KERNEL_CROSS_COMPILE" \
    olddefconfig

if ! grep -Fqx "CONFIG_INITRAMFS_SOURCE=\"$INITRAMFS_CPIO\"" "$LINUX_DIR/.config"; then
    echo "Final kernel config dropped CONFIG_INITRAMFS_SOURCE" >&2
    exit 1
fi

echo "==> Building Linux kernel image..."
make -C "$LINUX_DIR" -j"$(num_jobs)" \
    ARCH=riscv \
    CROSS_COMPILE="$KERNEL_CROSS_COMPILE" \
    KCFLAGS="-march=${KERNEL_MARCH} -mabi=${KERNEL_MABI}" \
    KAFLAGS="-march=${KERNEL_MARCH} -mabi=${KERNEL_MABI}" \
    Image

if [ -f "$LINUX_DIR/usr/initramfs_data.cpio" ]; then
    cpio -it < "$LINUX_DIR/usr/initramfs_data.cpio" | sed -e 's#^\./##' -e 's#^/##' > "$INITRAMFS_CONTENTS"
elif [ -f "$LINUX_DIR/usr/initramfs_inc_data" ]; then
    if gzip -dc "$LINUX_DIR/usr/initramfs_inc_data" 2>/dev/null | cpio -it | sed -e 's#^\./##' -e 's#^/##' > "$INITRAMFS_CONTENTS"; then
        :
    else
        cpio -it < "$LINUX_DIR/usr/initramfs_inc_data" | sed -e 's#^\./##' -e 's#^/##' > "$INITRAMFS_CONTENTS"
    fi
fi

if [ -f "$INITRAMFS_CONTENTS" ]; then
    for required_entry in init dev/console dev/null; do
        if ! grep -qx "$required_entry" "$INITRAMFS_CONTENTS"; then
            echo "Embedded initramfs is missing $required_entry" >&2
            exit 1
        fi
    done
fi

cp "$LINUX_DIR/arch/riscv/boot/Image" "$LINUX_IMAGE"
cp "$LINUX_DIR/vmlinux" "$LINUX_VMLINUX"
cp "$LINUX_DIR/System.map" "$LINUX_SYSTEM_MAP"

echo "==> Building OpenSBI fw_payload..."
make -C "$OPENSBI_DIR" -j"$(num_jobs)" \
    PLATFORM=generic \
    FW_PAYLOAD=y \
    FW_PAYLOAD_PATH="$LINUX_IMAGE" \
    FW_FDT_PATH="$DTB" \
    FW_TEXT_START=0x80000000 \
    FW_PAYLOAD_ALIGN=0x1000 \
    PLATFORM_RISCV_XLEN=32 \
    PLATFORM_RISCV_ISA="$PLATFORM_RISCV_ISA" \
    PLATFORM_RISCV_ABI="$PLATFORM_RISCV_ABI" \
    CROSS_COMPILE="$OPENSBI_CROSS_COMPILE"

cp "$OPENSBI_DIR/build/platform/generic/firmware/fw_payload.elf" "$LINUX_ELF"
"${OPENSBI_CROSS_COMPILE}objcopy" \
    --change-addresses -0x80000000 \
    -O binary \
    "$LINUX_ELF" "$LINUX_BIN"
"${OPENSBI_CROSS_COMPILE}objcopy" \
    -I binary \
    -O verilog \
    --verilog-data-width=4 \
    --reverse-bytes=4 \
    "$LINUX_BIN" "$LINUX_HEX"

echo "==> Linux payload image ready:"
echo "    DTB: $DTB"
echo "    Image: $LINUX_IMAGE"
echo "    vmlinux: $LINUX_VMLINUX"
echo "    System.map: $LINUX_SYSTEM_MAP"
echo "    ELF: $LINUX_ELF"
echo "    HEX: $LINUX_HEX"
