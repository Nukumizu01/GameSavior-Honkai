#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT_DIR"

PUBLIC_URL=${1:-http://127.0.0.1:8080}
CONFIG_URL=${MARCH7TH_CONFIG_URL:-https://m7a.top/assets/config/config.example.yaml}

random_secret() {
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 24
    else
        od -An -N24 -tx1 /dev/urandom | tr -d ' \n'
    fi
}

replace_env() {
    key=$1
    value=$2
    escaped=$(printf '%s' "$value" | sed 's/[&|]/\\&/g')
    sed -i "s|^${key}=.*|${key}=${escaped}|" .env
}

if [ ! -f .env ]; then
    cp .env.example .env
    ADMIN_PASSWORD=$(random_secret)
    WORKER_TOKEN=$(random_secret)
    replace_env APP_BASE_URL "$PUBLIC_URL"
    replace_env ADMIN_PASSWORD "$ADMIN_PASSWORD"
    replace_env WORKER_TOKEN "$WORKER_TOKEN"
    if command -v curl >/dev/null 2>&1 \
        && ! curl -sS --connect-timeout 4 --max-time 8 -o /dev/null https://registry-1.docker.io/v2/; then
        replace_env API_IMAGE "mirror.ccs.tencentyun.com/library/python:3.12-slim"
        replace_env MARCH7TH_IMAGE "ghcr.nju.edu.cn/moesnow/march7thassistant:latest"
        replace_env PIP_INDEX_URL "https://mirrors.aliyun.com/pypi/simple"
        REGISTRY_FALLBACK=1
    else
        REGISTRY_FALLBACK=0
    fi
    chmod 600 .env
    CREATED_ENV=1
else
    CREATED_ENV=0
    REGISTRY_FALLBACK=0
fi

mkdir -p data/artifacts data/worker_logs starrail/logs starrail/control starrail/UserProfile

if [ ! -s starrail/config.yaml ]; then
    temporary_config=starrail/.config.yaml.download
    cleanup_config() {
        rm -f "$temporary_config"
    }
    trap cleanup_config EXIT INT TERM
    rm -f "$temporary_config"
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL "$CONFIG_URL" -o "$temporary_config"
    elif command -v wget >/dev/null 2>&1; then
        wget -qO "$temporary_config" "$CONFIG_URL"
    else
        echo "错误：需要 curl 或 wget 下载 March7thAssistant 配置模板。" >&2
        exit 1
    fi
    mv "$temporary_config" starrail/config.yaml
    trap - EXIT INT TERM
    sed -i 's/^cloud_game_enable:.*/cloud_game_enable: true/' starrail/config.yaml
    sed -i 's/^browser_headless_enable:.*/browser_headless_enable: true/' starrail/config.yaml
    sed -i 's/^browser_persistent_enable:.*/browser_persistent_enable: true/' starrail/config.yaml
    sed -i 's/^pause_after_success:.*/pause_after_success: false/' starrail/config.yaml
    sed -i 's/^after_finish:.*/after_finish: Exit/' starrail/config.yaml
fi

echo
echo "Game Savior 初始化完成。"
echo "控制台地址: $PUBLIC_URL"
if [ "$CREATED_ENV" -eq 1 ]; then
    echo "管理员用户名: admin"
    echo "管理员密码: $ADMIN_PASSWORD"
    echo "请妥善保存密码；完整配置位于 .env。"
    if [ "$REGISTRY_FALLBACK" -eq 1 ]; then
        echo "Docker Hub 不可用，已自动切换到国内镜像。"
    fi
else
    echo ".env 已存在，未覆盖现有密码和密钥。"
fi
echo
echo "启动命令: docker compose up -d --build"
