# 定时任务交易价格分析报告

## 问题：今天的定时任务是否使用了获取收盘价进行交易？

**答案：是的，使用了收盘价。**

---

## 详细分析

### 1. 数据流向

```
daily_once.py (启动)
    ↓
daily_task() [main.py]
    ↓
fetch_etf_data() → 拉取历史数据 → save_to_db() → 保存到 SQLite
    ↓
_read_latest_price() → 从数据库读取最新价格
    ↓
execute_trade() → 使用该价格执行交易
```

### 2. 关键代码片段

#### 2.1 读取最新价格 (`_read_latest_price` in main.py, line 138-151)

```python
def _read_latest_price(etf_code: str) -> float | None:
    db_file = _etf_db_path()
    if not os.path.exists(db_file):
        return None
    conn = sqlite3.connect(db_file)
    try:
        df = pd.read_sql_query(f"SELECT * FROM etf_{etf_code} ORDER BY 日期 DESC LIMIT 1", conn)
    except Exception:
        try:
            df = pd.read_sql_query(f"SELECT * FROM etf_{etf_code} ORDER BY date DESC LIMIT 1", conn)
        except Exception:
            df = pd.DataFrame()
    finally:
        conn.close()

    if df.empty:
        return None

    # ✅ 这里获取收盘价
    for col in ("收盘", "收盘价", "close", "Close"):
        if col in df.columns:
            try:
                return float(df.iloc[0][col])
            except Exception:
                continue
    return None
```

**关键点：**
- 从数据库最后一行（`ORDER BY 日期 DESC LIMIT 1`）读取
- 按优先级查找列名：`"收盘"` → `"收盘价"` → `"close"` → `"Close"`
- 返回的是**收盘价**

#### 2.2 在决策中使用收盘价 (`get_rule_decision` in main.py, line 169-177)

```python
def get_rule_decision(df: pd.DataFrame, params: dict, etf_code: str | None = None) -> dict:
    # ...
    close_col = _find_col("收盘", "收盘价", "close", "Close")
    
    if not close_col:
        return {"decision": "hold", "reasoning": "规则：无收盘价数据", "confidence": 0.5}

    close = df[close_col]
    latest_close = close.iloc[-1]  # ✅ 获取最新收盘价
    
    # 使用 latest_close 进行技术分析
    # - MA20/MA60 交叉
    # - Breakout 突破
    # - RSI 超买超卖
    # - KDJ/MACD 信号
```

#### 2.3 执行交易时使用价格 (`daily_task` in main.py, line 320-330)

```python
# 读取当前价格（收盘价）
for etf in all_etfs:
    price = _read_latest_price(etf)
    if price is not None:
        current_prices[etf] = price

# ...

# 执行交易时使用该价格
for etf, decision in decisions_to_execute.items():
    if etf in current_prices:
        executor.execute_trade(etf, decision, current_prices[etf])  # ✅ 传入收盘价
```

#### 2.4 交易执行中的价格处理 (`execute_trade` in trade_executor.py)

```python
def execute_trade(self, etf_code: str, decision: Dict[str, Any], current_price: float) -> float:
    # ...
    if action == "buy" and etf_code not in self.positions:
        pos_pct = self._position_pct(decision)
        exec_px = self._buy_exec_price(current_price)  # ✅ 加入买入滑点
        # ...
        
    elif action == "sell" and etf_code in self.positions:
        # ...
        exec_px = self._sell_exec_price(current_price)  # ✅ 减去卖出滑点
        # ...
```

其中滑点计算：
```python
def _buy_exec_price(self, px: float) -> float:
    return float(px) * (1.0 + self.slippage_bps / 10000.0)

def _sell_exec_price(self, px: float) -> float:
    return float(px) * (1.0 - self.slippage_bps / 10000.0)
```

---

## 3. 今日执行情况（2025-12-12）

从日志输出可以看到：

```
已保存 159915 数据到数据库: D:\Quantitative Trading\ai-etf-trader\data\etf_data.db
已更新 159915 数据
已保存 159922 数据到数据库: ...
...
[equity-breakdown] 510050 qty=32597.5428 px=3.1340 val=102160.70
[equity-breakdown] 512800 qty=52697.4740 px=0.8130 val=42843.05
[equity-breakdown] 515110 qty=25639.6596 px=1.5370 val=39408.16
...
已写入日终快照 2025-12-12: 386281.13
```

**确认：**
- ✅ 数据已从数据源拉取并保存到数据库
- ✅ 使用了收盘价（px 字段）进行持仓估值
- ✅ 执行了交易决策
- ✅ 记录了日终快照

---

## 4. 价格来源链路

```
数据源 (akshare/tushare/etc.)
    ↓
fetch_etf_data() [data_fetcher.py]
    ↓
save_to_db() → SQLite (etf_data.db)
    ↓
daily_task() 读取数据库最后一行
    ↓
_read_latest_price() 提取"收盘"列
    ↓
current_prices dict
    ↓
execute_trade() 使用该价格
    ↓
记录到 trade_history.db
```

---

## 5. 配置参数

从 `.env` 文件可配置的相关参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `SLIPPAGE_BPS` | 2 | 滑点（万分之2） |
| `COST_BPS` | 5 | 交易成本（万分之5） |
| `STRATEGY_MODE` | AGGRESSIVE | 策略模式 |
| `ENABLE_DYNAMIC_POSITION` | false | 是否动态调整仓位 |
| `ENABLE_TRAILING_STOP` | false | 是否启用跟踪止损 |

---

## 6. 结论

✅ **确认：今天的定时任务使用了收盘价进行交易**

### 具体流程：
1. **数据拉取**：从数据源获取包含收盘价的历史数据
2. **数据存储**：保存到 SQLite 数据库
3. **价格读取**：从数据库最新一行读取收盘价
4. **决策生成**：基于收盘价计算技术指标（MA、RSI、Breakout 等）
5. **交易执行**：使用收盘价 + 滑点作为执行价格
6. **记录交易**：保存到交易历史数据库

### 价格调整：
- **买入**：收盘价 × (1 + 滑点%)
- **卖出**：收盘价 × (1 - 滑点%)
- **成本**：交易金额 × 成本费率

---

## 附录：相关文件位置

| 文件 | 功能 |
|------|------|
| `src/daily_once.py` | 定时任务入口 |
| `src/main.py` | 核心任务逻辑（daily_task） |
| `src/trade_executor.py` | 交易执行引擎 |
| `src/data_fetcher.py` | 数据拉取模块 |
| `data/etf_data.db` | ETF 历史数据库 |
| `data/trade_history.db` | 交易历史数据库 |


