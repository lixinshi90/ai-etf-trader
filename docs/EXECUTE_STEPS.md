# 执行步骤 - 解决 Request Timeout 问题

## 问题描述

你的 AI ETF Trader 系统出现以下错误：

```
510050 AI决策失败：Request timed out.
159915 AI决策失败：Request timed out.
510300 AI决策失败：Request timed out.
```

## 解决方案概览

已对系统进行了以下改进：

| 改进项 | 详情 |
|------|------|
| 超时时间 | 60 秒 → 120 秒 |
| 重试次数 | 3 次 → 5 次 |
| 重试策略 | 固定延迟 → 指数退避 |
| 回退模型 | 无 → gpt-3.5-turbo, gpt-4 |
| 错误处理 | 中断 → 继续执行 |

## 执行步骤

### 第 1 步：验证修改（1 分钟）

检查代码是否已正确修改：

```bash
# 检查 ai_decision.py 中的超时设置
grep "TIMEOUT_SECONDS" src/ai_decision.py
# 应该显示：timeout_s = float(os.getenv("TIMEOUT_SECONDS", "120"))

# 检查 ai_decision.py 中的重试次数
grep "MAX_RETRIES" src/ai_decision.py
# 应该显示：max_retries = int(os.getenv("MAX_RETRIES", "5"))

# 检查 main.py 中的错误处理
grep "使用默认策略" src/main.py
# 应该显示相关的错误处理代码
```

### 第 2 步：创建配置文件（2 分钟）

在项目根目录创建 `.env` 文件：

**Windows (PowerShell):**
```powershell
@"
OPENAI_API_KEY=sk-your-api-key-here
MODEL_NAME=gpt-4o-mini
TIMEOUT_SECONDS=120
MAX_RETRIES=5
FALLBACK_MODELS=gpt-3.5-turbo,gpt-4
"@ | Out-File -Encoding UTF8 .env
```

**Linux/Mac:**
```bash
cat > .env << 'EOF'
OPENAI_API_KEY=sk-your-api-key-here
MODEL_NAME=gpt-4o-mini
TIMEOUT_SECONDS=120
MAX_RETRIES=5
FALLBACK_MODELS=gpt-3.5-turbo,gpt-4
EOF
```

**或手动创建：**
1. 在项目根目录新建文件 `.env`
2. 添加以下内容：
```
OPENAI_API_KEY=sk-your-api-key-here
MODEL_NAME=gpt-4o-mini
TIMEOUT_SECONDS=120
MAX_RETRIES=5
FALLBACK_MODELS=gpt-3.5-turbo,gpt-4
```

### 第 3 步：运行诊断（3 分钟）

```bash
python -m src.diagnose
```

**预期输出：**
```
============================================================
环境变量检查
============================================================
OPENAI_API_KEY: sk-xxx...xxx
MODEL_NAME: gpt-4o-mini
TIMEOUT_SECONDS: 120
MAX_RETRIES: 5
FALLBACK_MODELS: gpt-3.5-turbo,gpt-4

============================================================
依赖库检查
============================================================
openai: 1.x.x
pandas: 2.x.x
python-dotenv: 已安装

============================================================
数据库检查
============================================================
ETF 数据库存在: ...
交易历史数据库存在: ...

============================================================
API 连接测试
============================================================
发送测试请求到 OpenAI API...
API 连接成功!
模型响应: OK
使用 tokens: 10

============================================================
诊断总结
============================================================
环境变量: 通过
依赖库: 通过
API 连接: 通过

============================================================
所有检查通过！系统已准备就绪。
运行: python -m src.main
```

### 第 4 步：运行系统（1 分钟）

```bash
python -m src.main
```

**预期输出：**
```
AI ETF Trader 启动中...
=== 2025-11-25 19:15:51 每日任务开始 ===
已保存 510050 数据到数据库: ...
已更新 510050 数据
已保存 159915 数据到数据库: ...
已更新 159915 数据
已保存 510300 数据到数据库: ...
已更新 510300 数据
调用模型 gpt-4o-mini（第1次尝试）...
✅ 510050 AI决策: buy (置信度: 0.85)
调用模型 gpt-4o-mini（第1次尝试）...
✅ 159915 AI决策: hold (置信度: 0.60)
调用模型 gpt-4o-mini（第1次尝试）...
✅ 510300 AI决策: sell (置信度: 0.75)
当前总资产: 100000.00 元
=== 每日任务结束 ===
```

