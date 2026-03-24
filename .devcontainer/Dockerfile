# Use pinned base image (Ubuntu 22.04)
FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04@sha256:d175659223e7178c772e09b3051a84f50f28e20f09627798782a17058df5366f

# Install packages
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        make \
        shellcheck \
        curl \
        bash \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy uv binaries from official image
COPY --from=ghcr.io/astral-sh/uv:0.6.2 /uv /uvx /usr/local/bin/
