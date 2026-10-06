# 部署指南

部署流程已经统一到项目根目录的 [README.md](README.md)。推荐使用 Git clone 和默认 `docker-compose.yml`：

```bash
git clone https://github.com/YOUR_NAME/game-savior.git
cd game-savior
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh http://SERVER_IP:8080
docker compose up -d --build
```

请不要提交 `.env`、`data/`、`starrail/config.yaml`、`starrail/UserProfile/`、日志、截图或二维码。这些内容均可能包含密码、Token、Cookie 或账号运行信息。
