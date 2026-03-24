FROM mcr.microsoft.com/devcontainers/base:ubuntu

# 必要なパッケージのインストール (make, shellcheck, curl, bash)
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get -y install --no-install-recommends \
        make \
        shellcheck \
        curl \
        bash \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# uv (SkillPortの実行・管理用) のインストール
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/uv \
    && mv /root/.local/bin/uvx /usr/local/bin/uvx
