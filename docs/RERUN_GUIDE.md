# 重新执行今日任务指南

日期：2025-12-22
状态：今日任务已执行，但净值数据异常

---

## 🔍 问题诊断

### 当前状态
- **今日净值（数据库）**：110049.91 ❌
- **理论净值（计算）**：121818.35 ✓
- **差异**：11768.44 元（约 11.8%）

### 原因分析
今日净值 110049.91 是**错误的**，可能由以下原因导致：
1. 之前的代码修改导致计算逻辑错误
2. `/api/portfolio` 接口的错误值被写入数据库
3. 今日任务执行时使用了错误的价格数据

### 今日持仓实际情况
- **现金**：81030.56
- **持仓**：4只ETF，市值 40787.79
  - 510300: 2525.61 × 4.730 = 11946.14
  - 513500: 1631.20 × 2.456 = 4006.22
  - 159928: 16071.43 × 0.809 = 13001.79
  - 512040: 10353.14 × 1.143 = 11833.64
- **正确总资产**：121818.35

---

## 💡 解决方案对比

### 方案一：仅修正净值（快速，5分钟）

**优点**：
- 快速修复数据
- 不影响已有交易记录
- 风险最小

**缺点**：
- 不会产生新的交易
- 不会应用新的风控参数
- 新增7只ETF不参与

**执行步骤**：
```bash
python fix_today_equity.py
# 输入 y 确认修正
```

---

### 方案二：重新执行今日任务（彻底，30分钟）

**优点**：
- 应用所有新配置（风控、仓位、标的池）
- 新增7只ETF参与决策
- 可以调整AI调用上限（如改为12次）
- 获得完整的今日交易记录

**缺点**：
- 会覆盖今日已有的8个AI决策
- 可能产生不同的交易决策
- 需要重新调用AI（消耗API额度）

**执行步骤**：

#### 1. 备份数据库（必须）
```bash
copy data\trade_history.db data\trade_history.backup_20251222_before_rerun.db
```

#### 2. 删除今日数据
```bash
python -c "
import sqlite3
conn = sqlite3.connect('data/trade_history.db')
cursor = conn.cursor()
# 删除今日净值
cursor.execute(\"DELETE FROM daily_equity WHERE date = '2025-12-22'\")
# 删除今日交易（如果有）
cursor.execute(\"DELETE FROM trades WHERE date >= '2025-12-22'\")
conn.commit()
conn.close()
print('✓ 已删除今日数据')
"
```

#### 3. 调整AI调用上限（可选）
编辑 `.env` 文件：
```
DAILY_AI_CALLS_LIMIT=12  # 从8改为12，覆盖更多标的
```

#### 4. 重新执行任务
```bash
python -m src.daily_once
```

#### 5. 验证结果
```bash
# 检查新的净值
python -c "
import sqlite3
import pandas as pd
conn = sqlite3.connect('data/trade_history.db')
df = pd.read_sql_query('SELECT date, equity FROM daily_equity WHERE date = \"2025-12-22\"', conn)
if not df.empty:
    print(f'今日净值: {df.iloc[0][\"equity\"]:.2f}')
else:
    print('今日净值未生成')
conn.close()
"

# 检查交易记录
python -c "
import sqlite3
import pandas as pd
conn = sqlite3.connect('data/trade_history.db')
df = pd.read_sql_query('SELECT COUNT(*) as cnt FROM trades WHERE date >= \"2025-12-22\"', conn)
print(f'今日交易: {df.iloc[0][\"cnt\"]} 笔')
conn.close()
"
```

---

## 🎯 推荐方案

### 如果您想要：

#### A. 快速修复数据，明天再用新配置
→ **选择方案一**（修正净值）
- 今天只修正数据
- 明天（12月23日）自动使用新配置

#### B. 今天就测试新配置和新标的
→ **选择方案二**（重新执行）
- 立即应用所有优化
- 新增ETF参与决策
- 可能产生新的交易

---

## ⚠️ 重新执行的影响详解

### 会发生什么

1. **AI决策**
   - 重新调用AI（8-12次，取决于DAILY_AI_CALLS_LIMIT）
   - 可能产生不同的决策（市场在变化）
   - 新增7只ETF会参与决策

2. **交易执行**
   - 根据新决策可能产生买入/卖出
   - 应用新的风控参数（止损/止盈）
   - 使用新的仓位参数（15%基础仓位）

3. **数据更新**
   - 覆盖今日净值（从110049.91改为正确值）
   - 可能新增交易记录
   - 更新持仓状态

### 不会发生什么

- ✓ 不会影响历史数据（12月19日及之前）
- ✓ 不会改变现有持仓（除非产生新交易）
- ✓ 不会影响已有的43笔交易记录

---

## 📊 建议

### 我的推荐：方案二（重新执行）

**理由**：
1. 今日净值数据确实错误，需要修正
2. 今天是交易日，可以正常执行
3. 新配置已就绪，应该尽快应用
4. 新增7只ETF应该参与决策
5. 已有备份，风险可控

### 执行前准备

1. **确认AI API配置正确**（如使用AI）
2. **确认网络连接正常**（拉取行情需要）
3. **确认有足够时间**（约30分钟）
4. **确认已备份数据库**

---

## 🚀 快速执行命令

```bash
# 1. 备份
copy data\trade_history.db data\trade_history.backup_20251222_before_rerun.db

# 2. 删除今日数据
python -c "import sqlite3; conn = sqlite3.connect('data/trade_history.db'); cursor = conn.cursor(); cursor.execute('DELETE FROM daily_equity WHERE date = \"2025-12-22\"'); cursor.execute('DELETE FROM trades WHERE date >= \"2025-12-22\"'); conn.commit(); conn.close(); print('✓ 已删除今日数据')"

# 3. 调整AI上限（可选）
# 编辑 .env: DAILY_AI_CALLS_LIMIT=12

# 4. 重新执行
python -m src.daily_once

# 5. 验证
python check_today_status.py
```

---

**决策权在您**：
- 方案一：安全保守，明天再用新配置
- 方案二：积极主动，今天就测试优化效果

两种方案都是可行的，根据您的风险偏好选择即可。

