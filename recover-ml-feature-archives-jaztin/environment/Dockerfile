FROM python:3.11-slim-bookworm@sha256:ad9eb6b79e05aa36fedb6a6edfd59caf4de6edeeef88c25a4adb2fdaed4e6e69

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        asciinema \
        curl \
        tmux \
    && rm -rf /var/lib/apt/lists/*

ARG OPA_VERSION=0.65.0
RUN curl -fsSL \
    "https://github.com/open-policy-agent/opa/releases/download/v${OPA_VERSION}/opa_linux_amd64_static" \
    -o /usr/local/bin/opa \
    && chmod +x /usr/local/bin/opa

WORKDIR /app

RUN pip install --no-cache-dir \
    polars==0.20.31 \
    duckdb==0.10.3 \
    pyarrow==16.1.0 \
    pyyaml==6.0.1 \
    pytest==8.2.2 \
    pytest-ctrf-json==0.0.9

COPY setup_archive.py /app/setup_archive.py
RUN python /app/setup_archive.py

COPY recover.rego /app/policy/recover.rego

RUN mkdir -p /app/facts /app/output /logs/verifier
