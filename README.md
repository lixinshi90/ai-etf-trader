# AI ETF Trader - 自动化交易系统

本项目是一个由 AI 驱动的 ETF 自动化交易系统，实现了从数据获取、AI 决策、交易执行到绩效评估和 Web 展示的完整闭环。

## ✨ 核心特性

- 混合决策引擎：结合大语言模型 (LLM)、传统技术指标（KDJ、MACD、MA Cross）与 Qlib 因子，通过可配置的合议模式 (CONSENSUS) 生成交易信号。
- 分层标的池：支持“核心池 + 观察池”的两层结构，先处理核心池，若无买信号再处理观察池。
- 动态仓位：可按照 AI 置信度或外部覆盖值调整仓位比例，并设置最小/最大边界。
- 风险控制：支持强制止损、快速止盈、跟踪止损（高水位回撤）；考虑手续费与滑点。
- Web 仪表盘：Flask + ECharts 展示账户净值、持仓、交易、AI 决策与 KPI。
- Qlib 集成（可选）：支持因子 CSV（本地）与 TopK 选股（Provider）两种融合方式。
- 波动率风险近似：提供 Vegas 风险敞口的近似计算（不依赖期权链与 IV）。

## 🧠 交易策略总览（当前实现）

系统的每日流程（收盘后）

1) 拉取与落库
- 通过 akshare 获取 ETF 日线数据（优先东方财富 fund_etf_hist_em，失败回退新浪 fund_etf_hist_sina），并写入 data/etf_data.db。
- 实时行情用于界面刷新，优先东方财富 fund_etf_spot_em，失败回退同花顺 fund_etf_spot_ths。闭市时会自动退回历史快照（源: history）。

2) 生成规则信号（rule-based）
- STRATEGY_MODE 决定规则集：
  - MA_CROSS：20/60 均线金叉/死叉 + 位于均线上下
  - BREAKOUT：唐奇安通道 N 日高点突破（默认 N=20）
  - MEAN_REVERSION：RSI(n=2) 超买/超卖（默认 low=10、high=95）
  - KDJ_MACD：J 低位上穿阈值 + MACD 金叉
  - AGGRESSIVE（默认）：综合上述多个规则，并可叠加“Qlib 因子”判断（见下）
- 若开启 Qlib 因子（QLIB_FACTOR_ENABLED=true，默认 true），且 data/qlib_factors/<code>.csv 存在，读取最近一行例如 rsi_14 等因子，给出辅助买/卖提示（默认使用 RSI14 的阈值比较）。

3) 可选：Qlib TopK 融合（选股层）
- 若 QLIB_ALGO_ENABLED=true 且 Qlib Provider (QLIB_DIR) 初始化成功，则计算一段回看期（QLIB_TOPK_LOOKBACK）的收益率排序，取前 K（QLIB_TOPK_K）作为 TopK 集合：
  - ETF 在 TopK：将规则信号提升为“买入”（并在 reasoning 中标注“Qlib TopK”）
  - ETF 不在 TopK 且规则为 hold：给出温和的“sell”提示（“Qlib 非TopK”）

4) AI 决策（限流）
- 对单个 ETF 传入最近一段行情与关键指标，调用大模型生成结构化决策（buy/sell/hold + confidence + reasoning + 可选止损/止盈/仓位建议）。
- 每日调用次数由 DAILY_AI_CALLS_LIMIT 控制（默认不超过标的个数）。

5) 合议（CONSENSUS）
- 仅当 AI 与 规则同向（同为 buy 或同为 sell）时才执行该方向；否则持有（hold）。
- 合并 reasoning 与 confidence，作为最终执行依据。

6) 执行与风控
- 仓位：支持固定基础仓位 + 按置信度动态放大；也支持由决策直接覆盖 position_pct。
- 风控：
  - 强制止损（HARD_STOP_LOSS_PCT）：浮亏超阈值即清仓；
  - 快速止盈（QUICK_TAKE_PROFIT_TRIGGER/SELL_RATIO）：浮盈达到触发阈值时部分卖出；
  - 跟踪止损（ENABLE_TRAILING_STOP/TRAILING_STOP_PCT/TRAILING_STEP_PCT）：价格创新高后抬升止损线，回撤即卖出；
  - 成本/滑点：COST_BPS、SLIPPAGE_BPS。
- 执行完成后，写入当日 equity 快照（daily_equity 表）。

7) Qlib 因子数据更新（在 daily_once 任务末尾）
- 导出原始 CSV（qlib_adapter）与计算因子（qlib_run）。
- 注意：因子计算在“当次决策之后”触发，因此新因子通常从“下一日”开始用于规则判断（除非你提前手工生成因子）。

## ⚙️ 策略相关配置（关键环境变量）

- 标的池
  - CORE_ETF_LIST、OBSERVE_ETF_LIST、ETF_LIST
  - FILTER_ENABLED（默认 true）、MIN_AVG_TURNOVER、MIN_LISTING_MONTHS：标的池过滤（流动性/上市时长）

