# AI ETF Trader - 快速部署指南

## 🚀 5分钟快速开始

### 第1步：准备本地环境（2分钟）

```bash
# 1. 克隆或进入项目目录
cd ai-etf-trader

# 2. 复制环境配置
cp .env.example .env

# 3. 编辑 .env，填入你的API密钥
nano .env  # 或用你喜欢的编辑器

# 关键配置项：
# OPENAI_API_KEY=your_actual_key
# BASE_URL=https://open.bigmodel.cn/api/paas/v4
# MODEL_NAME=glm-4-air
# ETF_LIST=510050,159915,510300
```

### 第2步：选择部署方式

#### 🐳 方式A：Docker Compose（最简单，推荐）

```bash
# 1. 确保已安装Docker和Docker Compose
docker --version
docker-compose --version

# 2. 启动应用（包括Web服务和Nginx）
docker-compose up -d

# 3. 查看日志
docker-compose logs -f ai-etf-trader

# 4. 访问应用
# 浏览器打开: http://localhost:5000
# 或: http://localhost/（通过Nginx）

# 5. 停止应用
docker-compose down
```

#### 🐳 方式B：Docker单容器

```bash
# 1. 构建镜像
docker build -t ai-etf-trader:latest .

# 2. 运行容器
docker run -d \
  --name ai-etf-trader \
  -p 5000:5000 \
  --env-file .env \
  -v $(pwd)/data:/app/data \
  -v $(pwd)/logs:/app/logs \
  ai-etf-trader:latest

# 3. 查看日志
docker logs -f ai-etf-trader

# 4. 访问应用
# http://localhost:5000

# 5. 停止容器
docker stop ai-etf-trader
docker rm ai-etf-trader
```

#### 🐧 方式C：Linux服务器（Ubuntu 22.04）

```bash
# 1. SSH连接到服务器
ssh root@your_server_ip

# 2. 克隆项目
cd /opt
git clone https://github.com/yourusername/ai-etf-trader.git
cd ai-etf-trader

# 3. 运行自动部署脚本（一键部署）
sudo bash deploy/deploy_ubuntu22.sh

# 4. 编辑配置文件
sudo nano /opt/ai-etf-trader/.env

# 5. 启动服务
sudo systemctl start ai-etf-web
sudo systemctl status ai-etf-web

# 6. 访问应用
# http://your_server_ip/
```

#### 💻 方式D：本地开发环境

```bash
# 1. 安装uv（如果未安装）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. 安装依赖
uv sync

# 3. 启动Web服务
uv run python -m src.web_app

# 4. 在另一个终端执行每日任务
uv run python -m src.daily_once

# 5. 访问应用
# http://127.0.0.1:5000
```

---

## 📋 部署检查清单

### 部署前检查

- [ ] 已复制 `.env.example` 为 `.env`
- [ ] 已填入 `OPENAI_API_KEY`
- [ ] 已配置 `ETF_LIST`（ETF代码）
- [ ] 已设置 `SCHEDULE_TIME`（执行时间）
- [ ] 已设置 `INITIAL_CAPITAL`（初始资金）

### 部署后验证

```bash
# 检查Web服务是否运行
curl http://localhost:5000/api/performance

# 检查数据库
sqlite3 data/etf_data.db "SELECT COUNT(*) FROM daily_equity;"

# 查看日志
tail -f logs/daily.log
```

---

## 🔧 常见问题

### Q1: 如何修改交易时间？
```bash
# 编辑 .env 文件
SCHEDULE_TIME=17:00  # 改为你想要的时间（24小时制）
```

### Q2: 如何添加新的ETF？
```bash
# 编辑 .env 文件
ETF_LIST=510050,159915,510300,512100,512660  # 添加新代码
```

### Q3: 如何查看交易历史？
```bash
# 访问API
curl http://localhost:5000/api/trades

# 或查询数据库
sqlite3 data/trade_history.db "SELECT * FROM trades LIMIT 10;"
```

### Q4: Docker容器无法启动？
```bash
# 查看错误日志
docker logs ai-etf-trader

# 检查.env文件
cat .env

# 重新构建镜像
docker build --no-cache -t ai-etf-trader:latest .
```

### Q5: 如何重置系统？
```bash
# 删除数据库（谨慎操作！）
rm data/etf_data.db data/trade_history.db

# 重启服务
docker-compose restart ai-etf-trader
# 或
sudo systemctl restart ai-etf-web
```

---

## [object Object]端点速览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/` | GET | Web仪表盘 |
| `/api/performance` | GET | 账户净值曲线 |
| `/api/portfolio` | GET | 资产和持仓 |
| `/api/trades` | GET | 交易记录 |
| `/api/decisions` | GET | AI决策历史 |
| `/api/etf_tickers` | GET | ETF实时行情 |
| `/api/qlib/factors` | GET | Qlib因子数据 |

---

## 🌐 配置域名和HTTPS（可选）

### 1. 配置域名DNS

在域名提供商处添加A记录：
```
A  your_domain.com  your_server_ip
```

### 2. 配置HTTPS（Let's Encrypt）

```bash
# 安装Certbot
sudo apt-get install -y certbot python3-certbot-nginx

# 申请证书
sudo certbot certonly --nginx -d your_domain.com

# Nginx会自动配置SSL
# 访问: https://your_domain.com
```

---

## 📈 性能监控

### 查看系统资源使用

```bash
# CPU和内存
htop

# 磁盘使用
df -h

# 网络连接
netstat -tlnp | grep 5000
```

### 查看应用日志

```bash
# Docker方式
docker-compose logs -f ai-etf-trader

# Linux服务方式
sudo journalctl -u ai-etf-web -f

# 应用日志
tail -f logs/daily.log
```

---

## 🔄 定时任务配置

### Docker方式（自动）

Docker Compose会自动运行Web服务，但每日任务需要手动配置：

```bash
# 进入容器
docker-compose exec ai-etf-trader bash

# 运行每日任务
python -m src.daily_once
```

### Linux服务方式

```bash
# 编辑crontab
sudo crontab -e

# 添加每日17:00执行的任务
0 17 * * 1-5 cd /opt/ai-etf-trader && /opt/ai-etf-trader/venv/bin/python -m src.daily_once >> /opt/ai-etf-trader/logs/cron.log 2>&1
```

---

## 📚 详细文档

- 📖 [完整部署指南](DEPLOYMENT_GUIDE.md) - 详细的部署步骤和故障排查
- ⚙️ [环境配置说明](.env.example) - 所有配置项的详细说明
- 🎯 [项目文档](README.md) - 项目概述和功能说明
- 📊 [项目状态](PROJECT_STATUS.md) - 项目完善情况报告

---

## 🆘 需要帮助？

1. 查看 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 的故障排查部分
2. 检查日志文件：`logs/daily.log`
3. 查看Docker日志：`docker-compose logs`
4. 查看Systemd日志：`sudo journalctl -u ai-etf-web`

---

## ✅ 部署完成标志

当你看到以下信息时，说明部署成功：

```
✅ Web服务运行在 http://localhost:5000
✅ 数据库已初始化
✅ 可以访问Web仪表盘
✅ API端点正常响应
✅ 日志文件正常生成
```

---

**祝部署顺利！** 🚀

有任何问题，请参考 [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md) 或查看日志。


