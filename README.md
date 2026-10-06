# Game Savior

Game Savior 是一个面向个人使用的云端游戏自动化控制台。它提供网页端任务调度、运行日志、截图、脚本设置、登录切换和飞书通知，并通过独立 Worker 驱动 March7thAssistant 执行《崩坏：星穹铁道》云游戏日常。

> 当前可用范围：崩铁 + March7thAssistant。原神 BetterGI 适配代码仍在仓库中，但默认关闭，尚不属于可直接部署的功能。

## 功能

- 网页控制台：创建、取消、重试任务，查看运行状态
- 分类脚本设置：体力、日常、云游戏、程序、推送等
- 定时执行：按时区和每日固定时间创建任务（`分 时 * * *`）
- 日志与附件：实时日志、完整 Worker 日志、运行截图
- 云游戏登录：切换账号、自动检测二维码、发送到飞书
- 飞书通知：成功、失败、超时和登录二维码通知
- 可靠停止：取消任务时终止脚本进程树
- 结果校验：脚本退出码为 0 但日志报告“未完成”时仍判定失败
- 数据持久化：SQLite、日志和附件保存在宿主机；附件保留参数默认 30 天

## 架构

```text
Browser / PWA
      |
      v
FastAPI API ---- SQLite / artifacts
      |
      v
StarRail Worker ---- March7thAssistant ---- 云·星穹铁道
      |
      +---- Feishu webhook / app bot
```

默认 Docker Compose 包含：

- `api`：FastAPI 后端和静态网页
- `starrail-worker`：March7thAssistant 与 Worker 适配器
- `caddy`：可选的 HTTPS 反向代理，仅在 `https` profile 中启动

## 前置条件

- Linux x86_64 服务器，建议 Ubuntu 22.04/24.04 或 Debian 12
- Docker Engine 24+ 与 Docker Compose v2
- 建议至少 2 核 CPU、4 GB 内存、20 GB 可用磁盘
- 服务器能够访问 Docker Hub、GitHub Container Registry 和云游戏服务
- 公网访问时配置防火墙或云安全组

March7thAssistant 和云游戏可能受网络区域、上游版本以及账号状态影响。请遵守游戏、云游戏和相关开源项目的服务条款，自行承担使用风险。

## 快速部署

### 1. 安装 Docker

Ubuntu 或 Debian 新服务器可使用 Docker 官方安装脚本：

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
docker version
docker compose version
```

生产服务器也可以按 [Docker Engine 官方文档](https://docs.docker.com/engine/install/) 配置软件源安装。若使用云厂商提供的 Docker 应用镜像，可直接进入下一步。

### 2. 克隆并初始化

```bash
git clone https://github.com/YOUR_NAME/game-savior.git
cd game-savior
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh http://SERVER_IP:8080
```

上传仓库后，请把 `YOUR_NAME/game-savior` 替换为真实 GitHub 仓库路径，把 `SERVER_IP` 替换为服务器公网 IP。

初始化脚本会：

- 从 `.env.example` 创建 `.env`
- 自动生成管理员密码和 Worker Token
- 创建 SQLite、日志、截图、控制目录和浏览器登录目录
- 下载 March7thAssistant 官方 `config.example.yaml`
- 设置云游戏、持久登录和无头运行的基础选项
- 检测 Docker Hub 连通性，必要时自动切换到国内镜像

脚本最后会输出管理员用户名和随机密码。它们也保存在仅本机使用的 `.env` 中。

### 3. 启动

```bash
docker compose up -d --build
docker compose ps
```

访问：

```text
http://SERVER_IP:8080
```

云安全组只需临时放行 `8080/TCP`，并建议限制为自己的公网 IP。不要公开数据库目录、Worker Token 或云游戏登录资料。

### 4. 首次登录云游戏

1. 使用初始化脚本输出的管理员账号登录控制台。
2. 点击“切换登录”。
3. 等待页面出现二维码，使用米游社或游戏支持的客户端扫码。
4. 登录状态会保存在 `starrail/UserProfile/`，后续容器重启会继续复用。
5. 创建一条手动任务，确认清体力、每日实训和奖励领取正常。

首次登录无法完全自动化，因为必须由账号持有人扫码确认。二维码和浏览器资料不会提交到 Git。

新数据库默认启用每天北京时间 `04:20` 的崩铁任务；当天时间已过时，调度器会补建当天任务。建议先在控制台关闭定时任务，完成扫码和手动验证后，再设置期望时间并启用。

## HTTPS 与域名

先把域名 A 记录解析到服务器，再修改 `.env`：

```env
DOMAIN=game.example.com
APP_BASE_URL=https://game.example.com
SESSION_COOKIE_SECURE=true
HTTP_BIND=127.0.0.1
```

在安全组开放 `80/TCP` 和 `443/TCP`，然后启动 HTTPS profile：

```bash
docker compose --profile https up -d --build
```

Caddy 会自动申请和续期证书。确认 HTTPS 可用后，不应再把 `8080` 暴露到公网。

## 飞书通知

文本通知使用群机器人 Webhook：

```env
FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/...
FEISHU_WEBHOOK_SECRET=...
```

发送登录二维码还需要飞书应用机器人：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=...
FEISHU_RECEIVE_ID=oc_xxx
FEISHU_RECEIVE_ID_TYPE=chat_id
```

修改 `.env` 后执行：

```bash
docker compose up -d --force-recreate api starrail-worker
```

登录网页后可点击“测试飞书通知”。成功、失败、超时任务会自动通知；通知中的运行链接会直达该次任务的日志和附件。

