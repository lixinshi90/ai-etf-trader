# AI ETF Trader - 完整部署指南

## 📋 目录

1. [前置要求](#前置要求)
2. [本地开发环境](#本地开发环境)
3. [GitHub仓库设置](#github仓库设置)
4. [Docker部署](#docker部署)
5. [Linux服务器部署](#linux服务器部署)
6. [生产环境配置](#生产环境配置)
7. [监控和维护](#监控和维护)
8. [故障排查](#故障排查)

---

## 前置要求

### 系统要求
- **Python**: 3.11+
- **操作系统**: Linux (Ubuntu 22.04+), macOS, Windows
- **内存**: 最少 2GB RAM
- **磁盘**: 最少 5GB 可用空间

### 必需工具
- Git
- Docker & Docker Compose (用于容器部署)
- uv (Python 包管理器)
- curl (用于健康检查)

### API密钥
- OpenAI API Key 或其他LLM服务的API密钥
- 推荐使用：Zhipu GLM-4, OpenAI GPT-4, 等

---

## 本地开发环境

### 1. 克隆项目

```bash
git clone https://github.com/yourusername/ai-etf-trader.git
cd ai-etf-trader
```

### 2. 安装uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### 3. 配置环境变量

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑 .env 文件，填入你的API密钥和配置
nano .env  # 或使用你喜欢的编辑器
```

**关键配置项：**
```env
OPENAI_API_KEY=your_actual_api_key
BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL_NAME=glm-4-air
ETF_LIST=510050,159915,510300
SCHEDULE_TIME=17:00
INITIAL_CAPITAL=100000
```

### 4. 安装依赖

```bash
# 安装所有依赖（包括开发依赖）
uv sync --all-extras

# 或仅安装生产依赖
uv sync
```

### 5. 初始化数据库

```bash
# 创建必要的目录
mkdir -p data logs decisions trades tmp

# 数据库会在首次运行时自动创建
```

### 6. 启动Web服务

```bash
# 开发模式
uv run python -m src.web_app

# 浏览器访问
# http://127.0.0.1:5000
```

### 7. 手动执行每日任务

```bash
# 执行一次完整的每日任务
uv run python -m src.daily_once

# 或启动定时调度器
uv run python -m src.main
```

---

## GitHub仓库设置

### 1. 创建GitHub仓库

1. 访问 https://github.com/new
2. 填写仓库信息：
   - **Repository name**: `ai-etf-trader`
   - **Description**: `AI-driven ETF automated trading system`
   - **Visibility**: Public
   - **不要** 初始化README（本地已有）

### 2. 本地初始化Git

```bash
cd ai-etf-trader
git init
git config user.name "Your Name"
git config user.email "your.email@example.com"
```

### 3. 添加远程仓库并推送

```bash
git add .
git commit -m "Initial commit: AI ETF Trader v1.0.0"
git branch -M main
git remote add origin https://github.com/yourusername/ai-etf-trader.git
git push -u origin main
```

### 4. 配置GitHub Secrets（用于CI/CD）

访问 **Settings > Secrets and variables > Actions**，添加以下secrets：

```
DOCKER_USERNAME=your_docker_username
DOCKER_PASSWORD=your_docker_password
```

### 5. 验证GitHub Actions

- 访问 **Actions** 标签页
- 应该看到 `Tests` 和 `Deploy` 工作流
- 推送代码后会自动运行测试

---

## Docker部署

### 1. 本地Docker测试

```bash
# 构建镜像
docker build -t ai-etf-trader:latest .

# 运行容器
docker run -d \
  --name ai-etf-trader \
  -p 5000:5000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  ai-etf-trader:latest

# 查看日志
docker logs -f ai-etf-trader

# 停止容器
docker stop ai-etf-trader
```

### 2. 使用Docker Compose

```bash
# 启动所有服务（包括Nginx）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f ai-etf-trader

# 停止服务
docker-compose down

# 清理所有数据
docker-compose down -v
```

### 3. 验证Docker部署

```bash
# 检查容器健康状态
docker ps

# 测试API
curl http://127.0.0.1:5000/api/performance

# 查看容器日志
docker logs ai-etf-trader
```

---

## Linux服务器部署

### 1. 服务器准备（Ubuntu 22.04）

```bash
# SSH连接到服务器
ssh root@your_server_ip

# 更新系统
apt-get update && apt-get upgrade -y

# 安装基础工具
apt-get install -y git curl wget unzip python3.11 python3.11-venv sqlite3
```

### 2. 使用自动部署脚本

```bash
# 克隆项目
cd /opt
git clone https://github.com/yourusername/ai-etf-trader.git
cd ai-etf-trader

# 运行部署脚本
sudo bash deploy/deploy_ubuntu22.sh

# 脚本会自动：
# - 安装Python 3.11和依赖
# - 创建虚拟环境
# - 配置Systemd服务
# - 配置Nginx反向代理
```

### 3. 手动部署步骤

如果不使用自动脚本，按以下步骤手动部署：

#### 3.1 创建应用用户

```bash
sudo useradd -m -s /bin/bash aiuser
sudo mkdir -p /opt/ai-etf-trader
sudo chown -R aiuser:aiuser /opt/ai-etf-trader
```

#### 3.2 克隆项目

```bash
cd /opt/ai-etf-trader
sudo -u aiuser git clone https://github.com/yourusername/ai-etf-trader.git .
```

#### 3.3 创建虚拟环境

```bash
sudo -u aiuser python3.11 -m venv venv
sudo -u aiuser venv/bin/pip install --upgrade pip wheel
```

#### 3.4 安装依赖

```bash
# 安装uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# 使用uv安装依赖
sudo -u aiuser /root/.cargo/bin/uv sync --frozen
```

#### 3.5 配置环境变量

```bash
sudo nano /opt/ai-etf-trader/.env

# 填入必要的配置：
# OPENAI_API_KEY=your_key
# BASE_URL=https://open.bigmodel.cn/api/paas/v4
# MODEL_NAME=glm-4-air
# ETF_LIST=510050,159915,510300
```

#### 3.6 配置Systemd服务

```bash
sudo nano /etc/systemd/system/ai-etf-web.service
```

```ini
[Unit]
Description=AI ETF Trader Web Service
After=network.target

[Service]
Type=simple
User=aiuser
Group=aiuser
WorkingDirectory=/opt/ai-etf-trader
EnvironmentFile=/opt/ai-etf-trader/.env
ExecStart=/opt/ai-etf-trader/venv/bin/gunicorn -b 127.0.0.1:5000 -w 2 src.web_app:app
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```

```bash
# 启用并启动服务
sudo systemctl daemon-reload
sudo systemctl enable ai-etf-web
sudo systemctl start ai-etf-web
sudo systemctl status ai-etf-web
```

#### 3.7 配置Nginx反向代理

```bash
sudo nano /etc/nginx/conf.d/ai-etf.conf
```

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

```bash
# 测试Nginx配置
sudo nginx -t

# 重启Nginx
sudo systemctl restart nginx
```

### 4. 验证部署

```bash
# 检查服务状态
sudo systemctl status ai-etf-web

# 查看服务日志
sudo journalctl -u ai-etf-web -f

# 测试API
curl http://127.0.0.1/api/performance

# 检查Nginx日志
sudo tail -f /var/log/nginx/access.log
```

---

## 生产环境配置

### 1. 配置HTTPS（Let's Encrypt）

```bash
# 安装Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# 申请证书
sudo certbot certonly --nginx -d your_domain.com

# 更新Nginx配置
sudo nano /etc/nginx/conf.d/ai-etf.conf
```

```nginx
server {
    listen 80;
    server_name your_domain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name your_domain.com;

    ssl_certificate /etc/letsencrypt/live/your_domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your_domain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 300;
    }
}
```

```bash
# 重启Nginx
sudo systemctl restart nginx

# 自动续期证书
sudo systemctl enable certbot.timer
```

### 2. 配置定时任务

```bash
# 编辑crontab
sudo crontab -e

# 添加每日17:00执行的任务
0 17 * * 1-5 cd /opt/ai-etf-trader && /opt/ai-etf-trader/venv/bin/python -m src.daily_once >> /opt/ai-etf-trader/logs/cron.log 2>&1

# 添加每周日备份
0 2 * * 0 /opt/ai-etf-trader/backup.sh
```

### 3. 配置日志轮转

```bash
sudo nano /etc/logrotate.d/ai-etf-trader
```

```
/opt/ai-etf-trader/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    notifempty
    create 0640 aiuser aiuser
    sharedscripts
}
```

### 4. 配置防火墙

```bash
# 仅允许必要的端口
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 5. 配置备份

创建备份脚本 `/opt/ai-etf-trader/backup.sh`：

```bash
#!/bin/bash
BACKUP_DIR="/backup/ai-etf-trader"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

mkdir -p $BACKUP_DIR

# 备份数据库
cp /opt/ai-etf-trader/data/etf_data.db $BACKUP_DIR/etf_data_$TIMESTAMP.db
cp /opt/ai-etf-trader/data/trade_history.db $BACKUP_DIR/trade_history_$TIMESTAMP.db

# 备份决策日志
tar -czf $BACKUP_DIR/decisions_$TIMESTAMP.tar.gz /opt/ai-etf-trader/decisions/

# 删除7天前的备份
find $BACKUP_DIR -type f -mtime +7 -delete

echo "Backup completed at $TIMESTAMP"
```

```bash
# 设置执行权限
sudo chmod +x /opt/ai-etf-trader/backup.sh
```

---

## 监控和维护

### 1. 系统监控

```bash
# 查看CPU和内存使用
htop

# 查看磁盘使用
df -h

# 查看进程
ps aux | grep python

# 查看网络连接
netstat -tlnp | grep 5000
```

### 2. 日志监控

```bash
# 实时查看Web服务日志
sudo journalctl -u ai-etf-web -f

# 查看最近100行日志
sudo journalctl -u ai-etf-web -n 100

# 查看应用日志
tail -f /opt/ai-etf-trader/logs/daily.log

# 查看Nginx日志
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### 3. 健康检查

```bash
# 检查Web服务
curl -s http://127.0.0.1:5000/api/performance | jq .

# 检查数据库
sqlite3 /opt/ai-etf-trader/data/etf_data.db "SELECT COUNT(*) FROM daily_equity;"

# 检查最新交易
sqlite3 /opt/ai-etf-trader/data/trade_history.db "SELECT * FROM trades ORDER BY date DESC LIMIT 5;"
```

### 4. 定期更新

```bash
# 更新系统包
sudo apt-get update && sudo apt-get upgrade -y

# 更新Python依赖
cd /opt/ai-etf-trader
sudo -u aiuser uv sync --upgrade

# 重启服务
sudo systemctl restart ai-etf-web
```

---

## 故障排查

### 问题1：Web服务无法启动

```bash
# 检查日志
sudo journalctl -u ai-etf-web -n 50

# 检查端口占用
sudo lsof -i :5000

# 检查.env文件
cat /opt/ai-etf-trader/.env

# 检查权限
ls -la /opt/ai-etf-trader/
```

### 问题2：API调用超时

```bash
# 增加超时时间
# 编辑 .env，修改 TIMEOUT_SECONDS=300

# 检查网络连接
curl -v https://open.bigmodel.cn/api/paas/v4

# 检查API密钥
echo $OPENAI_API_KEY
```

### 问题3：数据库锁定

```bash
# 检查数据库进程
lsof /opt/ai-etf-trader/data/etf_data.db

# 重启服务
sudo systemctl restart ai-etf-web

# 检查数据库完整性
sqlite3 /opt/ai-etf-trader/data/etf_data.db "PRAGMA integrity_check;"
```

### 问题4：磁盘空间不足

```bash
# 检查磁盘使用
du -sh /opt/ai-etf-trader/*

# 清理日志
sudo rm /opt/ai-etf-trader/logs/*.log

# 清理临时文件
sudo rm -rf /opt/ai-etf-trader/tmp/*

# 清理旧备份
find /backup/ai-etf-trader -type f -mtime +30 -delete
```

### 问题5：Nginx 502 Bad Gateway

```bash
# 检查上游服务
curl http://127.0.0.1:5000/

# 检查Nginx日志
sudo tail -f /var/log/nginx/error.log

# 检查Systemd服务
sudo systemctl status ai-etf-web

# 重启服务
sudo systemctl restart ai-etf-web
sudo systemctl restart nginx
```

---

## 性能优化

### 1. Gunicorn配置优化

编辑 `/etc/systemd/system/ai-etf-web.service`：

```ini
ExecStart=/opt/ai-etf-trader/venv/bin/gunicorn \
    -b 127.0.0.1:5000 \
    -w 4 \
    -k gevent \
    --worker-connections 1000 \
    --timeout 300 \
    --access-logfile /opt/ai-etf-trader/logs/access.log \
    src.web_app:app
```

### 2. Nginx缓存配置

```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=100m inactive=60m;

location /api/ {
    proxy_cache api_cache;
    proxy_cache_valid 200 10m;
    proxy_cache_bypass $http_pragma $http_authorization;
    
    proxy_pass http://127.0.0.1:5000;
    # ... 其他配置
}
```

### 3. 数据库优化

```bash
# 定期优化数据库
sqlite3 /opt/ai-etf-trader/data/etf_data.db "VACUUM;"

# 创建索引
sqlite3 /opt/ai-etf-trader/data/etf_data.db "CREATE INDEX IF NOT EXISTS idx_date ON daily_equity(date);"
```

---

## 常见问题FAQ

**Q: 如何更改交易时间？**
A: 编辑 `.env` 文件，修改 `SCHEDULE_TIME=17:00`

**Q: 如何添加新的ETF？**
A: 编辑 `.env` 文件，修改 `ETF_LIST=510050,159915,510300,...`

**Q: 如何查看交易历史？**
A: 访问 `http://your_domain/api/trades`

**Q: 如何备份数据？**
A: 运行 `/opt/ai-etf-trader/backup.sh`

**Q: 如何重置系统？**
A: 删除 `data/` 目录中的数据库文件，重启服务

---

## 支持和反馈

- 📖 [项目文档](README.md)
- 🐛 [报告问题](https://github.com/yourusername/ai-etf-trader/issues)
- 💬 [讨论](https://github.com/yourusername/ai-etf-trader/discussions)

---

**最后更新**: 2024年12月
**版本**: 1.0.0
