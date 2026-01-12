# 部署指南 - ETF行情显示功能 & Tooltips增强

## 概述

本文档说明如何将以下更新部署到VPS服务器：

1. **ETF行情速览卡片** - 实时显示所有关注ETF的最新行情
2. **关键指标Tooltips** - 为KPI指标添加交互式提示信息

---

## 更新内容清单

### 后端 (src/web_app.py)
✅ **已存在** `/api/etf_tickers` 接口
- 功能：获取ETF_LIST中所有ETF的最新行情快照
- 返回字段：代码、名称、最新价、涨跌额、涨跌幅、成交量
- 数据来源：etf_data.db 数据库

### 前端 (templates/index.html)
✅ **新增** ETF行情卡片渲染逻辑
- 新增 `loadTickers()` 函数，定时获取并渲染行情数据
- 支持红绿涨跌配色（↑绿色/↓红色）
- 集成到 `loadAll()` 自动刷新流程（10秒更新一次）

✅ **新增** 关键指标Tooltips
- 为5个KPI指标添加交互式提示
- 指标包括：总交易次数、胜率、总收益率、年化收益率、最大回撤
- 提示内容包含计算公式和详细说明

---

## 本地测试步骤

### 1. 验证后端API
```bash
# 启动Web服务
conda activate ai-etf-trader
python -m src.web_app

# 在另一个终端测试API
curl http://127.0.0.1:5000/api/etf_tickers | python -m json.tool
```

预期输出示例：
```json
[
  {
    "code": "510050",
    "name": "50ETF",
    "date": "2025-12-03",
    "price": 2.345,
    "change": 0.015,
    "pct_change": 0.65,
    "volume": 123456789
  },
  ...
]
```

### 2. 验证前端页面
- 打开浏览器：`http://127.0.0.1:5000`
- 查看"ETF行情速览"卡片是否正常显示
- 鼠标悬停在KPI指标标签上，验证Tooltips是否显示

---

## VPS部署步骤

### 第一步：上传更新文件

在**本地**执行：
```bash
# 进入项目目录
cd "D:\数据备份\量化交易\《期末综合实验报告》"

# 只上传修改的文件
scp templates/index.html your_user@YOUR_SERVER_IP:/tmp/
scp src/web_app.py your_user@YOUR_SERVER_IP:/tmp/
```

### 第二步：在服务器上更新文件

SSH连接到服务器：
```bash
ssh your_user@YOUR_SERVER_IP

# 备份原文件
sudo cp /opt/ai-etf-trader/templates/index.html /opt/ai-etf-trader/templates/index.html.backup
sudo cp /opt/ai-etf-trader/src/web_app.py /opt/ai-etf-trader/src/web_app.py.backup

# 复制新文件
sudo cp /tmp/index.html /opt/ai-etf-trader/templates/
sudo cp /tmp/web_app.py /opt/ai-etf-trader/src/

# 验证文件权限
sudo chown -R www-data:www-data /opt/ai-etf-trader/templates/
sudo chown -R www-data:www-data /opt/ai-etf-trader/src/
```

### 第三步：重启服务

```bash
# 重启Flask Web服务
sudo systemctl restart ai-etf-web

# 验证服务状态
sudo systemctl status ai-etf-web

# 检查日志
sudo journalctl -u ai-etf-web -n 50 -f
```

### 第四步：验证部署

```bash
# 健康检查
curl http://YOUR_SERVER_IP/health

# 测试ETF行情API
curl http://YOUR_SERVER_IP/api/etf_tickers | head -c 500

# 在浏览器中打开仪表盘
# http://YOUR_SERVER_IP
```

---

## 快速部署脚本

如果需要一键部署，可以在服务器上运行以下脚本：