## 配置说明

常用环境变量：

| 变量 | 作用 | 默认值 |
| --- | --- | --- |
| `APP_BASE_URL` | 通知中的控制台公网地址 | `http://127.0.0.1:8080` |
| `ADMIN_USERNAME` | 管理员用户名 | `admin` |
| `ADMIN_PASSWORD` | 管理员初始密码 | 必须修改 |
| `WORKER_TOKEN` | API 与 Worker 的共享密钥 | 必须修改 |
| `RETENTION_DAYS` | 日志和附件保留天数 | `30` |
| `HTTP_BIND` | 8080 监听地址 | `0.0.0.0` |
| `HTTP_PORT` | HTTP 端口 | `8080` |
| `TZ` | 容器时区 | `Asia/Shanghai` |

完整配置见 [.env.example](.env.example)。游戏脚本选项优先在网页“脚本设置”中修改，它们会在下一次任务开始前写入 `starrail/config.yaml`。

`ADMIN_USERNAME` 和 `ADMIN_PASSWORD` 只用于首次创建数据库管理员。已有数据库时，修改这两个变量不会更新已有账号密码。当前维护清理通过受管理员认证保护的 `POST /api/v1/maintenance/retention/run` 手动触发，尚未提供自动清理全部宿主机日志的机制。

## 常用命令

```bash
# 查看状态
docker compose ps

# 查看 API / Worker 日志
docker compose logs -f api
docker compose logs -f starrail-worker

# 更新代码并重建
git pull --ff-only
docker compose up -d --build

# 重启 Worker
docker compose restart starrail-worker

# 停止服务但保留数据
docker compose down
```

不要使用 `docker compose down -v`，除非明确准备删除 Caddy 证书数据。项目运行数据保存在宿主机目录，删除 `data/` 或 `starrail/UserProfile/` 会分别丢失控制台记录或云游戏登录状态。

## 国内网络镜像

默认使用官方公共镜像和 PyPI。无法稳定访问时可在构建命令中覆盖：

```bash
API_IMAGE=python:3.12-slim \
MARCH7TH_IMAGE=ghcr.nju.edu.cn/moesnow/march7thassistant:latest \
PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple \
docker compose build

docker compose up -d
```

## 故障排查

```bash
# 确认容器状态和健康检查
docker compose ps

# 查看最近 200 行日志
docker compose logs --tail=200 api
docker compose logs --tail=200 starrail-worker

# 验证最终 Compose 配置
docker compose config --quiet
```

- 网页打不开：检查 `docker compose ps`、云安全组和服务器防火墙是否放行 `HTTP_PORT`。
- Worker 离线：确认 API 已健康，并核对 `.env` 中 `WORKER_TOKEN` 未被单独修改。
- 二维码不出现：查看 Worker 日志，确认云游戏页面可从服务器访问，再重试“切换登录”。
- 更新后页面仍旧：执行 `git pull --ff-only && docker compose up -d --build`，再强制刷新浏览器。
- 登录失效：在控制台重新发起“切换登录”，不要手工提交或复制 `starrail/UserProfile/` 到公开位置。

## 数据目录

以下内容只应保存在部署服务器，不应提交到 GitHub：

- `.env`：密码、Token、飞书密钥
- `data/`：SQLite、附件、通知记录
- `starrail/config.yaml`：脚本运行状态及可能的私有配置
- `starrail/UserProfile/`：云游戏 Cookie 和登录会话
- `starrail/logs/`：脚本日志、截图、二维码
- `starrail/control/`：临时控制指令和登录状态
- `worker_logs/`：Worker 完整日志

仓库已通过 `.gitignore` 和 `.dockerignore` 排除这些文件。上传前仍建议执行：

```bash
git status --short
git grep -nE 'ADMIN_PASSWORD=.+|WORKER_TOKEN=.+|FEISHU_APP_SECRET=.+' -- ':!README.md' ':!.env.example'
```

## 项目结构

```text
app/                       FastAPI、数据库、调度和 API
web/                       原生 HTML/CSS/JavaScript 前端
workers/                   Worker 协议与 March7thAssistant 适配器
scripts/bootstrap.sh       Linux 首次部署初始化
docker-compose.yml         默认完整部署
docker-compose.server.yml  现有服务器兼容配置
Dockerfile                 API 镜像
Dockerfile.starrail-worker Worker 镜像
```

## 已知限制

- 当前只支持一个崩铁账号和一个 Worker。
- 原神 BetterGI 尚未启用。
- March7thAssistant 是独立开源项目，其更新可能改变配置、日志文本或容器行为。
- 首次登录及登录失效后必须由用户扫码。
- SQLite 适合个人单实例使用，不适合多 API 副本并发部署。

## 安全建议

- 首次启动后立即确认 `.env` 中没有示例密码。
- SSH 只允许密钥登录，并在安全组中限制来源 IP。
- 生产环境使用 HTTPS，将 `HTTP_BIND` 设为 `127.0.0.1`。
- 不要把 `.env`、二维码、截图、Cookie、日志压缩包上传到 Issue 或公开仓库。
- 如果密钥曾出现在聊天、终端历史或公开提交中，应立即轮换。

## 上游项目

- [March7thAssistant](https://github.com/moesnow/March7thAssistant)
- [BetterGI](https://github.com/babalae/better-genshin-impact)

本仓库不包含游戏客户端，也不隶属于米哈游、March7thAssistant 或 BetterGI。
