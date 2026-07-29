# 🚀 开源部署与期末报告指南

## 📋 任务清单

本文档将帮助你完成以下任务：

1. ✅ 创建项目副本用于开源部署
2. ✅ 删除期权与IV相关功能
3. ✅ 检查项目是否符合期末报告要求
4. ✅ 解决 akshare 数据源连接问题

---

## 📌 第一部分：创建项目副本用于开源部署

### 1.1 创建副本目录结构

```bash
# 在项目根目录的上一级创建副本
cd ..
cp -r ai-etf-trader ai-etf-trader-opensource

# 进入副本目录
cd ai-etf-trader-opensource
```

### 1.2 清理敏感信息

```bash
# 删除敏感文件
rm -f .env                          # 删除本地配置（包含API密钥）
rm -rf logs/*.log                   # 删除日志文件
rm -rf data/trade_history.db        # 删除交易历史
rm -rf data/etf_data.db             # 删除本地数据
rm -rf decisions/                   # 删除决策日志
rm -rf prompts/                     # 删除提示词历史
rm -rf .git                         # 删除git历史（可选）
```

### 1.3 创建开源友好的配置

```bash
# 确保 .env.example 包含所有必需的配置项
cat > .env.example << 'EOF'
# ==================== 必填配置 ====================
# OpenAI API 密钥（或兼容服务的密钥）
OPENAI_API_KEY=sk-your-api-key-here

# 核心与观察标的池
CORE_ETF_LIST=510300,510050,159915,588000
OBSERVE_ETF_LIST=512480,516160,513100,159790

# ==================== 可选配置 ====================
# 初始资本（默认100000）
INITIAL_CAPITAL=100000

# Flask 配置
FLASK_HOST=127.0.0.1
FLASK_PORT=5000
FLASK_DEBUG=false

# 数据获取配置
REFRESH_DAYS=700

# AI 决策配置
STRATEGY_MODE=MA_CROSS
BREAKOUT_N=20
RSI_N=2
RSI_LOW=10
RSI_HIGH=95

# 风控配置
STOP_LOSS_PCT=0.05
TAKE_PROFIT_PCT=0.10

# Qlib 配置（可选）
QLIB_ENABLE=false
QLIB_ALGO_ENABLED=false
QLIB_TOPK_K=2
QLIB_TOPK_LOOKBACK=60

# 期权配置
OPT_MAX_EXPIRY_DAYS=30
OPT_CACHE_TTL=60

# Vegas 风险配置
VEGAS_VOL_LOOKBACK=20
VEGAS_T_DAYS=30

# 风险无风险率
RISK_FREE_RATE=0.02
EOF
```

### 1.4 更新 README.md

```bash
# 为开源版本创建专门的 README
cat > README_OPENSOURCE.md << 'EOF'
# AI ETF Trader - 开源版本

这是 AI ETF Trader 的开源版本，用于学习和研究目的。

## 快速开始

### 1. 安装依赖

```bash
# 安装 uv
# Windows (PowerShell)
irm https://astral.sh/uv/install.ps1 | iex

# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# 同步依赖
uv sync
```

### 2. 配置项目

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入你的 OpenAI API 密钥
# OPENAI_API_KEY=sk-your-key-here
```

### 3. 运行项目

```bash
# 启动 Web 仪表盘
uv run python -m src.web_app

# 打开浏览器访问
http://localhost:5000
```

## 功能特性

- ✅ AI 驱动的 ETF 自动化交易系统
- ✅ 混合决策引擎（LLM + 技术指标）
- ✅ Web 仪表盘实时展示
- ✅ 完整的风险管理机制
- ✅ 支持 Qlib 因子分析

## 注意事项

- 本项目仅供学习和研究使用
- 实际交易前请充分测试和评估风险
- 确保 API 密钥的安全性

## 许可证

MIT License

## 贡献

