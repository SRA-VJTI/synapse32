FROM ubuntu:24.04

ARG SPIKE_VERSION=v1.1.0
ARG RISCV_TESTS_VERSION=2ebecad997fa58cd9e5724340ba75aa4b59bd1d0
# riscv-arch-test tag 3.10.0
ARG RISCV_ARCH_TEST_VERSION=fc32e41d49480fd99ba0a192dfff9c3319b44873

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
        python3-dev \
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
    ../configure CXXFLAGS="-include cstdint" --prefix=/opt/spike --enable-commitlog && \
    make -j"$(nproc)" && \
    make install && \
    rm -rf /tmp/riscv-isa-sim

# A shallow clone only holds the branch tip, so fetch the pinned commit itself.
RUN git init "$RISCV_TESTS_DIR" && \
    cd "$RISCV_TESTS_DIR" && \
    git remote add origin https://github.com/riscv-software-src/riscv-tests.git && \
    git fetch --depth 1 origin "$RISCV_TESTS_VERSION" && \
    git checkout FETCH_HEAD && \
    git submodule update --init --depth 1 --recursive && \
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

# Sources of the suites compare_with_spike.py runs; it compiles them with .github/arch-test.
ENV RISCV_ARCH_TEST_DIR=/opt/riscv-arch-test
RUN git init "$RISCV_ARCH_TEST_DIR" && \
    cd "$RISCV_ARCH_TEST_DIR" && \
    git remote add origin https://github.com/riscv-non-isa/riscv-arch-test.git && \
    git fetch --depth 1 origin "$RISCV_ARCH_TEST_VERSION" && \
    git checkout FETCH_HEAD && \
    find . -mindepth 1 -maxdepth 1 ! -name riscv-test-suite -exec rm -rf {} + && \
    find riscv-test-suite -mindepth 1 -maxdepth 1 ! -name env ! -name rv32i_m -exec rm -rf {} + && \
    find riscv-test-suite/rv32i_m -mindepth 1 -maxdepth 1 ! -name I ! -name M ! -name A ! -name Zifencei \
        ! -name privilege -exec rm -rf {} + && \
    ls riscv-test-suite/env/arch_test.h riscv-test-suite/rv32i_m/I/src/add-01.S

WORKDIR /workspace
CMD ["/bin/bash"]
