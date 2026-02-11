FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Keep CI/devcontainer setup fast and reproducible by using distro packages.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        binutils-riscv64-unknown-elf \
        ca-certificates \
        g++ \
        gcc-riscv64-unknown-elf \
        git \
        iverilog \
        make \
        python3 \
        python3-dev \
        python3-pip \
        python3-venv \
        verilator && \
    verilator --version && \
    verilator --version | grep -Eq '^Verilator 5\.' && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Set up a working directory
WORKDIR /workspace

CMD ["/bin/bash"]
