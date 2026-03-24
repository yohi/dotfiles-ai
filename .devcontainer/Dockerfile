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

# Copy uv binaries from official image with pinned digest
COPY --from=ghcr.io/astral-sh/uv:0.6.2-bookworm-slim@sha256:0637172088f119183359d9c22e431f99c15f9b12e3478950550f28822005423f /uv /uvx /usr/local/bin/

# Create non-root user
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=$USER_UID

# The base image might already have a vscode user, so we handle it gracefully.
# Check if user exists, if not create it. Then ensure permissions on uv binaries.
RUN if ! id -u $USERNAME > /dev/null 2>&1; then \
        groupadd --gid $USER_GID $USERNAME \
        && useradd --uid $USER_UID --gid $USER_GID -m $USERNAME; \
    fi \
    && chown $USERNAME:$USER_GID /usr/local/bin/uv /usr/local/bin/uvx

USER $USERNAME