## 如果仍然出现超时错误？

### 方案 A：增加超时时间

编辑 `.env` 文件，修改：

```env
TIMEOUT_SECONDS=180  # 改为 180 秒
```

然后重新运行：
```bash
python -m src.main
```

### 方案 B：使用更快的模型

编辑 `.env` 文件，修改：

```env
MODEL_NAME=gpt-3.5-turbo  # 改为 gpt-3.5-turbo
TIMEOUT_SECONDS=120
```

然后重新运行：
```bash
python -m src.main
```

### 方案 C：使用国内代理服务

如果 OpenAI 官方 API 不稳定，可以使用国内兼容服务。

**DeepSeek 示例：**

1. 注册 DeepSeek 账户并获取 API 密钥
2. 编辑 `.env` 文件：

```env
BASE_URL=https://api.deepseek.com/v1
OPENAI_API_KEY=sk-deepseek-key-here
MODEL_NAME=deepseek-chat
TIMEOUT_SECONDS=120
```

3. 重新运行：
```bash
python -m src.main
```

**Groq 示例：**

```env
BASE_URL=https://api.groq.com/openai/v1
OPENAI_API_KEY=gsk-groq-key-here
MODEL_NAME=mixtral-8x7b-32768
TIMEOUT_SECONDS=120
```

### 方案 D：减少数据量

编辑 `src/main.py`，找到这一行（大约第 60 行）：

```python
latest_dfs[etf] = df.tail(200)  # 取近200条
```

改为：

```python
latest_dfs[etf] = df.tail(100)  # 取近100条
```

然后重新运行：
```bash
python -m src.main
```

## 故障排查

### 问题 1：诊断脚本显示 "API 连接失败"

**原因可能：**
1. API 密钥无效
2. 账户余额不足
3. 网络连接问题

**解决方法：**
```bash
# 检查 API 密钥
echo $OPENAI_API_KEY  # Linux/Mac
echo %OPENAI_API_KEY%  # Windows

# 测试网络连接
ping api.openai.com

# 检查账户余额
# 登录 https://platform.openai.com/account/usage/overview
```

### 问题 2：仍然显示 "Request timed out"

**原因可能：**
1. API 服务器响应慢
2. 网络延迟高
3. 模型队列拥堵

**解决方法：**
1. 增加 `TIMEOUT_SECONDS` 到 240
2. 使用 `gpt-3.5-turbo` 替代 `gpt-4o-mini`
3. 使用国内代理服务
4. 等待几分钟后重试

### 问题 3：诊断脚本显示 "依赖库未安装"

**解决方法：**
```bash
pip install openai pandas python-dotenv
```

## 验证修复成功

修复成功的标志：

✅ 诊断脚本显示"所有检查通过"
✅ 主程序显示"AI决策"而不是"AI决策失败"
✅ 系统正常执行交易
✅ 决策记录保存到 `decisions/` 目录

## 查看决策记录

修复成功后，可以查看 AI 的决策记录：

```bash
# 列出最新的决策文件
ls -lt decisions/ | head -10

# 查看某个决策的详细内容
cat decisions/20251125_510050_*.json

# 查看某个决策的 Prompt
cat prompts/20251125_510050_*_prompt.txt
```

## 下一步

1. **定期监控** - 观察系统运行情况，记录 API 响应时间
2. **性能优化** - 如果需要，可以实现并发调用或其他优化
3. **模型选择** - 根据实际情况选择最合适的模型
4. **成本控制** - 监控 API 使用成本

## 获取帮助

- 完整配置指南：`CONFIG_GUIDE.md`
- 快速修复指南：`QUICK_FIX.md`
- 修复总结：`TIMEOUT_FIX_SUMMARY.md`
- 运行诊断：`python -m src.diagnose`

## 总结

通过以上步骤，你的 AI ETF Trader 系统应该能够正常运行，不再出现 Request Timeout 错误。

关键改进：
- ✅ 超时时间加倍（60s → 120s）
- ✅ 重试机制改进（3次 → 5次，指数退避）
- ✅ 回退模型支持（自动尝试备用模型）
- ✅ 错误处理完善（失败时使用默认策略）

祝你的量化交易系统运行顺利！


