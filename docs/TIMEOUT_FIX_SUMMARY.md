# Request Timeout 问题修复总结

## 问题现象

```
510050 AI决策失败：Request timed out.
159915 AI决策失败：Request timed out.
510300 AI决策失败：Request timed out.
```

系统在调用 OpenAI API 获取 AI 决策时频繁超时，导致交易无法执行。

## 根本原因

1. **超时时间过短** - 默认 60 秒不足以应对 OpenAI API 的响应延迟
2. **重试机制不足** - 只有 3 次重试，且没有指数退避策略
3. **缺乏回退方案** - 主模型失败时没有备用模型
4. **错误处理不完善** - 单个 ETF 的失败导致整个流程中断

## 已应用的修复

### 1. 修改文件：`src/ai_decision.py`

#### 改进 1：增加超时时间和重试次数

```python
# 之前
timeout_s = float(os.getenv("TIMEOUT_SECONDS", "60"))
max_retries = int(os.getenv("MAX_RETRIES", "3"))
fallback_models_env = os.getenv("FALLBACK_MODELS", "")

# 现在
timeout_s = float(os.getenv("TIMEOUT_SECONDS", "120"))  # 增加到120秒
max_retries = int(os.getenv("MAX_RETRIES", "5"))  # 增加到5次
fallback_models_env = os.getenv("FALLBACK_MODELS", "gpt-3.5-turbo,gpt-4")
```

#### 改进 2：改进重试逻辑和日志

```python
# 添加更详细的日志输出
print(f"调用模型 {m}（第{attempt}次尝试）...")
print(f"❌ 模型{m}调用失败（第{attempt}次）：{e}")
print(f"⏳ {wait}秒后重试...")
print(f"模型 {m} 调用成功！")

# 改进重试延迟策略
wait = 5 * (2 ** (attempt - 1))  # 5s, 10s, 20s, 40s, 80s
```

### 2. 修改文件：`src/main.py`

#### 改进：改进错误处理，使用默认策略

```python
# 之前
try:
    decision = get_ai_decision(etf, df)
    print(f"{etf} AI决策: {decision.get('decision')}")
except Exception as e:
    print(f"{etf} AI决策失败：{e}")
    # 没有后续处理，交易无法执行

# 现在
try:
    decision = get_ai_decision(etf, df)
    print(f"✅ {etf} AI决策: {decision.get('decision')}")
except Exception as e:
    print(f"⚠️ {etf} AI决策失败：{e}")
    print(f"📌 {etf} 使用默认策略：持有")
    # 使用默认的 hold 策略，确保交易继续
    default_decision = {
        "decision": "hold",
        "confidence": 0.0,
        "reasoning": f"AI 调用失败，使用默认策略。错误：{str(e)}"
    }
    if etf in current_prices:
        executor.execute_trade(etf, default_decision, current_prices[etf])
```

## 新增文件

### 1. `CONFIG_GUIDE.md` - 完整配置指南

包含：
- 问题诊断
- 已应用的改进说明
- 配置方法（.env 文件、环境变量、代理服务）
- 调试建议
- 性能优化建议
- 常见问题解答

### 2. `QUICK_FIX.md` - 快速修复指南

包含：
- 3 步快速修复流程
- 如果仍然超时的 4 个解决方案
- 已应用改进的对比表
- 常见问题解答

### 3. `src/diagnose.py` - 诊断脚本

功能：
- 检查环境变量配置
- 检查依赖库安装
- 测试 API 连接
- 检查数据库状态
- 生成诊断报告

使用方式：
```bash
python -m src.diagnose
```

## 改进对比表

| 方面 | 修复前 | 修复后 | 改进 |
|------|-------|-------|------|
| 超时时间 | 60 秒 | 120 秒 | +100% |
| 重试次数 | 3 次 | 5 次 | +67% |
| 重试延迟 | 固定 | 指数退避 | 更智能 |
| 回退模型 | 无 | 2 个 | 更可靠 |
| 错误处理 | 中断 | 继续 | 更健壮 |
| 日志详细度 | 低 | 高 | 更易调试 |

