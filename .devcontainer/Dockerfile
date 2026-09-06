FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        autoconf \
        automake \
        autotools-dev \
        binutils-riscv64-linux-gnu \
        binutils-riscv64-unknown-elf \
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
        gcc-riscv64-unknown-elf \
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

# Building a native rv32ima+ilp32 Linux toolchain from source takes about
# 45 minutes in GitHub Actions. Keep it opt-in for Linux bring-up images; the
# CI image only needs the packaged bare-metal toolchain below.
ARG BUILD_RV32_LINUX_TOOLCHAIN=1
RUN if [ "$BUILD_RV32_LINUX_TOOLCHAIN" = "1" ]; then \
      git clone --depth 1 https://github.com/riscv-collab/riscv-gnu-toolchain /tmp/riscv-gnu-toolchain && \
      cd /tmp/riscv-gnu-toolchain && \
      ./configure --prefix=/opt/riscv32 --with-arch=rv32ima --with-abi=ilp32 && \
      make linux -j"$(( $(nproc) < 4 ? $(nproc) : 4 ))" && \
      rm -rf /tmp/riscv-gnu-toolchain; \
    fi

ENV PATH="/opt/riscv32/bin:${PATH}"

# Set up a working directory
WORKDIR /workspace

CMD ["/bin/bash"]
