# 🔍 AI ETF Trader - 数据为空原因诊断报告

**诊断时间**: 2025-11-26 11:24:51  
**系统状态**: 部分功能正常，交易执行链条中断

---

## 📋 问题现象

| 接口 | 返回状态 | 数据 |
|------|--------|------|
| `/api/decisions` | ✅ 正常 | 6条决策记录 |
| `/api/trades` | ❌ 异常 | 空数组 `[]` |
| `/api/performance` | ❌ 异常 | 空数据 `{"dates":[], "values":[]}` |
| `/api/metrics` | ❌ 异常 | 全0 `{...0.0...}` |

---

## 🔎 根本原因分析

### 问题链条

```
数据更新失败 → 无当前价格 → 交易无法执行 → 数据库无交易 → 接口返回空
```

### 详细分析

#### 1️⃣ **数据更新阶段 - 网络连接失败**

**日志记录**:
```
2025-11-26 11:24:52,675 WARNING 更新 510050 失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2025-11-26 11:24:53,164 WARNING 更新 159915 失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
2025-11-26 11:24:53,973 WARNING 更新 510300 失败：('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
```

**问题**:
- 三个ETF数据更新全部失败
- 错误类型: `RemoteDisconnected` - 远程服务器主动关闭连接
- 可能原因:
  - 数据源服务器不稳定
  - 网络连接中断
  - 请求被限流或拒绝

**影响**:
- `current_prices` 字典为空或不完整
- 无法获取最新交易价格

---

#### 2️⃣ **AI决策阶段 - 正常工作**

**日志记录**:
```
2025-11-26 11:24:57,840 INFO HTTP Request: POST https://open.bigmodel.cn/api/paas/v4/chat/completions "HTTP/1.1 200 OK"
2025-11-26 11:24:57,861 INFO 510050 AI决策: hold (置信度: 0.6)
2025-11-26 11:25:01,037 INFO 159915 AI决策: hold (置信度: 0.6)
2025-11-26 11:25:06,479 INFO 510300 AI决策: hold (置信度: 0.6)
```

**状态**: ✅ 正常
- GLM-4-Air 模型调用成功
- 三个ETF都获得了决策
- 所有决策都是 `hold`（持有）

**为什么都是hold?**
- 数据更新失败 → 无法获取最新价格
- AI基于历史数据分析 → 保守决策为 `hold`
- 这是合理的风险管理行为

---

#### 3️⃣ **交易执行阶段 - 链条中断**

**代码位置**: `src/main.py` 第 ~180 行

```python
if etf in current_prices:
    executor.execute_trade(etf, final_decision, current_prices[etf])
```

**问题分析**:

1. **条件检查失败**:
   ```python
   if etf in current_prices:  # ← current_prices 为空或不包含该ETF
       executor.execute_trade(...)  # ← 这行不会执行
   ```

2. **即使执行，也不会产生交易**:
   ```python
   # src/trade_executor.py
   def execute_trade(self, etf_code, decision, current_price):
       action = str(decision.get("decision", "hold")).lower()
       
       if action == "buy" and etf_code not in self.positions:
           # 执行买入逻辑
           ...
       elif action == "sell" and etf_code in self.positions:
           # 执行卖出逻辑
           ...
       else:
           # hold 或无法卖出/买入 → 不执行任何操作
           pass  # ← 这里什么都不做
   ```

**结果**:
- 没有 `INSERT INTO trades` 语句执行
- 数据库 `trades` 表保持为空

---

#### 4️⃣ **数据库查询阶段 - 级联为空**

**接口实现** (`src/web_app.py`):

```python
@app.route("/api/trades")
def get_trades():
    trades = pd.read_sql_query("SELECT * FROM trades ...", conn)
    return jsonify(trades.to_dict("records"))  # ← 空DataFrame → 空列表

@app.route("/api/performance")
def get_performance():
    trades = pd.read_sql_query("SELECT * FROM trades ...", conn)
    if trades.empty:
        return jsonify({"dates": [], "values": []})  # ← 直接返回空

@app.route("/api/metrics")
def get_metrics():
    metrics = calculate_performance(_db_path())  # ← 基于trades表计算
    # 无交易 → 所有指标为0
```

