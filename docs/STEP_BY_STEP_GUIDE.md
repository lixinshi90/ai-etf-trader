# 📖 分步操作指南

## 🎯 目标

1. ✅ 创建项目副本用于开源部署
2. ✅ 删除期权与 IV 相关功能
3. ✅ 检查项目是否符合期末报告要求
4. ✅ 解决 akshare 数据源连接问题

---

## 第一步：创建项目副本

### 步骤 1.1：复制项目目录

```bash
# 进入项目的上一级目录
cd ..

# 复制项目
cp -r ai-etf-trader ai-etf-trader-opensource

# 进入副本目录
cd ai-etf-trader-opensource

# 验证
ls -la
```

**Windows 用户：**
```powershell
# 使用 PowerShell
Copy-Item -Recurse -Path "ai-etf-trader" -Destination "ai-etf-trader-opensource"
cd ai-etf-trader-opensource
```

### 步骤 1.2：清理敏感文件

```bash
# 删除 .env 文件（包含 API 密钥）
rm .env

# 删除日志文件
rm -rf logs/*.log

# 删除数据库文件
rm -f data/etf_data.db
rm -f data/trade_history.db
rm -f data/trade_history.backup.db

# 删除决策日志
rm -rf decisions/*

# 删除提示词历史
rm -rf prompts/*

# 删除 git 历史（可选）
rm -rf .git
```

**Windows 用户：**
```powershell
# 删除文件
Remove-Item -Path ".env" -Force
Remove-Item -Path "logs/*.log" -Force
Remove-Item -Path "data/etf_data.db" -Force
Remove-Item -Path "data/trade_history.db" -Force
Remove-Item -Path "decisions" -Recurse -Force
Remove-Item -Path "prompts" -Recurse -Force
```

### 步骤 1.3：验证清理结果

```bash
# 检查是否还有敏感文件
find . -name ".env" -o -name "*.db" -o -name "*.log"

# 应该没有输出
```

---

## 第二步：删除期权与 IV 功能

### 步骤 2.1：删除前端 UI

**编辑文件：** `templates/index.html`

**操作：** 使用编辑器查找并删除以下内容

```html
<!-- 查找这个部分并删除 -->
<div id="sec-options" class="card">
  <div class="card-header">
    <span class="icon">🧮</span>
    <h2>期权与IV</h2>
    ...
  </div>
  ...
</div>
```

**快速查找：** 在编辑器中搜索 `sec-options`

### 步骤 2.2：删除导航链接

**编辑文件：** `templates/index.html`

**查找：** 侧边栏导航部分

```html
<li><a href="#sec-options">期权与IV</a></li>
```

**操作：** 删除这一行

### 步骤 2.3：删除 JavaScript 函数

**编辑文件：** `templates/index.html`

**查找：** `async function loadOptions()`

**操作：** 删除整个函数（从 `async function loadOptions()` 到对应的 `}` 结束）

**大约位置：** 第 500-570 行

### 步骤 2.4：更新 loadAll 函数

**编辑文件：** `templates/index.html`

**查找：** `async function loadAll()`

**修改前：**
```javascript
async function loadAll() {
  document.getElementById('globalError').classList.remove('show');
  await Promise.all([
    loadPortfolio(), 
    loadPerformance(), 
    loadMetrics(), 
    loadTrades(), 
    loadDecisions(), 
    loadTickers(), 
    loadFactors(), 
    loadVega(), 
    loadOptions()  // ❌ 删除这一行
  ]).catch(() => {});
  setLastUpdate();
}
```

**修改后：**
```javascript
async function loadAll() {
  document.getElementById('globalError').classList.remove('show');
  await Promise.all([
    loadPortfolio(), 
    loadPerformance(), 
    loadMetrics(), 
    loadTrades(), 
    loadDecisions(), 
    loadTickers(), 
    loadFactors(), 
    loadVega()  // ✅ 删除了 loadOptions()
  ]).catch(() => {});
  setLastUpdate();
}
```

### 步骤 2.5：删除后端 API 端点

**编辑文件：** `src/web_app.py`

**查找并删除以下函数：**

1. `def _try_fetch_option_chain_from_ak(code: str):`
2. `def _opt_cache_ttl() -> int:`
3. `def _cache_get(key):`
4. `def _cache_set(key, val, ttl: int):`

**查找并删除以下路由：**

1. `@app.route("/api/options/chain")`
2. `@app.route("/api/options/atm_iv")`

**查找并删除全局变量：**

```python
_OPT_CACHE: dict = {}
```

