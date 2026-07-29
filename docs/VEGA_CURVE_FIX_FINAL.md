# 波动率曲线显示问题 - 最终修复报告

修复时间：2025-12-22
状态：✅ 已解决

---

## 问题根因

**Flask-Caching 缓存键冲突**

`/api/vega_risk` 接口使用了 `@cache.cached(timeout=10)`，但没有指定 `query_string=True` 参数。这导致：

1. 首次请求 `/api/vega_risk`（无参数）→ 返回汇总列表，缓存为 key="vega_risk"
2. 后续请求 `/api/vega_risk?code=510300&period=120` → 使用相同的缓存键，返回错误的汇总数据
3. 前端期望 `{"rows": [...]}` 格式，但收到列表 `[...]`
4. 前端代码 `const rows = (series && series.rows) ? series.rows : []` 得到空数组
5. Console 显示：`No vega data rows returned`

---

## 修复方案

### 1. 后端修复（src/web_app.py）

**修改前**：
```python
@app.route("/api/vega_risk")
@cache.cached(timeout=10)
def get_vega_risk_api():
```

**修改后**：
```python
@app.route("/api/vega_risk")
@cache.cached(timeout=10, query_string=True)  # 根据查询字符串区分缓存
def get_vega_risk_api():
```

**效果**：
- `/api/vega_risk` → 缓存键：`vega_risk?`
- `/api/vega_risk?code=510300&period=120` → 缓存键：`vega_risk?code=510300&period=120`
- 两个请求不再共享缓存

### 2. 前端优化（templates/index.html）

已在之前添加：
- 数据验证
- 错误处理
- Console 日志
- 图表重新初始化逻辑

---

## 验证结果

### API 测试
```bash
# 汇总接口
GET /api/vega_risk
返回：列表，14 个 ETF 的最新数据

# 时间序列接口
GET /api/vega_risk?code=510300&period=120
返回：{"rows": [...]}，120 条历史数据点
日期范围：2025-06-30 至 2025-12-22
```

### 前端测试
1. 打开浏览器 Console
2. 刷新页面（Ctrl + F5）
3. 应看到：`Vega chart rendered with 120 data points`
4. 波动率曲线正常显示

---

## 技术细节

### Flask-Caching 参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `timeout` | 缓存过期时间（秒） | 300 |
| `query_string` | 是否将查询参数包含在缓存键中 | False |
| `unless` | 条件函数，返回 True 时不缓存 | None |

**最佳实践**：
- 对于有查询参数的 API，务必使用 `query_string=True`
- 或使用 `key_prefix` 自定义缓存键

### 数据流程

```
前端 loadVega()
    ↓
1. 获取汇总：GET /api/vega_risk
    ← 返回：[{code: "510300", ...}, ...]
    ↓
2. 填充下拉框，选择第一个 code
    ↓
3. 获取时间序列：GET /api/vega_risk?code=510300&period=120
    ← 返回：{"rows": [{date: "2025-06-30", ...}, ...]}
    ↓
4. 提取 rows 数组
    ↓
5. 初始化 ECharts 并渲染
```

---

## 相关修复

### 已完成
1. ✅ 修复缓存键冲突（src/web_app.py）
2. ✅ 优化前端渲染逻辑（templates/index.html）
3. ✅ 清理非交易日数据（clean_non_trading_days.py）
4. ✅ 修复胜率计算（src/performance.py）
5. ✅ 移除"(待开盘)"错误逻辑（src/web_app.py）

### 清理的临时文件
- debug_vega_frontend.py
- test_cache_fix.py

---

## 用户操作指南

### 立即执行
1. **强制刷新浏览器**
   ```
   Ctrl + F5（Windows）
   Cmd + Shift + R（Mac）
   ```

2. **打开开发者工具**
   ```
   F12 → Console 标签
   ```

3. **验证输出**
   应看到：
   ```
   Vega chart rendered with 120 data points
   ```

4. **检查曲线**
   - "波动率风险（近似）"模块应显示完整曲线
   - 包含两条线：累计ΔV（蓝色）和 σ(%)（橙色）
   - 时间范围：2025-06-30 至 2025-12-22

### 如仍有问题

在 Console 执行：
```javascript
// 测试 API
fetch('/api/vega_risk?code=510300&period=120')
  .then(r => r.json())
  .then(d => {
    console.log('Response type:', typeof d);
    console.log('Has rows:', 'rows' in d);
    console.log('Rows length:', d.rows ? d.rows.length : 0);
  });
```

预期输出：
```
Response type: object
Has rows: true
Rows length: 120
```

---

## 经验总结

### 问题诊断流程
1. ✅ 检查后端 API 返回数据
2. ✅ 检查前端请求和响应
3. ✅ 检查数据格式匹配
4. ✅ 检查缓存机制
5. ✅ 检查浏览器 Console 日志

### 常见陷阱
1. **缓存键冲突**：Flask-Caching 默认不区分查询参数
2. **数据格式不一致**：后端返回列表，前端期望对象
3. **浏览器缓存**：修改后需强制刷新
4. **异步加载**：图表容器可能未就绪

---

## 验收清单

- [x] 后端缓存键修复
- [x] API 返回正确格式
- [x] 前端渲染逻辑优化
- [x] 非交易日数据清理
- [x] 测试脚本验证通过
- [ ] 用户浏览器验证通过

---

**修复完成**
请立即刷新浏览器验证！

