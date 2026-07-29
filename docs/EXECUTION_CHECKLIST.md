# 系统优化执行清单

执行时间：2025-12-22
状态：等待用户执行

---

## ✅ 第一步：配置文件更新（已完成）

- [x] `config.yaml` 已更新风控和仓位参数
- [x] `env_config.txt` 已创建（环境变量模板）
- [x] `OPTIMIZATION_REPORT.md` 已生成（优化报告）

---

## 📋 第二步：创建 .env 文件（需用户执行）

### 操作步骤

1. **复制配置模板**
   ```bash
   # 在项目根目录执行
   cp env_config.txt .env
   ```

2. **编辑 .env 文件**
   - 打开 `.env` 文件
   - 填写 AI API 配置（如果使用AI决策）：
     ```
     AI_API_KEY=your_actual_api_key
     AI_API_BASE=https://api.openai.com/v1
     AI_MODEL=gpt-4
     ```
   - 其他参数保持默认即可

3. **验证配置**
   ```bash
   python validate_config.py
   ```

---

## 📊 第三步：拉取新增ETF数据（需用户执行）

### 新增的7只ETF

| 代码 | 名称 | 类型 |
|------|------|------|
| 512290 | 生物医药ETF | 核心池 |
| 513520 | 恒生科技ETF | 核心池 |
| 510580 | 500ETF | 核心池 |
| 512680 | 化工ETF | 观察池 |
| 515030 | 新能源车ETF | 观察池 |
| 512170 | 医疗ETF | 观察池 |
| 159605 | 人工智能ETF | 观察池 |

### 操作步骤

```bash
# 在项目根目录执行
python fetch_new_etfs.py
```

**预期输出**：
```
=== 拉取新增ETF历史数据 ===

共 7 只ETF需要更新

正在拉取 512290 (生物医药ETF)... ✓ 成功 (800 条记录)
正在拉取 513520 (恒生科技ETF)... ✓ 成功 (800 条记录)
...

=== 拉取完成 ===
成功：7 只
失败：0 只
```

**如果失败**：
- 检查网络连接
- 稍后重试
- 验证ETF代码有效性

---

## 🔍 第四步：验证配置（需用户执行）

```bash
python validate_config.py
```

**验证项目**：
1. ✅ config.yaml 风控参数
2. ✅ config.yaml 仓位参数
3. ✅ .env 文件存在性
4. ✅ ETF_LIST 配置
5. ✅ 数据库完整性
6. ✅ 新增ETF数据

**预期结果**：所有检查项显示 ✓

---

## 💾 第五步：备份数据库（强烈建议）

```bash
# Windows
copy data\trade_history.db data\trade_history.backup_20251222.db

# Linux/Mac
cp data/trade_history.db data/trade_history.backup_20251222.db
```

---

## 🚀 第六步：启动优化后的系统

### 方式一：启动Web服务

```bash
cd "d:\Quantitative Trading\ai-etf-trader"
python -m src.web_app
```

访问：http://127.0.0.1:5001

### 方式二：执行每日任务（测试）

```bash
# 仅测试，不实际交易
python -m src.daily_once --dry-run

# 实际执行
python -m src.daily_once
```

---

## 📊 第七步：监控首日执行

### 监控重点

1. **新增ETF信号**
   - 查看7只新增ETF是否产生交易信号
   - 记录信号类型（buy/sell/hold）

2. **风控触发**
   - 观察止损/止盈是否正常触发
   - 记录触发次数和效果

3. **仓位分布**
   - 确认单一标的权重 ≤ 25%
   - 验证动态仓位计算正确性

4. **AI决策**
   - 确认AI调用次数 ≤ 8次
   - 验证置信度过滤（≥70%）生效

### 监控工具

- **Web仪表盘**：http://127.0.0.1:5001
- **日志文件**：`logs/daily.log`
- **决策文件**：`decisions/` 目录

---

## ⚠️ 常见问题处理

### 问题1：.env 文件无法创建

**原因**：文件被 .gitignore 阻止

**解决**：
```bash
# 直接编辑创建
notepad .env  # Windows
nano .env     # Linux/Mac

# 然后复制 env_config.txt 的内容
```

### 问题2：新增ETF数据拉取失败

**原因**：网络问题或ETF代码无效

**解决**：
```bash
# 单独拉取失败的ETF
python -c "
from src.data_fetcher import fetch_etf_data, save_to_db
code = '512290'  # 替换为失败的代码
df = fetch_etf_data(code, days=800)
save_to_db(df, code)
"
```

### 问题3：配置验证失败

**原因**：参数值不匹配

**解决**：
1. 检查 `config.yaml` 格式（YAML语法）
2. 确认 `.env` 文件参数值正确
3. 重新运行 `validate_config.py`

### 问题4：Web服务启动失败

**原因**：端口被占用或模块导入错误

**解决**：
```bash
# 检查端口
netstat -ano | findstr :5001  # Windows
lsof -i :5001                 # Linux/Mac

# 更换端口
# 在 .env 中设置：FLASK_PORT=5002
```

---

## 📈 第八步：首日执行后复查

### 复查时间
2025-12-23（首日执行后）

### 复查内容

1. **交易执行情况**
   - [ ] 交易次数是否合理
   - [ ] 新增ETF是否有交易
   - [ ] 风控是否正常触发

2. **资产变化**
   - [ ] 总资产变化幅度
   - [ ] 持仓分布是否合理
   - [ ] 现金比例是否正常

3. **系统稳定性**
   - [ ] 是否有报错
   - [ ] 日志是否完整
   - [ ] API调用是否正常

4. **参数微调**
   - [ ] 是否需要调整止损/止盈阈值
   - [ ] 是否需要调整仓位参数
   - [ ] 是否需要调整AI置信度阈值

---

## 📞 技术支持

如遇到问题，请提供：
1. 错误信息截图
2. `logs/daily.log` 相关日志
3. `validate_config.py` 输出结果
4. 执行的具体步骤

---

**清单创建时间**：2025-12-22
**预计执行时间**：30分钟
**难度等级**：⭐⭐（中等）
**风险等级**：⭐（低，已备份）