## 使用指南

### 快速开始（推荐）

1. **运行诊断**
   ```bash
   python -m src.diagnose
   ```

2. **创建配置文件**
   
   在项目根目录创建 `.env` 文件：
   ```env
   OPENAI_API_KEY=sk-your-key
   TIMEOUT_SECONDS=120
   MAX_RETRIES=5
   ```

3. **运行系统**
   ```bash
   python -m src.main
   ```

### 如果仍然超时

查看 `QUICK_FIX.md` 中的"如果仍然超时？"部分，有 4 个解决方案：
- 方案 A：增加超时时间到 180 秒
- 方案 B：使用 gpt-3.5-turbo 模型
- 方案 C：使用国内代理服务（DeepSeek/Groq）
- 方案 D：减少数据量

## 配置选项

### 环境变量

| 变量 | 默认值 | 说明 |
|------|-------|------|
| OPENAI_API_KEY | 无 | OpenAI API 密钥（必需） |
| MODEL_NAME | gpt-4o-mini | 主模型 |
| TIMEOUT_SECONDS | 120 | API 超时时间（秒） |
| MAX_RETRIES | 5 | 最大重试次数 |
| FALLBACK_MODELS | gpt-3.5-turbo,gpt-4 | 回退模型列表 |
| BASE_URL | 无 | API 基础 URL（用于代理） |

### 创建 .env 文件示例

```env
# 官方 OpenAI API
OPENAI_API_KEY=sk-proj-xxx...
MODEL_NAME=gpt-4o-mini
TIMEOUT_SECONDS=120
MAX_RETRIES=5

# 或使用 DeepSeek 代理
# BASE_URL=https://api.deepseek.com/v1
# OPENAI_API_KEY=sk-deepseek-xxx...
# MODEL_NAME=deepseek-chat
```

## 验证修复

修复完成后，运行以下命令验证：

```bash
# 1. 诊断系统
python -m src.diagnose

# 2. 运行主程序
python -m src.main

# 3. 查看决策记录
ls -lt decisions/ | head -5
cat decisions/20251125_510050_*.json
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

## 后续优化建议

1. **性能优化**
   - 实现并发调用多个 ETF 的 AI 决策
   - 优化 Prompt，减少 token 使用
   - 实现更智能的缓存策略

2. **监控和告警**
   - 记录 API 响应时间
   - 监控成本使用
   - 设置告警阈值

3. **模型选择**
   - 根据不同 ETF 选择不同模型
   - 定期评估模型性能
   - 考虑使用更新的模型

4. **容错能力**
   - 实现更复杂的回退策略
   - 支持离线模式
   - 实现本地决策模型

## 文件清单

### 修改的文件
- `src/ai_decision.py` - 增加超时和重试逻辑
- `src/main.py` - 改进错误处理

### 新增的文件
- `CONFIG_GUIDE.md` - 完整配置指南
- `QUICK_FIX.md` - 快速修复指南
- `src/diagnose.py` - 诊断脚本
- `TIMEOUT_FIX_SUMMARY.md` - 本文件

## 支持和反馈

如有问题，请：

1. 运行诊断脚本：`python -m src.diagnose`
2. 查看日志文件：`logs/` 目录
3. 查看决策记录：`decisions/` 目录
4. 参考配置指南：`CONFIG_GUIDE.md`

## 总结

通过以上修复，系统的可靠性和容错能力得到了显著提升：

✅ **超时时间加倍** - 从 60 秒增加到 120 秒
✅ **重试机制改进** - 从 3 次增加到 5 次，使用指数退避
✅ **回退模型支持** - 主模型失败时自动尝试备用模型
✅ **错误处理完善** - 单个 ETF 失败不影响其他 ETF
✅ **诊断工具齐全** - 提供完整的诊断和配置指南

系统现在能够更好地应对 OpenAI API 的延迟和不稳定性，确保交易流程的连贯性。