- 规则策略
  - STRATEGY_MODE=AGGRESSIVE|MA_CROSS|BREAKOUT|MEAN_REVERSION|KDJ_MACD（默认 AGGRESSIVE）
  - BREAKOUT_N=20
  - RSI_N=2、RSI_LOW=10、RSI_HIGH=95
  - KDJ_LOW=20

- Qlib 融合
  - QLIB_FACTOR_ENABLED=true（默认 true）：使用 data/qlib_factors/<code>.csv 的最近一行因子参与规则判断
  - QLIB_ALGO_ENABLED=false（默认 false）：启用 TopK 选股融合（需 Qlib Provider 可用）
  - QLIB_DIR=./data/qlib/cn_etf、QLIB_REGION=cn、QLIB_TOPK_LOOKBACK=60、QLIB_TOPK_K=2

- AI 决策
  - DAILY_AI_CALLS_LIMIT：每日最大 AI 调用次数（默认不超过标的数）

- 仓位与风控
  - ENABLE_DYNAMIC_POSITION=false、BASE_POSITION_PCT=0.2、MIN_POSITION_PCT=0.05、MAX_POSITION_PCT=0.3
  - HARD_STOP_LOSS_PCT=0.0
  - QUICK_TAKE_PROFIT_TRIGGER=0.0、QUICK_TAKE_PROFIT_SELL_RATIO=0.0
  - ENABLE_TRAILING_STOP=false、TRAILING_STOP_PCT=0.05、TRAILING_STEP_PCT=0.01
  - COST_BPS=5、SLIPPAGE_BPS=2

- 实时/历史行情
  - 闭市：/api/etf_tickers?live=1 返回 market_open=false，source=history；界面显示历史快照属正常

## 🛠️ 技术栈

- 包管理：uv（极速 Python 包管理器）
- 后端：Flask、Pandas、NumPy、Akshare
- AI：OpenAI 兼容 SDK
- 数据库：SQLite
- 量化：Qlib（可选）
- 前端：ECharts、HTML/CSS/JavaScript

## 🚀 快速开始

1) 安装 uv（略）并克隆项目；2) uv sync 安装依赖；3) 拷贝 .env.example 为 .env 并按需修改；4) 启动 Web 或执行每日任务。

- 启动 Web 仪表盘
```bash
uv run python -m src.web_app
# 浏览器访问 http://127.0.0.1:5000
```
- 手动执行每日任务
```bash
uv run python -m src.daily_once
```

## 📈 Qlib 集成（可选）

- 若只使用“因子 CSV 融合”，无需安装 Qlib Provider：保持 QLIB_FACTOR_ENABLED=true，同时确保 data/qlib_factors 下存在对应 CSV 即可。
- 若要启用 TopK 选股融合（QLIB_ALGO_ENABLED=true），需准备 Qlib Provider（dump_bin 建库）并设置 QLIB_DIR、QLIB_REGION。

## 📁 项目结构

```
ai-etf-trader/
├── data/                 # 数据库、Qlib 数据等
├── decisions/            # AI 决策 JSON
├── deploy/               # 部署脚本
├── logs/                 # 运行日志
├── prompts/              # Prompt 模板与历史
├── scripts/              # 辅助脚本（回填、审计、诊断等）
├── src/                  # 核心代码
│   ├── web_app.py        # Flask Web & API
│   ├── daily_once.py     # 一次性每日任务入口
│   ├── main.py           # 主任务调度与策略融合
│   ├── data_fetcher.py   # 数据获取（多源 fallback）
│   ├── ai_decision.py    # AI 决策
│   ├── trade_executor.py # 交易执行与风控
│   ├── qlib_adapter.py   # 导出原始 CSV
│   └── qlib_run.py       # 计算因子（生成 data/qlib_factors）
├── static/               # 前端静态资源
├── templates/            # 前端模板
└── pyproject.toml        # 依赖与元数据（uv 使用）
```

## ⚙️ API 速览（常用）

- GET /api/performance：账户净值曲线
- GET /api/portfolio：资产与持仓
- GET /api/trades：交易记录
- GET /api/decisions：AI 决策
- GET /api/etf_tickers?live=1：实时/历史行情（带 source）
- GET /api/qlib/factors：最新因子快照（每个代码 1 行）或指定 code 的最近多行
- GET /api/vega_risk：波动率风险近似（汇总/单标的时间序列）
- GET /api/qlib/status：Qlib Provider 状态（仅 Web 端）

## ❓常见问题

- 闭市为什么显示“源: history”？
  - 这是设计逻辑：闭市时回退到数据库最新快照，仍可查看最新收盘价、涨跌等。
- 名称为什么可能为“-”？
  - 实时源不可用时无法动态补名；可通过环境变量 ETF_NAME_MAP 提供静态映射，或待网络恢复后自动补全。

## 🤝 贡献

欢迎提交 Issues 与 PR，一起完善策略与风控。
