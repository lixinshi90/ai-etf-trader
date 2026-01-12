# 修复检查清单

## 代码修改验证

### ✅ 检查 1：ai_decision.py 超时时间

```bash
grep "TIMEOUT_SECONDS.*120" src/ai_decision.py
```

**预期：** 显示 `timeout_s = float(os.getenv("TIMEOUT_SECONDS", "120"))`

- [ ] 已验证

### ✅ 检查 2：ai_decision.py 重试次数

```bash
grep "MAX_RETRIES.*5" src/ai_decision.py
```

**预期：** 显示 `max_retries = int(os.getenv("MAX_RETRIES", "5"))`

- [ ] 已验证

### ✅ 检查 3：ai_decision.py 回退模型

```bash
grep "FALLBACK_MODELS.*gpt" src/ai_decision.py
```

**预期：** 显示 `fallback_models_env = os.getenv("FALLBACK_MODELS", "gpt-3.5-turbo,gpt-4")`

- [ ] 已验证

### ✅ 检查 4：main.py 错误处理

```bash
grep "使用默认策略" src/main.py
```

**预期：** 显示错误处理代码

- [ ] 已验证

## 配置文件检查

### ✅ 检查 5：.env 文件存在

```bash
ls -la .env
```

**预期：** 显示 `.env` 文件

- [ ] 已创建

### ✅ 检查 6：.env 文件内容

```bash
cat .env
```

**预期：** 显示以下内容：
```
OPENAI_API_KEY=sk-...
MODEL_NAME=gpt-4o-mini
TIMEOUT_SECONDS=120
MAX_RETRIES=5
FALLBACK_MODELS=gpt-3.5-turbo,gpt-4
```

- [ ] 已验证

## 依赖库检查

### ✅ 检查 7：OpenAI 库

```bash
python -c "import openai; print(openai.__version__)"
```

**预期：** 显示版本号（如 1.3.0 或更高）

- [ ] 已验证

### ✅ 检查 8：Pandas 库

```bash
python -c "import pandas; print(pandas.__version__)"
```

**预期：** 显示版本号

- [ ] 已验证

### ✅ 检查 9：python-dotenv 库

```bash
python -c "import dotenv; print('OK')"
```

**预期：** 显示 `OK`

- [ ] 已验证

## 诊断工具检查

### ✅ 检查 10：诊断脚本存在

```bash
ls -la src/diagnose.py
```

**预期：** 显示 `src/diagnose.py` 文件

- [ ] 已验证

### ✅ 检查 11：运行诊断脚本

```bash
python -m src.diagnose
```

**预期：** 显示诊断报告，所有检查通过

- [ ] 已验证

## API 连接检查

### ✅ 检查 12：API 密钥有效

诊断脚本应显示：
```
API 连接成功!
模型响应: OK
```

- [ ] 已验证

### ✅ 检查 13：网络连接

```bash
ping api.openai.com
```

**预期：** 能够连接到 OpenAI API

- [ ] 已验证

## 系统运行检查

### ✅ 检查 14：主程序启动

```bash
python -m src.main
```

**预期：** 显示启动信息，无错误

- [ ] 已验证

### ✅ 检查 15：数据更新

**预期：** 显示类似以下信息：
```
已更新 510050 数据
已更新 159915 数据
已更新 510300 数据
```

- [ ] 已验证

### ✅ 检查 16：AI 决策成功

**预期：** 显示类似以下信息：
```
✅ 510050 AI决策: buy (置信度: 0.85)
✅ 159915 AI决策: hold (置信度: 0.60)
✅ 510300 AI决策: sell (置信度: 0.75)
```

**不应该显示：**
```
❌ 510050 AI决策失败：Request timed out.
```

- [ ] 已验证

### ✅ 检查 17：交易执行

**预期：** 系统继续运行，显示资产信息：
```
当前总资产: 100000.00 元
```

- [ ] 已验证

## 文件检查

### ✅ 检查 18：决策记录

```bash
ls -la decisions/
```

**预期：** 显示最新的决策 JSON 文件

- [ ] 已验证

### ✅ 检查 19：Prompt 记录

```bash
ls -la prompts/
```

**预期：** 显示最新的 Prompt 文本文件

- [ ] 已验证

### ✅ 检查 20：数据库

```bash
ls -la data/
```

**预期：** 显示 `etf_data.db` 和 `trade_history.db`

- [ ] 已验证

## 文档检查

### ✅ 检查 21：配置指南

```bash
ls -la CONFIG_GUIDE.md
```

**预期：** 文件存在

- [ ] 已验证

### ✅ 检查 22：快速修复指南

```bash
ls -la QUICK_FIX.md
```

**预期：** 文件存在

- [ ] 已验证

### ✅ 检查 23：修复总结

```bash
ls -la TIMEOUT_FIX_SUMMARY.md
```

**预期：** 文件存在

- [ ] 已验证

### ✅ 检查 24：执行步骤

```bash
ls -la EXECUTE_STEPS.md
```

**预期：** 文件存在

- [ ] 已验证

## 性能检查

### ✅ 检查 25：API 响应时间

运行系统后，查看日志中的响应时间。

**预期：** 响应时间在 10-60 秒内（取决于模型和网络）

- [ ] 已验证

### ✅ 检查 26：重试次数

如果遇到超时，系统应该自动重试。

**预期：** 日志显示重试信息，如：
```
❌ 模型gpt-4o-mini调用失败（第1次）：...
⏳ 5秒后重试...
```

- [ ] 已验证

## 备用方案检查

### ✅ 检查 27：回退模型

如果主模型失败，系统应该尝试备用模型。

**预期：** 日志显示：
```
模型gpt-4o-mini调用失败且达到最大重试次数：...
尝试回退模型...
调用模型 gpt-3.5-turbo（第1次尝试）...
```

- [ ] 已验证

### ✅ 检查 28：默认策略

如果所有模型都失败，系统应该使用默认策略。

**预期：** 日志显示：
```
⚠️ 510050 AI决策失败：...
📌 510050 使用默认策略：持有
```

- [ ] 已验证

## 最终验证

### ✅ 检查 29：系统稳定性

运行系统 5 分钟，观察是否有错误。

**预期：** 系统正常运行，无异常

- [ ] 已验证

### ✅ 检查 30：完整流程

完整运行一次 `daily_task`：
1. 数据更新 ✅
2. AI 决策 ✅
3. 交易执行 ✅
4. 资产更新 ✅

**预期：** 所有步骤成功完成

- [ ] 已验证

## 总结

- [ ] 所有代码修改已验证
- [ ] 配置文件已创建
- [ ] 依赖库已安装
- [ ] 诊断工具已运行
- [ ] API 连接已测试
- [ ] 系统已成功运行
- [ ] 所有文档已创建
- [ ] 性能符合预期
- [ ] 备用方案已验证
- [ ] 系统稳定性已确认

**修复状态：** ✅ 完成

**下一步：** 
- 定期监控系统运行情况
- 根据需要调整配置参数
- 考虑性能优化

---

**修复日期：** 2025-11-25
**修复人员：** AI Assistant
**验证状态：** 待确认


