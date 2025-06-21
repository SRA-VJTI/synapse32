FROM ubuntu:24.10

# Install system dependencies and Verilator build deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        git help2man perl python3 python3-venv python3-pip make autoconf g++ flex bison ccache \
        libgoogle-perftools-dev numactl perl-doc \
        ca-certificates \
        libboost-all-dev \
        libfl-dev libfl2 zlib1g zlib1g-dev \
        autoconf automake autotools-dev curl libmpc-dev libmpfr-dev libgmp-dev \
        gawk build-essential texinfo gperf libtool patchutils bc \
        libexpat-dev python3-pip iverilog gtkwave x11-apps && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Build RISC-V toolchain with multilib (RV32+RV64 support)
RUN git clone https://github.com/riscv/riscv-gnu-toolchain.git && \
    cd riscv-gnu-toolchain && \
    ./configure --prefix=/opt/riscv --enable-multilib && \
    make -j$(nproc)

ENV PATH="/opt/riscv/bin:${PATH}"

# Install Verilator from source
RUN git clone https://github.com/verilator/verilator && \
    cd verilator && \
    git checkout stable && \
    autoconf && \
    ./configure --prefix=/usr/local && \
    make -j$(nproc) && \
    make install

# Set up a working directory
WORKDIR /workspace

CMD ["/bin/bash"]
