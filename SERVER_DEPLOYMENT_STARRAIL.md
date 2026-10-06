# 服务器部署说明

服务器部署已经统一为 Git clone + Docker Compose，不再维护压缩包上传流程。

完整步骤、环境变量、HTTPS、飞书和故障排查请阅读 [README.md](README.md)。最短部署流程如下：

```bash
git clone https://github.com/YOUR_NAME/game-savior.git
cd game-savior
chmod +x scripts/bootstrap.sh
./scripts/bootstrap.sh http://SERVER_IP:8080
docker compose up -d --build
docker compose ps
```

首次运行后必须在网页中完成一次云游戏扫码登录。登录资料保存在 `starrail/UserProfile/`，该目录已被 Git 忽略。