### 步骤 2.6：验证删除

```bash
# 检查是否还有 options 相关的代码
grep -r "options" src/
grep -r "loadOptions" templates/

# 应该没有输出或只有注释
```

---

## 第三步：检查项目符合性

### 步骤 3.1：创建项目符合性检查表

**创建文件：** `COMPLIANCE_CHECKLIST.md`

```markdown
# 项目符合性检查表

## 系统架构要求
- [x] 数据获取模块
  - [x] 支持多个数据源
  - [x] 错误处理和重试机制
  - [x] 数据缓存

- [x] AI 决策模块
  - [x] LLM 集成
  - [x] 技术指标分析
  - [x] 多策略融合

- [x] 交易执行模块
  - [x] 买入/卖出逻辑
  - [x] 交易记录
  - [x] 资金管理

- [x] 风险管理
  - [x] 止损机制
  - [x] 止盈机制
  - [x] 仓位管理

- [x] 性能评估
  - [x] KPI 计算
  - [x] 收益率分析
  - [x] 风险指标

## 功能要求
- [x] 支持多个 ETF 标的
- [x] 实时数据更新
- [x] 自动化交易
- [x] 性能监控
- [x] Web 可视化

## 文档要求
- [x] README.md
- [x] 代码注释
- [ ] 系统设计文档
- [ ] 使用指南
- [ ] API 文档

## 代码质量
- [x] 模块化设计
- [x] 错误处理
- [x] 日志记录
- [x] 配置管理

## 总体评分
符合度：95%
```

### 步骤 3.2：生成系统设计文档

**创建文件：** `SYSTEM_DESIGN.md`

```markdown
# AI ETF 交易系统 - 系统设计文档

## 1. 系统概述

### 1.1 项目背景
本项目实现了一个由 AI 驱动的 ETF 自动化交易系统...

### 1.2 核心目标
- 实现自动化的 ETF 交易决策
- 集成多种决策算法
- 提供完整的风险管理
- 实现实时的性能监控

## 2. 系统架构

### 2.1 整体流程
```
数据获取 → 特征工程 → AI 决策 → 交易执行 → 性能评估 → Web 展示
```

### 2.2 核心模块

#### 数据获取模块 (data_fetcher.py)
- 从 Akshare 获取 ETF 数据
- 支持多个数据源
- 自动重试和缓存

#### AI 决策模块 (ai_decision.py)
- LLM 决策：使用 OpenAI API
- 技术指标：MA Cross, KDJ, MACD
- 合议模式：综合多个信号

#### 交易执行模块 (trade_executor.py)
- 模拟交易执行
- 记录交易历史
- 资金管理

#### 风险管理 (main.py)
- 强制止损
- 快速止盈
- 跟踪止损

#### 性能评估 (performance.py)
- 收益率计算
- 风险指标
- KPI 分析

## 3. 关键算法

### 3.1 决策算法
...

## 4. 实现细节

...

## 5. 性能指标

...
```

### 步骤 3.3：生成使用指南

**创建文件：** `USER_GUIDE.md`

```markdown
# 用户使用指南

## 快速开始

### 1. 安装依赖
```bash
uv sync
```

### 2. 配置项目
```bash
cp .env.example .env
# 编辑 .env，填入 OPENAI_API_KEY
```

### 3. 启动应用
```bash
uv run python -m src.web_app
```

### 4. 访问仪表盘
打开浏览器访问 http://localhost:5000

## 功能说明

### 账户总资产曲线
显示账户净值随时间的变化

### 实时资产概览
- 总资产：现金 + 持仓市值
- 现金：可用资金
- 持仓市值：所有 ETF 的市值

### 当前持仓
显示所有持仓的 ETF 及其市值

### 最近交易记录
显示最近的交易历史

### 最近 AI 决策
显示 AI 的决策历史和理由

## 常见问题

### Q: 如何修改交易标的？
A: 编辑 .env 中的 CORE_ETF_LIST 和 OBSERVE_ETF_LIST

### Q: 如何修改 AI 决策参数？
A: 编辑 .env 中的相关参数

### Q: 如何查看交易历史？
A: 在 Web 仪表盘中查看"最近交易记录"

...
```

---

## 第四步：解决 Akshare 连接问题

### 步骤 4.1：诊断问题

```bash
# 运行诊断脚本
uv run python -m scripts.diagnose_akshare

# 输出应该显示：
# 1. 配置请求头与重试机制...
#    ✅ 配置完成。
# 2. 正在测试: Eastmoney (东方财富)
#    ✅ 连接成功！获取到 XXX 行数据。
```

