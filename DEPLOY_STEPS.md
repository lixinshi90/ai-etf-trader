# AI ETF Trader - 部署步骤（完整版）

**项目状态**: ✅ 已完善，可部署上线  
**最后更新**: 2024年12月13日

---

## 📋 目录

1. [第一阶段：GitHub仓库设置](#第一阶段github仓库设置)
2. [第二阶段：本地环境准备](#第二阶段本地环境准备)
3. [第三阶段：选择部署方式](#第三阶段选择部署方式)
4. [第四阶段：验证部署](#第四阶段验证部署)
5. [第五阶段：生产环境配置](#第五阶段生产环境配置)

---

## 第一阶段：GitHub仓库设置

### 步骤1.1：创建GitHub仓库

1. 访问 https://github.com/new
2. 填写以下信息：
   - **Repository name**: `ai-etf-trader`
   - **Description**: `AI-driven ETF automated trading system`
   - **Visibility**: Public（便于获取GitHub地址）
   - **Initialize this repository with**: 不选择（本地已有文件）

3. 点击 "Create repository"

### 步骤1.2：初始化本地Git仓库

```bash
cd ai-etf-trader

# 初始化Git
git init

# 配置用户信息
git config user.name "Your Name"
git config user.email "your.email@example.com"

# 添加所有文件
git add .

# 首次提交
git commit -m "Initial commit: AI ETF Trader v1.0.0"

# 重命名主分支为main
git branch -M main
```

### 步骤1.3：连接到GitHub仓库

```bash
# 添加远程仓库（替换yourusername）
git remote add origin https://github.com/yourusername/ai-etf-trader.git

# 推送到GitHub
git push -u origin main

# 验证推送成功
git log --oneline -5
```

### 步骤1.4：配置GitHub Secrets（用于CI/CD）

1. 访问 https://github.com/yourusername/ai-etf-trader/settings/secrets/actions
2. 点击 "New repository secret"
3. 添加以下secrets：

```
DOCKER_USERNAME = your_docker_username
DOCKER_PASSWORD = your_docker_password
```

### 步骤1.5：验证GitHub Actions

1. 访问 https://github.com/yourusername/ai-etf-trader/actions
2. 应该看到两个工作流：
   - ✅ Tests (tests.yml)
   - ✅ Deploy (deploy.yml)
3. 推送代码后会自动运行测试

---

## 第二阶段：本地环境准备

### 步骤2.1：复制环境配置

```bash
# 复制示例配置文件
cp .env.example .env

# 编辑配置文件（使用你喜欢的编辑器）
nano .env
# 或
code .env
# 或
vim .env
```

### 步骤2.2：填写关键配置项

编辑 `.env` 文件，填入以下必需的配置：

```env
# ---- LLM配置 ----
OPENAI_API_KEY=your_actual_api_key_here
BASE_URL=https://open.bigmodel.cn/api/paas/v4
MODEL_NAME=glm-4-air

# ---- ETF配置 ----
CORE_ETF_LIST=510050,159915,510300
OBSERVE_ETF_LIST=512100,512660,512800
ETF_LIST=510050,159915,510300,512100,512660,512800

# ---- 策略配置 ----
STRATEGY_MODE=AGGRESSIVE
SCHEDULE_TIME=17:00

# ---- 账户配置 ----
INITIAL_CAPITAL=100000

# ---- 其他配置 ----
LOG_LEVEL=INFO
FLASK_DEBUG=false
```

### 步骤2.3：验证配置

```bash
# 检查.env文件是否正确
cat .env

# 确保没有暴露敏感信息
grep -v "^#" .env | grep -v "^$"
```

---

## 第三阶段：选择部署方式

### 方式A：Docker Compose（推荐，最简单）

#### A1：安装Docker和Docker Compose

```bash
# Windows/Mac: 下载 Docker Desktop
# https://www.docker.com/products/docker-desktop

# Linux (Ubuntu):
sudo apt-get update
sudo apt-get install -y docker.io docker-compose
sudo usermod -aG docker $USER
```

#### A2：启动应用

```bash
# 进入项目目录
cd ai-etf-trader

# 启动所有服务（Web + Nginx）
docker-compose up -d

# 查看运行状态
docker-compose ps

# 查看日志
docker-compose logs -f ai-etf-trader
```

#### A3：访问应用

```bash
# 方式1：直接访问Web服务
curl http://localhost:5000

# 方式2：通过Nginx访问
curl http://localhost

# 方式3：浏览器打开
# http://localhost:5000
# 或
# http://localhost
```

#### A4：停止应用

```bash
# 停止所有服务
docker-compose down

# 停止并删除所有数据
docker-compose down -v
```

---

### 方式B：Linux服务器（Ubuntu 22.04）

#### B1：服务器准备

```bash
# SSH连接到服务器
ssh root@your_server_ip

# 更新系统
apt-get update && apt-get upgrade -y

# 安装基础工具
apt-get install -y git curl wget unzip python3.11 python3.11-venv sqlite3 nginx
```

#### B2：克隆项目

```bash
# 进入/opt目录
cd /opt

# 克隆项目
git clone https://github.com/yourusername/ai-etf-trader.git
cd ai-etf-trader
```

#### B3：运行自动部署脚本（推荐）

```bash
# 运行一键部署脚本
sudo bash deploy/deploy_ubuntu22.sh

# 脚本会自动：
# - 安装Python 3.11和依赖
# - 创建虚拟环境
# - 安装Python包
# - 配置Systemd服务
# - 配置Nginx反向代理
# - 启动服务
```

#### B4：配置环境变量

```bash
# 编辑.env文件
sudo nano /opt/ai-etf-trader/.env

# 填入必要的配置（见步骤2.2）
```

#### B5：启动服务

```bash
# 启动Web服务
sudo systemctl start ai-etf-web

# 查看服务状态
sudo systemctl status ai-etf-web

# 启动Nginx
sudo systemctl start nginx
sudo systemctl status nginx

# 查看日志
sudo journalctl -u ai-etf-web -f
```

#### B6：访问应用

```bash
# 本地测试
curl http://127.0.0.1:5000

# 远程访问
curl http://your_server_ip

# 浏览器打开
# http://your_server_ip
```

---

### 方式C：本地开发环境

#### C1：安装uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

#### C2：安装依赖

```bash
# 进入项目目录
cd ai-etf-trader

# 安装所有依赖
uv sync --all-extras
```

#### C3：启动Web服务

```bash
# 启动Flask Web应用
uv run python -m src.web_app

# 输出应该显示：
# * Running on http://127.0.0.1:5000
```

#### C4：在另一个终端执行每日任务

```bash
# 打开新终端，进入项目目录
cd ai-etf-trader

# 执行一次每日任务
uv run python -m src.daily_once

# 或启动定时调度器
uv run python -m src.main
```

#### C5：访问应用

```bash
# 浏览器打开
# http://127.0.0.1:5000
```

---

## 第四阶段：验证部署

### 步骤4.1：检查Web服务

```bash
# 测试API端点
curl http://localhost:5000/api/performance
curl http://localhost:5000/api/portfolio
curl http://localhost:5000/api/etf_tickers

# 或在浏览器中打开
# http://localhost:5000
```

### 步骤4.2：检查数据库

```bash
# 查询每日净值
sqlite3 data/etf_data.db "SELECT COUNT(*) FROM daily_equity;"

# 查询交易记录
sqlite3 data/trade_history.db "SELECT COUNT(*) FROM trades;"

# 查看最新交易
sqlite3 data/trade_history.db "SELECT * FROM trades ORDER BY date DESC LIMIT 5;"
```

### 步骤4.3：检查日志

```bash
# 查看应用日志
tail -f logs/daily.log

# Docker方式
docker-compose logs -f ai-etf-trader

# Linux服务方式
sudo journalctl -u ai-etf-web -f
```

### 步骤4.4：检查系统资源

```bash
# 查看CPU和内存使用
htop

# 查看磁盘使用
df -h

# 查看进程
ps aux | grep python
```

---

## 第五阶段：生产环境配置

### 步骤5.1：配置HTTPS（Let's Encrypt）

```bash
# 安装Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# 申请证书（替换your_domain.com）
sudo certbot certonly --nginx -d your_domain.com

# 更新Nginx配置
sudo nano /etc/nginx/conf.d/ai-etf.conf

# 添加SSL配置（见下方）
```

**Nginx SSL配置示例**:

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

### 步骤5.2：配置定时任务

```bash
# 编辑crontab
sudo crontab -e

# 添加每日17:00执行的任务（周一到周五）
0 17 * * 1-5 cd /opt/ai-etf-trader && /opt/ai-etf-trader/venv/bin/python -m src.daily_once >> /opt/ai-etf-trader/logs/cron.log 2>&1

# 添加每周日备份
0 2 * * 0 /opt/ai-etf-trader/backup.sh
```

### 步骤5.3：配置日志轮转

```bash
# 创建logrotate配置
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
}
```

### 步骤5.4：配置防火墙

```bash
# 仅允许必要的端口
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp    # SSH
sudo ufw allow 80/tcp    # HTTP
sudo ufw allow 443/tcp   # HTTPS
sudo ufw enable
```

### 步骤5.5：配置备份

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

## 🎯 部署完成检查清单

### 部署前

- [ ] 已创建GitHub仓库
- [ ] 已初始化本地Git仓库
- [ ] 已推送代码到GitHub
- [ ] 已配置GitHub Secrets
- [ ] 已复制.env.example为.env
- [ ] 已填入所有必需的配置项

### 部署中

- [ ] 已选择部署方式（Docker/Linux/本地）
- [ ] 已安装必需的工具
- [ ] 已克隆/拉取最新代码
- [ ] 已启动应用服务

### 部署后

- [ ] Web服务正常运行
- [ ] 可以访问Web仪表盘
- [ ] API端点正常响应
- [ ] 数据库已初始化
- [ ] 日志文件正常生成
- [ ] 定时任务已配置（如需要）
- [ ] HTTPS已配置（生产环境）
- [ ] 备份策略已配置（生产环境）

---

## 📞 故障排查

### 问题1：Web服务无法启动

```bash
# 查看错误日志
docker-compose logs ai-etf-trader
# 或
sudo journalctl -u ai-etf-web -n 50

# 检查.env文件
cat .env

# 检查端口占用
sudo lsof -i :5000
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

### 问题3：数据库错误

```bash
# 检查数据库完整性
sqlite3 data/etf_data.db "PRAGMA integrity_check;"

# 重建数据库
rm data/etf_data.db
# 重启服务，数据库会自动重建
```

---

## 📚 相关文档

| 文档 | 用途 |
|------|------|
| [README.md](README.md) | 项目概述和功能说明 |
| [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) | 详细部署指南和故障排查 |
| [QUICK_START_DEPLOYMENT.md](QUICK_START_DEPLOYMENT.md) | 快速开始指南 |
| [.env.example](.env.example) | 环境变量配置说明 |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | 项目完善情况报告 |

---

## ✨ 部署成功标志

当你看到以下信息时，说明部署成功：

```
✅ Web服务运行在 http://localhost:5000 (或你的域名)
✅ 可以访问Web仪表盘
✅ API端点正常响应
✅ 数据库已初始化
✅ 日志文件正常生成
✅ 定时任务正常执行（如已配置）
```

---

## 🚀 下一步

1. **监控应用**：定期检查日志和系统资源
2. **更新代码**：定期拉取最新更新
3. **备份数据**：定期备份数据库
4. **优化配置**：根据实际情况调整参数

---

**祝部署顺利！** 🎉

有任何问题，请查看 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 或检查日志文件。