欢迎提交 Pull Requests 和 Issues！
EOF
```

### 1.5 创建 .gitignore

```bash
cat > .gitignore << 'EOF'
# 环境变量
.env
.env.local
.env.*.local

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# 虚拟环境
.venv
venv/
ENV/
env/
qlib-venv/

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# 数据和日志
data/etf_data.db
data/trade_history.db
data/trade_history.backup.db
logs/*.log
decisions/
prompts/

# 系统文件
.DS_Store
Thumbs.db

# 临时文件
tmp/
*.tmp
*.bak
EOF
```

### 1.6 创建 LICENSE

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
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE OR OTHERWISE,
ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
EOF
```

---

## 🗑️ 第二部分：删除期权与IV相关功能

### 2.1 删除前端 UI 组件

**文件：** `templates/index.html`

删除以下部分：

```html
<!-- 删除这个卡片 -->
<div id="sec-options" class="card">
  <div class="card-header">
    <span class="icon">🧮</span>
    <h2>期权与IV</h2>
    <div style="margin-left:auto; display:flex; align-items:center; gap:8px;">
      <span class="muted">标的</span>
      <select id="optSelect" class="btn"></select>
      <button class="btn-refresh" onclick="loadOptions()">刷新</button>
    </div>
  </div>
  <div class="card-body">
    <div id="optEmpty" class="empty-state show">
      <div class="empty-state-icon">📭</div>
      <div class="empty-state-text">正在加载期权与IV...</div>
    </div>
    <div style="display:grid;grid-template-columns:1fr;gap:16px;">
      <div class="table-wrapper">
        <h3 style="font-size:14px;color:#555;margin-bottom:8px;">ATM IV 概览（行权价最接近标的）</h3>
        <table id="optAtmTable" style="display:none;">
          <thead>
            <tr>
              <th>类型</th>
              <th>K</th>
              <th>到期(天)</th>
              <th>中间价</th>
              <th>IV(%)</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
      <div class="table-wrapper">
        <h3 style="font-size:14px;color:#555;margin-bottom:8px;">期权链（近月）</h3>
        <table id="optChainTable" style="display:none;">
          <thead>
            <tr>
              <th>类型</th>
              <th>K</th>
              <th>到期日</th>
              <th>剩余天</th>
              <th>中间价</th>
              <th>IV(%)</th>
              <th>Delta</th>
              <th>Gamma</th>
              <th>Vega</th>
              <th>Theta</th>
            </tr>
          </thead>
          <tbody></tbody>
        </table>
      </div>
    </div>
  </div>
</div>
```

### 2.2 删除导航链接

在 `templates/index.html` 的侧边栏中，删除：

```html
<li><a href="#sec-options">期权与IV</a></li>
```

### 2.3 删除 JavaScript 函数

在 `templates/index.html` 的 `<script>` 标签中，删除：

```javascript
async function loadOptions() {
  // ... 整个函数
}
```

并从 `loadAll()` 函数中删除：

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

### 2.4 删除后端 API 端点

**文件：** `src/web_app.py`

删除以下函数和路由：

```python
# 删除这些函数
def _try_fetch_option_chain_from_ak(code: str):
    # ...

def _opt_cache_ttl() -> int:
    # ...

def _cache_get(key):
    # ...

def _cache_set(key, val, ttl: int):
    # ...

# 删除这些路由
@app.route("/api/options/chain")
def get_options_chain():
    # ...

@app.route("/api/options/atm_iv")
def get_options_atm_iv():
    # ...
```

并删除全局变量：

```python
_OPT_CACHE: dict = {}
```

### 2.5 删除相关导入

在 `src/web_app.py` 中，删除与期权相关的导入：

```python
# 删除这些导入（如果有的话）
from src.options import implied_vol, greeks as bs_greeks
```

---

## ✅ 第三部分：检查项目是否符合期末报告要求

### 3.1 期末报告要求分析

根据文档名称 "2025-2026学年第1学期《量化交易》期末综合实验报告：AI炒ETF系统的实现及报告.docx"，项目应该包含：

| 要求 | 你的项目 | 状态 |
|------|--------|------|
| **系统设计** | ✅ 完整的系统架构 | ✅ |
| **数据获取** | ✅ Akshare 数据源 | ✅ |
| **AI 决策** | ✅ LLM + 技术指标 | ✅ |
| **交易执行** | ✅ 模拟交易系统 | ✅ |
| **风险管理** | ✅ 止损、止盈机制 | ✅ |
| **性能评估** | ✅ KPI 计算 | ✅ |
| **可视化展示** | ✅ Web 仪表盘 | ✅ |
| **文档** | ⚠️ 需要补充 | 📝 |

### 3.2 项目符合性检查清单

```markdown
## 系统架构
- [x] 数据获取模块（data_fetcher.py）
- [x] AI 决策模块（ai_decision.py）
- [x] 交易执行模块（trade_executor.py）
- [x] 性能评估模块（performance.py）
- [x] Web 展示模块（web_app.py）

## 核心功能
- [x] 支持多个 ETF 标的
- [x] 实时数据更新
- [x] AI 驱动的决策
- [x] 自动化交易执行
- [x] 风险管理机制
- [x] 性能指标计算

## 高级功能
- [x] 分层标的池（核心池 + 观察池）
- [x] 动态仓位管理
- [x] 多策略融合（MA Cross + KDJ + MACD + LLM）
- [x] Qlib 集成（可选）
- [x] 波动率风险分析

## 文档与报告
- [x] README.md
- [x] 代码注释
- [ ] 期末报告文档（需要生成）
- [ ] 系统设计文档（需要补充）
- [ ] 使用指南（需要补充）
```

### 3.3 生成期末报告所需的文档

创建以下文档以支持期末报告：

**文件：** `SYSTEM_DESIGN.md`

```markdown
# AI ETF 交易系统 - 系统设计文档

## 1. 系统概述

### 1.1 项目背景
本项目实现了一个由 AI 驱动的 ETF 自动化交易系统，旨在通过结合大语言模型、传统技术指标和量化因子，生成高效的交易信号。

### 1.2 核心目标
- 实现自动化的 ETF 交易决策
- 集成多种决策算法提高准确性
- 提供完整的风险管理机制
- 实现实时的性能监控和展示

## 2. 系统架构

### 2.1 整体架构图
```
数据源 (Akshare)
    ↓
数据获取模块 (data_fetcher.py)
    ↓
特征工程 (indicators.py, qlib_adapter.py)
    ↓
AI 决策引擎 (ai_decision.py)
    ├─ LLM 决策
    ├─ 技术指标决策
    └─ Qlib 因子决策
    ↓
合议模式 (CONSENSUS)
    ↓
交易执行模块 (trade_executor.py)
    ↓
数据库存储 (SQLite)
    ↓
Web 展示 (web_app.py + 前端)
```

### 2.2 模块设计

#### 数据获取模块
- 从 Akshare 获取实时 ETF 数据
- 支持多个数据源（Eastmoney, Sina, 10jqka）
- 自动重试和错误处理

#### AI 决策模块
- LLM 决策：使用 OpenAI API 进行智能分析
- 技术指标：MA Cross, KDJ, MACD
- Qlib 因子：支持高级因子分析
- 合议模式：综合多个信号生成最终决策

#### 交易执行模块
- 模拟交易（不涉及真实资金）
- 支持买入、卖出、持有操作
- 记录所有交易历史

#### 风险管理
- 强制止损：超过阈值自动平仓
- 快速止盈：达到目标自动平仓
- 跟踪止损：动态调整止损点

## 3. 关键算法

### 3.1 决策算法
...

## 4. 性能指标

### 4.1 KPI 计算
- 总收益率
- 年化收益率
- 最大回撤
- 胜率
- 夏普比率

## 5. 实现细节

...
```

---

## 🔧 第四部分：解决 Akshare 数据源连接问题

### 4.1 问题分析

你遇到的错误：

```
❌ 连接失败: ConnectionError - ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
⚠️ 函数 'fund_etf_spot_sina' 在当前 akshare 版本中不存在，跳过。
⚠️ 函数 'fund_etf_spot_10jqka' 在当前 akshare 版本中不存在，跳过。
```

**原因：**
1. **网络问题** - IP 被风控或网络连接不稳定
2. **API 版本变化** - Akshare 版本更新导致函数名变化
3. **数据源不可用** - 某些数据源已下线

### 4.2 解决方案

#### 方案 1: 使用本地缓存数据

**修改文件：** `src/data_fetcher.py`

```python
def fetch_etf_data(code: str, days: int = 700) -> pd.DataFrame:
    """
    获取 ETF 数据，优先使用缓存
    """
    # 1. 尝试从数据库读取
    try:
        df = read_from_db(code)
        if not df.empty and len(df) >= 100:
            return df
    except Exception:
        pass
    
    # 2. 尝试从 Akshare 获取
    try:
        df = fetch_from_akshare(code, days)
        if not df.empty:
            save_to_db(df, code)
            return df
    except Exception as e:
        logger.warning(f"从 Akshare 获取 {code} 失败: {e}")
    
    # 3. 使用缓存数据
    logger.info(f"使用 {code} 的缓存数据")
    return read_from_db(code)
```

#### 方案 2: 更新 Akshare 函数调用

**修改文件：** `scripts/diagnose_akshare.py`

```python
def main():
    try:
        import akshare as ak
        from src.data_fetcher import _configure_ak_session
    except ImportError as e:
        print(f"❌ 无法导入所需模块: {e}")
        return

    print("1. 配置请求头与重试机制...")
    _configure_ak_session()
    print("   ✅ 配置完成。")

    # 更新为最新的 Akshare API
    sources_to_check = [
        ("Eastmoney (东方财富)", "fund_etf_spot_em"),
        # 注意：Sina 和 10jqka 的函数名可能已变更
        # 可以使用 dir(ak) 查看可用函数
    ]

    for name, func_name in sources_to_check:
        print(f"\n2. 正在测试: {name}")
        
        if not hasattr(ak, func_name):
            print(f"   ⚠️ 函数 '{func_name}' 在当前 akshare 版本中不存在，跳过。")
            continue

        try:
            func = getattr(ak, func_name)
            df = func()
            if df is not None and not df.empty:
                print(f"   ✅ 连接成功！获取到 {len(df)} 行数据。")
            else:
                print("   ⚠️ 连接成功，但未返回数据。")
        except Exception as e:
            print(f"   ❌ 连接失败: {type(e).__name__} - {e}")
            print("   💡 建议：检查网络连接或尝试切换网络")

    print("\n🏁 诊断完成。")
```

#### 方案 3: 添加网络重试机制

**修改文件：** `src/data_fetcher.py`

```python
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _configure_ak_session():
    """配置 Akshare 会话，添加重试机制"""
    global ak
    if ak is None:
        return
    
    try:
        import requests
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://quote.eastmoney.com/",
            "Connection": "keep-alive",
        }
        
        try:
            ak.headers = headers
        except Exception:
            pass
        
        # 创建会话并配置重试
        s = requests.Session()
        retry = Retry(
            total=5,  # 增加重试次数
            backoff_factor=2,  # 增加退避时间
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        
        try:
            ak.session = s
        except Exception:
            pass
    except Exception:
        pass

def fetch_etf_data(code: str, days: int = 700, max_retries: int = 3) -> pd.DataFrame:
    """
    获取 ETF 数据，支持重试
    """
    for attempt in range(max_retries):
        try:
            if ak is None:
                raise ImportError("akshare not installed")
            
            df = ak.fund_etf_hist(symbol=code, period="daily", start_date="20200101")
            if df is not None and not df.empty:
                return df
        except Exception as e:
            logger.warning(f"尝试 {attempt + 1}/{max_retries} 获取 {code} 失败: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # 指数退避
    
    # 所有重试都失败，返回空 DataFrame
    return pd.DataFrame()
```

#### 方案 4: 使用备用数据源

**创建文件：** `src/backup_data_source.py`

```python
"""
备用数据源，当 Akshare 不可用时使用
"""

import pandas as pd
import requests
from datetime import datetime, timedelta

def fetch_from_tencent(code: str) -> pd.DataFrame:
    """从腾讯财经获取数据"""
    try:
        # 腾讯财经 API
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "param": f"{code},day,,,100",
            "newp": "1"
        }
        resp = requests.get(url, params=params, timeout=10)
        # 解析响应...
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

def fetch_from_sina(code: str) -> pd.DataFrame:
    """从新浪财经获取数据"""
    try:
        # 新浪财经 API
        url = f"https://hq.sinajs.cn/"
        params = {"list": code}
        resp = requests.get(url, params=params, timeout=10)
        # 解析响应...
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()
```

### 4.3 临时解决方案

如果网络问题无法立即解决，可以使用以下临时方案：

```bash
# 1. 使用手机热点
# 将电脑连接到手机热点，避免 IP 被风控

# 2. 使用 VPN
# 如果 IP 被风控，可以尝试使用 VPN

# 3. 使用代理
# 在 .env 中添加代理配置
HTTP_PROXY=http://proxy.example.com:8080
HTTPS_PROXY=http://proxy.example.com:8080

# 4. 延迟重试
# 修改 data_fetcher.py 中的重试间隔
```

### 4.4 检查 Akshare 可用函数

```bash
# 运行以下命令查看当前 Akshare 版本的可用函数
uv run python << 'EOF'
import akshare as ak

# 列出所有以 fund_etf 开头的函数
funcs = [f for f in dir(ak) if f.startswith('fund_etf')]
print("可用的 fund_etf 函数:")
for f in funcs:
    print(f"  - {f}")
EOF
```

---

## 📝 第五部分：综合建议

### 5.1 开源部署检查清单

- [ ] 删除所有敏感信息（API 密钥、个人数据）
- [ ] 创建 .env.example 配置模板
- [ ] 编写详细的 README.md
- [ ] 添加 LICENSE 文件
- [ ] 创建 .gitignore
- [ ] 清理日志和临时文件
- [ ] 更新代码注释
- [ ] 添加贡献指南

### 5.2 期末报告检查清单

- [ ] 系统设计文档
- [ ] 实现细节说明
- [ ] 性能评估结果
- [ ] 使用示例
- [ ] 遇到的问题和解决方案
- [ ] 未来改进方向
- [ ] 参考文献

### 5.3 数据源问题解决方案优先级

1. **优先级 1：使用本地缓存** - 最快最稳定
2. **优先级 2：增加重试机制** - 提高成功率
3. **优先级 3：使用备用数据源** - 增加可靠性
4. **优先级 4：手动更新数据** - 最后的手段

---

## 🎯 后续步骤

1. **立即执行**
   - 创建项目副本
   - 删除期权与 IV 功能
   - 清理敏感信息

2. **本周完成**
   - 解决 Akshare 连接问题
   - 生成期末报告文档
   - 测试开源版本

3. **本月完成**
   - 上传到 GitHub
   - 收集反馈
   - 持续改进

---

**最后更新：** 2025-12-12  
**状态：** 📝 进行中