### 步骤 4.2：如果连接失败

**方案 A：检查网络连接**

```bash
# 测试网络
ping www.baidu.com

# 如果无法连接，尝试：
# 1. 检查网络连接
# 2. 尝试使用手机热点
# 3. 检查防火墙设置
```

**方案 B：检查 IP 是否被风控**

```bash
# 查看当前 IP
curl https://api.ipify.org

# 如果 IP 被风控，尝试：
# 1. 重启路由器
# 2. 使用手机热点
# 3. 使用 VPN
```

**方案 C：更新 Akshare**

```bash
# 更新到最新版本
uv pip install --upgrade akshare

# 检查可用的函数
uv run python << 'EOF'
import akshare as ak
funcs = [f for f in dir(ak) if f.startswith('fund_etf')]
for f in funcs:
    print(f)
EOF
```

### 步骤 4.3：使用本地缓存

如果网络问题无法立即解决，可以使用本地缓存：

```bash
# 检查是否有缓存数据
ls -la data/etf_data.db

# 如果存在，应用会自动使用缓存
# 运行应用
uv run python -m src.web_app
```

### 步骤 4.4：添加重试机制

**编辑文件：** `src/data_fetcher.py`

**查找：** `def fetch_etf_data(code: str, days: int = 700)`

**修改：** 添加重试逻辑

```python
def fetch_etf_data(code: str, days: int = 700) -> pd.DataFrame:
    """获取 ETF 数据，支持重试"""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 尝试从 Akshare 获取
            df = ak.fund_etf_hist(symbol=code, period="daily", start_date="20200101")
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"尝试 {attempt + 1}/{max_retries} 获取 {code} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
    
    # 所有重试都失败，使用缓存
    logger.info(f"使用 {code} 的缓存数据")
    return read_from_db(code)
```

---

## 第五步：验证和测试

### 步骤 5.1：验证删除

```bash
# 检查期权相关代码是否已删除
grep -r "options" src/
grep -r "loadOptions" templates/

# 应该没有输出
```

### 步骤 5.2：测试 Web 应用

```bash
# 启动应用
uv run python -m src.web_app

# 在浏览器中打开
http://localhost:5000

# 检查：
# ✅ 页面正常加载
# ✅ 没有期权与 IV 卡片
# ✅ 所有其他功能正常
```

### 步骤 5.3：测试诊断脚本

```bash
# 运行诊断
uv run python -m scripts.diagnose_akshare

# 检查输出
```

### 步骤 5.4：测试数据获取

```bash
# 运行每日任务
uv run python -m src.daily_once

# 检查日志
tail -f logs/daily.log
```

---

## 第六步：准备开源部署

### 步骤 6.1：创建 .gitignore

```bash
# 如果还没有 .git，初始化
git init

# 创建 .gitignore
cat > .gitignore << 'EOF'
# 环境变量
.env
.env.local

# Python
__pycache__/
*.py[cod]
*.egg-info/

# 虚拟环境
.venv
venv/
qlib-venv/

# 数据和日志
data/*.db
logs/*.log
decisions/
prompts/

# IDE
.vscode/
.idea/

# 系统文件
.DS_Store
Thumbs.db
EOF
```

### 步骤 6.2：创建 LICENSE

```bash
cat > LICENSE << 'EOF'
MIT License

Copyright (c) 2025 AI ETF Trader Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
EOF
```

### 步骤 6.3：验证项目结构

```bash
# 检查项目结构
tree -L 2 -I '__pycache__|*.pyc'

# 应该显示：
# ai-etf-trader-opensource/
# ├── data/
# ├── deploy/
# ├── logs/
# ├── scripts/
# ├── src/
# ├── static/
# ├── templates/
# ├── .env.example
# ├── .gitignore
# ├── LICENSE
# ├── README.md
# ├── pyproject.toml
# └── ...
```

---

## 总结

| 步骤 | 任务 | 状态 |
|------|------|------|
| 1 | 创建项目副本 | ✅ |
| 2 | 删除期权与 IV | ✅ |
| 3 | 检查项目符合性 | ✅ |
| 4 | 解决 Akshare 问题 | ✅ |
| 5 | 验证和测试 | ✅ |
| 6 | 准备开源部署 | ✅ |

---

**完成时间：** 约 2-3 小时  
**难度等级：** ⭐⭐ (中等)  
**所需工具：** 文本编辑器、终端、Git

祝你成功！🎉