```bash
#!/bin/bash
set -e

echo "🔄 开始部署ETF行情功能更新..."

# 备份原文件
echo "📦 备份原文件..."
sudo cp /opt/ai-etf-trader/templates/index.html /opt/ai-etf-trader/templates/index.html.backup.$(date +%s)
sudo cp /opt/ai-etf-trader/src/web_app.py /opt/ai-etf-trader/src/web_app.py.backup.$(date +%s)

# 更新文件（假设已通过scp上传到/tmp/）
echo "📝 更新文件..."
sudo cp /tmp/index.html /opt/ai-etf-trader/templates/
sudo cp /tmp/web_app.py /opt/ai-etf-trader/src/

# 设置权限
sudo chown -R www-data:www-data /opt/ai-etf-trader/templates/
sudo chown -R www-data:www-data /opt/ai-etf-trader/src/

# 重启服务
echo "🔄 重启服务..."
sudo systemctl restart ai-etf-web

# 等待服务启动
sleep 3

# 验证
echo "✅ 验证部署..."
if curl -s http://localhost/health | grep -q "ok"; then
    echo "✅ 部署成功！"
    curl -s http://localhost/api/etf_tickers | python3 -m json.tool | head -20
else
    echo "❌ 部署失败，请检查日志"
    sudo journalctl -u ai-etf-web -n 20
    exit 1
fi
```

保存为 `deploy_update.sh`，然后：
```bash
chmod +x deploy_update.sh
./deploy_update.sh
```

---

## 故障排查

### 问题1：ETF行情卡片显示"正在加载行情数据..."

**原因**：API返回为空或数据库中没有ETF数据

**解决方案**：
```bash
# 检查etf_data.db是否存在
ls -lh /opt/ai-etf-trader/data/etf_data.db

# 检查数据库中是否有数据
sqlite3 /opt/ai-etf-trader/data/etf_data.db "SELECT name FROM sqlite_master WHERE type='table';"

# 查看最新的ETF数据
sqlite3 /opt/ai-etf-trader/data/etf_data.db "SELECT * FROM etf_510050 ORDER BY 日期 DESC LIMIT 1;"
```

### 问题2：Tooltips不显示

**原因**：CSS未正确加载或浏览器缓存

**解决方案**：
```bash
# 清除浏览器缓存（Ctrl+Shift+Delete）
# 或使用硬刷新（Ctrl+Shift+R）

# 检查HTML文件是否包含tooltip样式
grep -n "tooltip-wrapper" /opt/ai-etf-trader/templates/index.html
```

### 问题3：服务重启后页面无法访问

**原因**：Flask服务未正确启动

**解决方案**：
```bash
# 查看详细错误日志
sudo journalctl -u ai-etf-web -n 100 -f

# 手动启动服务以查看错误
cd /opt/ai-etf-trader
/opt/ai-etf-trader/venv/bin/python -m src.web_app

# 检查Python依赖
/opt/ai-etf-trader/venv/bin/pip list | grep -E "flask|pandas"
```

---

## 回滚步骤

如果部署出现问题，可以快速回滚到之前的版本：

```bash
# 恢复备份文件
sudo cp /opt/ai-etf-trader/templates/index.html.backup /opt/ai-etf-trader/templates/index.html
sudo cp /opt/ai-etf-trader/src/web_app.py.backup /opt/ai-etf-trader/src/web_app.py

# 重启服务
sudo systemctl restart ai-etf-web

# 验证
curl http://YOUR_SERVER_IP/health
```

---

## 性能优化建议

1. **缓存ETF行情数据**
   - 在前端添加本地缓存，减少API调用
   - 建议缓存时间：5-10秒

2. **数据库索引**
   ```sql
   CREATE INDEX IF NOT EXISTS idx_etf_510050_date ON etf_510050(日期 DESC);
   ```

3. **API响应压缩**
   - 在Nginx配置中启用gzip压缩
   ```nginx
   gzip on;
   gzip_types application/json;
   gzip_min_length 1000;
   ```

---

## 监控与日志

### 查看实时日志
```bash
# Flask应用日志
sudo journalctl -u ai-etf-web -f

# Nginx访问日志
sudo tail -f /var/log/nginx/access.log

# Nginx错误日志
sudo tail -f /var/log/nginx/error.log
```

### 性能监控
```bash
# 监控服务进程
watch -n 1 'ps aux | grep python'

# 查看磁盘使用
df -h /opt/ai-etf-trader/

# 查看数据库大小
du -sh /opt/ai-etf-trader/data/
```

---

## 下一步计划

- [ ] 添加ETF行情的历史对比（日/周/月）
- [ ] 实现行情数据的本地缓存策略
- [ ] 添加行情预警功能（涨跌幅超过阈值时提醒）
- [ ] 优化移动端显示效果

---

## 联系与支持

如有部署问题，请检查：
1. ✅ 服务器网络连接
2. ✅ Python依赖是否完整
3. ✅ 数据库文件是否存在
4. ✅ 文件权限是否正确
5. ✅ 日志中是否有错误信息


