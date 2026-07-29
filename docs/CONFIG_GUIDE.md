# AI ETF Trader 配置指南

## 问题诊断

你遇到的 `Request timed out` 错误通常由以下原因引起：

1. **API 响应缓慢** - OpenAI 服务在高峰期可能响应慢
2. **网络连接问题** - 国内网络访问 OpenAI 可能不稳定
3. **超时设置过短** - 默认 60 秒可能不够
4. **模型队列拥堵** - gpt-4o-mini 在高峰期可能排队

## 已应用的改进

### 1. 增加超时时间
- **之前**：60 秒
- **现在**：120 秒
- **可配置**：通过 `TIMEOUT_SECONDS` 环境变量

### 2. 增加重试次数
- **之前**：3 次
- **现在**：5 次
- **策略**：指数退避 (5s, 10s, 20s, 40s, 80s)
- **可配置**：通过 `MAX_RETRIES` 环境变量

### 3. 添加回退模型
- **主模型**：gpt-4o-mini
- **回退模型**：gpt-3.5-turbo, gpt-4
- **可配置**：通过 `FALLBACK_MODELS` 环境变量

### 4. 改进错误处理
- AI 决策失败时使用默认的 "hold" 策略
- 系统不会因为 API 超时而中断
- 更详细的日志输出便于调试

## 配置方法

### 方法 1：创建 .env 文件（推荐）

在项目根目录创建 `.env` 文件：

```env
# OpenAI API 密钥（必需）
OPENAI_API_KEY=sk-xxx...

# 模型名称
MODEL_NAME=gpt-4o-mini

# 超时时间（秒）
TIMEOUT_SECONDS=120

# 最大重试次数
MAX_RETRIES=5

# 回退模型列表
FALLBACK_MODELS=gpt-3.5-turbo,gpt-4
```

### 方法 2：设置环境变量

```bash
# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-xxx..."
$env:TIMEOUT_SECONDS="120"
$env:MAX_RETRIES="5"

# Linux/Mac
export OPENAI_API_KEY="sk-xxx..."
export TIMEOUT_SECONDS="120"
export MAX_RETRIES="5"
```

### 方法 3：使用国内代理服务

如果 OpenAI 官方 API 不稳定，可以使用兼容服务：

```env
# DeepSeek 示例
BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-xxx...
MODEL_NAME=deepseek-chat

# 或其他兼容服务
# BASE_URL=https://api.groq.com/openai/v1
# MODEL_NAME=mixtral-8x7b-32768
```

## 调试建议

### 1. 增加超时时间

如果仍然超时，尝试增加：

```env
TIMEOUT_SECONDS=180  # 或 240
```

### 2. 减少数据量

在 `main.py` 中修改数据范围：

```python
latest_dfs[etf] = df.tail(100)  # 从 200 改为 100
```

### 3. 使用更快的模型

```env
MODEL_NAME=gpt-3.5-turbo  # 比 gpt-4o-mini 更快
```

### 4. 检查网络连接

```bash
# 测试到 OpenAI 的连接
ping api.openai.com

# 或使用 curl 测试
curl -I https://api.openai.com/v1/models
```

## 监控日志

系统会在以下目录保存日志和决策记录：

- `logs/` - 运行日志
- `decisions/` - AI 决策记录
- `prompts/` - 提示词和消息记录

查看最新的决策：

```bash
ls -lt decisions/ | head -10
cat decisions/20251125_510050_*.json
```

## 性能优化建议

### 1. 缓存策略

系统已实现当日缓存，同一 ETF 在同一天只会调用一次 API。

### 2. 批量处理

可以修改 `main.py` 实现并发调用多个 ETF 的 AI 决策：

```python
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=3) as executor:
    futures = {executor.submit(get_ai_decision, etf, latest_dfs[etf]): etf 
               for etf in ETF_LIST}
    for future in futures:
        etf = futures[future]
        try:
            decision = future.result()
        except Exception as e:
            print(f"{etf} 决策失败：{e}")
```

### 3. 简化 Prompt

在 `prompts.py` 中减少数据量或简化分析要求，可以加快 API 响应。

## 常见问题

### Q: 还是超时怎么办？

A: 尝试以下步骤：
1. 增加 `TIMEOUT_SECONDS` 到 240
2. 减少 `MAX_RETRIES` 到 3（避免等待过长）
3. 使用 `gpt-3.5-turbo` 替代 `gpt-4o-mini`
4. 考虑使用国内代理服务

### Q: 如何跳过 AI 决策直接交易？

A: 修改 `main.py` 中的 `daily_task` 函数，使用固定策略：

```python
decision = {"decision": "hold", "confidence": 1.0}
executor.execute_trade(etf, decision, current_prices[etf])
```

### Q: 如何查看 API 调用成本？

A: 在 OpenAI 官网查看 Usage 页面，或在代码中记录 token 使用量。

## 联系支持

如果问题仍未解决，请检查：
1. API 密钥是否正确
2. 账户是否有足够的余额
3. 网络连接是否正常
4. 模型名称是否正确


