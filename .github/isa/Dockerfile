FROM ubuntu:24.04

ARG SPIKE_VERSION=v1.1.0
ARG RISCV_TESTS_VERSION=2ebecad997fa58cd9e5724340ba75aa4b59bd1d0

ENV DEBIAN_FRONTEND=noninteractive \
    RISCV=/usr \
    RISCV_TESTS_DIR=/opt/riscv-tests \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:/opt/spike/bin:$PATH

LABEL org.opencontainers.image.title="synapse32 ISA golden test environment" \
      org.opencontainers.image.description="Pinned Spike and prebuilt riscv-tests corpus for Synapse32" \
      org.opencontainers.image.source="https://github.com/5iri/synapse32"

RUN apt-get update && apt-get install -y --no-install-recommends \
        autoconf \
        automake \
        autotools-dev \
        binutils-riscv64-unknown-elf \
        bison \
        build-essential \
        ca-certificates \
        device-tree-compiler \
        flex \
        gawk \
        gcc-riscv64-unknown-elf \
        git \
        gperf \
        libboost-filesystem-dev \
        libboost-regex-dev \
        libboost-system-dev \
        libexpat1-dev \
        libgmp-dev \
        libmpc-dev \
        libmpfr-dev \
        libtool \
        make \
        ninja-build \
        patchutils \
        picolibc-riscv64-unknown-elf \
        python3 \
        python3-venv \
        texinfo \
        verilator \
        zlib1g-dev && \
    verilator --version | grep -Eq '^Verilator 5\.' && \
    rm -rf /var/lib/apt/lists/*

RUN git clone --depth 1 --branch "$SPIKE_VERSION" \
        https://github.com/riscv-software-src/riscv-isa-sim.git /tmp/riscv-isa-sim && \
    mkdir /tmp/riscv-isa-sim/build && \
    cd /tmp/riscv-isa-sim/build && \
    ../configure CXXFLAGS="-include cstdint" --prefix=/opt/spike && \
    make -j"$(nproc)" && \
    make install && \
    rm -rf /tmp/riscv-isa-sim

RUN git clone --depth 1 --recurse-submodules \
        https://github.com/riscv-software-src/riscv-tests.git "$RISCV_TESTS_DIR" && \
    cd "$RISCV_TESTS_DIR" && \
    git checkout "$RISCV_TESTS_VERSION" && \
    autoconf && \
    ./configure --prefix="$RISCV_TESTS_DIR/install" && \
    cd isa && \
    for suite in rv32ui rv32um rv32ua rv32mi rv32si; do \
        for source in "$suite"/*.S; do \
            make -j"$(nproc)" XLEN=32 "$(dirname "$source")-p-$(basename "$source" .S)"; \
        done; \
    done && \
    find "$RISCV_TESTS_DIR/isa" -maxdepth 1 -type f \
        \( -name 'rv32ui-p-*' -o -name 'rv32um-p-*' -o -name 'rv32ua-p-*' \
           -o -name 'rv32mi-p-*' -o -name 'rv32si-p-*' \) -print | sort

COPY tests/requirements.txt /tmp/isa-requirements.txt
RUN python3 -m venv "$VIRTUAL_ENV" && \
    "$VIRTUAL_ENV/bin/pip" install --no-cache-dir --upgrade pip && \
    "$VIRTUAL_ENV/bin/pip" install --no-cache-dir -r /tmp/isa-requirements.txt && \
    rm /tmp/isa-requirements.txt

WORKDIR /workspace
CMD ["/bin/bash"]
