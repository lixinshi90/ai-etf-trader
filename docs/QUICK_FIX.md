# 快速修复指南 - Request Timeout 问题

## 问题描述

```
510050 AI决策失败：Request timed out.
159915 AI决策失败：Request timed out.
510300 AI决策失败：Request timed out.
```

## 快速修复步骤

### 步骤 1：诊断系统（5分钟）

```bash
cd 《期末综合实验报告》
python -m src.diagnose
```

这会检查：
- ✅ 环境变量配置
- ✅ 依赖库安装
- ✅ API 连接状态
- ✅ 数据库状态

### 步骤 2：创建 .env 配置文件（2分钟）

在项目根目录创建 `.env` 文件，内容如下：

```env
OPENAI_API_KEY=sk-your-api-key-here
MODEL_NAME=gpt-4o-mini
TIMEOUT_SECONDS=120
MAX_RETRIES=5
FALLBACK_MODELS=gpt-3.5-turbo,gpt-4
```

**关键参数说明：**
- `TIMEOUT_SECONDS=120` - 增加超时时间到 120 秒（之前是 60 秒）
- `MAX_RETRIES=5` - 增加重试次数到 5 次（之前是 3 次）
- `FALLBACK_MODELS` - 如果主模型失败，自动尝试备用模型

### 步骤 3：运行系统（1分钟）

```bash
python -m src.main
```

预期输出：
```
AI ETF Trader 启动中...
=== 2025-11-25 19:15:51 每日任务开始 ===
调用模型 gpt-4o-mini（第1次尝试）...
✅ 510050 AI决策: buy (置信度: 0.85)
✅ 159915 AI决策: hold (置信度: 0.60)
✅ 510300 AI决策: sell (置信度: 0.75)
当前总资产: 100000.00 元
=== 每日任务结束 ===
```

## 如果仍然超时？

### 方案 A：增加超时时间

修改 `.env` 文件：

```env
TIMEOUT_SECONDS=180  # 改为 180 秒
MAX_RETRIES=5
```

### 方案 B：使用更快的模型

```env
MODEL_NAME=gpt-3.5-turbo  # 比 gpt-4o-mini 更快
TIMEOUT_SECONDS=120
```

### 方案 C：使用国内代理服务

如果 OpenAI 官方 API 不稳定，使用国内兼容服务：

#### DeepSeek 示例
```env
BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-deepseek-key-here
MODEL_NAME=deepseek-chat
TIMEOUT_SECONDS=120
```

#### Groq 示例
```env
BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=gsk-groq-key-here
MODEL_NAME=mixtral-8x7b-32768
TIMEOUT_SECONDS=120
```

### 方案 D：减少数据量

编辑 `src/main.py`，找到这一行：

```python
latest_dfs[etf] = df.tail(200)  # 取近200条
```

改为：

```python
latest_dfs[etf] = df.tail(100)  # 取近100条
```

更少的数据 = 更快的 API 响应

## 已应用的改进

系统已自动应用以下改进：

| 改进项 | 之前 | 现在 | 说明 |
|------|------|------|------|
| 超时时间 | 60 秒 | 120 秒 | 给 API 更多时间响应 |
| 重试次数 | 3 次 | 5 次 | 更多重试机会 |
| 重试策略 | 固定延迟 | 指数退避 | 5s, 10s, 20s, 40s, 80s |
| 回退模型 | 无 | 有 | gpt-3.5-turbo, gpt-4 |
| 错误处理 | 中断 | 继续 | 失败时使用默认策略 |
| 日志输出 | 简单 | 详细 | 便于调试 |

## 验证修复

运行诊断脚本验证：

```bash
python -m src.diagnose
```

输出应该显示：
```
诊断总结
============================================================
环境变量: 通过
依赖库: 通过
API 连接: 通过

============================================================
所有检查通过！系统已准备就绪。
运行: python -m src.main
```

## 常见问题

### Q: 为什么还是超时？

A: 可能的原因：
1. **API 密钥无效** - 检查 OPENAI_API_KEY 是否正确
2. **账户余额不足** - 检查 OpenAI 账户余额
3. **网络问题** - 尝试 ping api.openai.com
4. **模型不存在** - 检查 MODEL_NAME 是否正确
5. **高峰期拥堵** - 等待几分钟后重试

### Q: 如何跳过 AI 决策？

A: 编辑 `src/main.py`，在 `daily_task` 函数中注释掉 AI 决策部分：

```python
# 3) 获取AI决策并执行交易
for etf in ETF_LIST:
    # 使用固定策略而不是 AI 决策
    decision = {"decision": "hold", "confidence": 1.0}
    if etf in current_prices:
        executor.execute_trade(etf, decision, current_prices[etf])
```

### Q: 如何查看 API 调用日志？

A: 查看以下目录：
- `decisions/` - AI 决策记录
- `prompts/` - 提示词和消息

```bash
ls -lt decisions/ | head -5
cat decisions/20251125_510050_*.json
```

## 获取帮助

1. 查看完整配置指南：`CONFIG_GUIDE.md`
2. 运行诊断工具：`python -m src.diagnose`
3. 检查日志文件：`logs/` 目录
4. 查看决策记录：`decisions/` 目录

## 下一步

修复超时问题后，可以考虑：

1. **优化 Prompt** - 简化分析要求，加快响应
2. **并发处理** - 同时调用多个 ETF 的 AI 决策
3. **本地缓存** - 避免重复调用同一 ETF 的决策
4. **性能监控** - 记录 API 响应时间和成本

详见 `CONFIG_GUIDE.md` 中的"性能优化建议"部分。


