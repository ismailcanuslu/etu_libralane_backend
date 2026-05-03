# librelane/runner:basic
# Minimal EDA toolbox image — verilator, iverilog, yosys, gtkwave.
# Per-job ephemeral container. Backend bind-mount eder /work dizinini.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        verilator \
        iverilog \
        yosys \
        gtkwave \
        make \
        bash \
        coreutils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
CMD ["bash"]
