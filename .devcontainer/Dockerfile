FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        autoconf \
        automake \
        autotools-dev \
        binutils-riscv64-linux-gnu \
        bc \
        bison \
        bzip2 \
        cpio \
        ca-certificates \
        curl \
        device-tree-compiler \
        flex \
        g++ \
        gawk \
        gcc-riscv64-linux-gnu \
        git \
        gperf \
        iverilog \
        libexpat-dev \
        libgmp-dev \
        libmpc-dev \
        libmpfr-dev \
        libssl-dev \
        libtool \
        make \
        ninja-build \
        patchutils \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        texinfo \
        verilator \
        wget \
        zlib1g-dev && \
    verilator --version && \
    verilator --version | grep -Eq '^Verilator 5\.' && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Build a native rv32ima+ilp32 Linux toolchain (gcc + glibc) from riscv-gnu-toolchain.
# This is the only reliable way to get rv32+ilp32 userspace binaries; no Ubuntu package
# provides rv32 multilib or an ilp32 glibc sysroot.
RUN git clone --depth 1 https://github.com/riscv-collab/riscv-gnu-toolchain /tmp/riscv-gnu-toolchain && \
    cd /tmp/riscv-gnu-toolchain && \
    ./configure \
        --prefix=/opt/riscv32 \
        --with-arch=rv32ima \
        --with-abi=ilp32 && \
    make linux -j"$(( $(nproc) < 4 ? $(nproc) : 4 ))" && \
    rm -rf /tmp/riscv-gnu-toolchain

ENV PATH="/opt/riscv32/bin:${PATH}"

# Set up a working directory
WORKDIR /workspace

CMD ["/bin/bash"]