**结果**: 三个接口全部返回空/零值

---

## 📊 执行流程图

```
daily_once.py
    ↓
main.daily_task()
    ↓
[1] fetch_etf_data() ❌ 失败 → current_prices 为空
    ↓
[2] get_ai_decision() ✅ 成功 → 决策为 hold
    ↓
[3] execute_trade(decision='hold', price=None) ❌ 不执行
    ↓
[4] trades 表保持为空
    ↓
web_app.py 接口查询 → 全部返回空/零值
```

---

## 🛠️ 解决方案

### 方案 A: 修复网络连接（推荐）

**优先级**: ⭐⭐⭐⭐⭐

**步骤**:
1. 检查数据源服务器状态
2. 添加连接重试机制
3. 增加超时时间配置
4. 考虑使用代理或VPN

**修改文件**: `src/data_fetcher.py`

```python
# 添加重试逻辑
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def create_session_with_retry():
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session
```

---

### 方案 B: 使用缓存数据（备选）

**优先级**: ⭐⭐⭐⭐

**步骤**:
1. 数据更新失败时，使用数据库中的最新历史数据
2. 记录使用缓存的事实
3. 继续执行交易流程

**修改文件**: `src/main.py`

```python
def daily_task(executor, etf_list, daily_ai_limit):
    # ...
    for etf in etf_list:
        try:
            df = fetch_etf_data(etf, days=700)
            save_to_db(df, etf, db_path=_etf_db_path())
            logger.info("已更新 %s 数据", etf)
        except Exception as e:
            logger.warning("更新 %s 失败，使用缓存数据: %s", etf, e)
            # ← 继续使用数据库中的历史数据
            # 不中断流程
```

---

### 方案 C: 添加测试交易数据（演示用）

**优先级**: ⭐⭐⭐

**步骤**:
1. 创建初始化脚本，插入测试交易数据
2. 用于演示和测试前端界面
3. 不影响实际交易逻辑

**创建文件**: `src/init_demo_trades.py`

```python
def init_demo_trades():
    """为演示目的插入示例交易数据"""
    executor = TradeExecutor()
    
    # 模拟买入
    executor.execute_trade('510050', {
        'decision': 'buy',
        'confidence': 0.8,
        'reasoning': '演示数据：MA20上穿MA60'
    }, 2.5)
    
    # 模拟卖出
    executor.execute_trade('510050', {
        'decision': 'sell',
        'confidence': 0.7,
        'reasoning': '演示数据：获利了结'
    }, 2.6)
```

---

## 📈 当前系统状态评估

| 组件 | 状态 | 评分 |
|------|------|------|
| 数据获取 | ❌ 网络故障 | 1/5 |
| AI决策 | ✅ 正常工作 | 5/5 |
| 交易执行 | ⚠️ 无交易 | 2/5 |
| 数据库 | ✅ 正常 | 5/5 |
| Web前端 | ✅ 已优化 | 5/5 |
| **整体** | ⚠️ 部分功能 | **2.6/5** |

---

## 🎯 建议行动

### 立即行动（今天）
1. ✅ 检查网络连接和数据源服务器
2. ✅ 实施方案 B（使用缓存数据）
3. ✅ 测试修复效果

### 短期改进（本周）
1. 实施方案 A（添加重试机制）
2. 添加更详细的错误日志
3. 配置监控告警

### 长期优化（本月）
1. 实现多数据源备份
2. 添加数据质量检查
3. 优化交易决策逻辑

---

## 📝 附录：关键代码位置

| 文件 | 行号 | 功能 |
|------|------|------|
| `src/data_fetcher.py` | - | 数据获取 |
| `src/main.py` | ~180 | 交易执行条件 |
| `src/trade_executor.py` | ~120 | 交易执行逻辑 |
| `src/web_app.py` | ~40-90 | API接口 |
| `src/daily_once.py` | - | 一次性任务入口 |

---

**报告生成时间**: 2025-11-26  
**诊断工程师**: AI Assistant  
**状态**: 待处理


