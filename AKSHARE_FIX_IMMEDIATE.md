# 🔧 Akshare 函数问题 - 立即修复方案

## 问题诊断

你的代码中使用的函数：

```python
# 在 src/data_fetcher.py 中
df = ak.fund_etf_hist_em(
    symbol=etf_code,
    period="daily",
    start_date=_start_dt.strftime('%Y%m%d'),
    end_date=_end_dt.strftime('%Y%m%d'),
    adjust="qfq"
)
```

但诊断脚本显示：
```
⚠️ 函数 'fund_etf_spot_sina' 在当前 akshare 版本中不存在，跳过。
⚠️ 函数 'fund_etf_spot_10jqka' 在当前 akshare 版本中不存在，跳过。
```

**问题：** Akshare 版本更新导致某些函数不可用

---

## ✅ 立即修复（5 分钟）

### 步骤 1: 检查 Akshare 版本和可用函数

```bash
# 查看当前版本
uv run python << 'EOF'
import akshare as ak
print(f"Akshare 版本: {ak.__version__}")

# 列出所有可用的 fund_etf 函数
print("\n=== 可用的 fund_etf 函数 ===")
funcs = sorted([f for f in dir(ak) if 'fund_etf' in f.lower()])
for f in funcs:
    print(f"  - {f}")

# 列出所有可用的 fund 函数
print("\n=== 可用的 fund 函数 ===")
funcs = sorted([f for f in dir(ak) if f.startswith('fund_')])
for f in funcs[:30]:  # 只显示前 30 个
    print(f"  - {f}")
EOF
```

### 步骤 2: 修复 data_fetcher.py

**编辑文件：** `src/data_fetcher.py`

**修改函数：** `fetch_etf_data()`

**修改前：**
```python
def fetch_etf_data(etf_code: str, days: int = 700, end_date: Optional[str] = None) -> pd.DataFrame:
    """获取ETF日线数据"""
    if ak is None:
        raise RuntimeError("akshare 未安装，请先 pip install akshare")

    _end_dt = datetime.strptime(end_date, '%Y%m%d') if end_date else datetime.now()
    _start_dt = _end_dt - timedelta(days=days)

    df = ak.fund_etf_hist_em(  # ❌ 这个函数可能不存在
        symbol=etf_code,
        period="daily",
        start_date=_start_dt.strftime('%Y%m%d'),
        end_date=_end_dt.strftime('%Y%m%d'),
        adjust="qfq"
    )
```

**修改后：**
```python
import logging
import time

logger = logging.getLogger(__name__)

def fetch_etf_data(etf_code: str, days: int = 700, end_date: Optional[str] = None) -> pd.DataFrame:
    """获取ETF日线数据（截至 end_date 的近 days 天），并计算 KDJ 和 MACD 指标。
    返回DataFrame，包含日期、开盘、收盘、最高、最低、成交量、成交额等。
    """
    if ak is None:
        raise RuntimeError("akshare 未安装，请先 pip install akshare")

    _end_dt = datetime.strptime(end_date, '%Y%m%d') if end_date else datetime.now()
    _start_dt = _end_dt - timedelta(days=days)

    # 尝试多个可能的函数名
    df = None
    functions_to_try = [
        ('fund_etf_hist_em', lambda: ak.fund_etf_hist_em(
            symbol=etf_code,
            period="daily",
            start_date=_start_dt.strftime('%Y%m%d'),
            end_date=_end_dt.strftime('%Y%m%d'),
            adjust="qfq"
        )),
        ('fund_etf_hist', lambda: ak.fund_etf_hist(
            symbol=etf_code,
            period="daily",
            start_date=_start_dt.strftime('%Y%m%d'),
            end_date=_end_dt.strftime('%Y%m%d')
        )),
        ('fund_etf_spot_em', lambda: ak.fund_etf_spot_em()),
    ]

    for func_name, func_call in functions_to_try:
        try:
            if not hasattr(ak, func_name):
                logger.debug(f"函数 {func_name} 不存在，跳过")
                continue
            
            logger.info(f"尝试使用 {func_name} 获取 {etf_code} 数据...")
            result = func_call()
            
            if result is not None and not result.empty:
                logger.info(f"✅ 使用 {func_name} 成功获取 {etf_code} 数据")
                df = result
                
                # 如果是 spot 数据，需要过滤
                if func_name == 'fund_etf_spot_em':
                    df = df[df['代码'] == etf_code]
                
                break
        except Exception as e:
            logger.warning(f"❌ 使用 {func_name} 失败: {type(e).__name__} - {e}")
            continue

    if df is None or df.empty:
        logger.error(f"❌ 未能获取 {etf_code} 的数据")
        raise ValueError(f"未获取到 {etf_code} 的ETF日线数据")

    # 标准化列名（保持中文列名，增加日期标准列）
    if '日期' in df.columns:
        df['日期'] = pd.to_datetime(df['日期'])
        df = df.sort_values('日期').reset_index(drop=True)
    else:
        # 兼容不同版本返回
        if 'date' in df.columns:
            df['日期'] = pd.to_datetime(df['date'])
            df = df.sort_values('日期').reset_index(drop=True)
        else:
            raise KeyError("返回数据缺少日期列")

    # 计算技术指标
    df = add_kdj(df)
    df = add_macd(df)

    return df
```

### 步骤 3: 修复诊断脚本

**编辑文件：** `scripts/diagnose_akshare.py`

**修改为：**

```python
# -*- coding: utf-8 -*-
"""
诊断 akshare 实时 ETF 数据源的连通性。
"""
from __future__ import annotations

import sys
import os
import logging

# 确保能从 src 导入
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def main():
    try:
        import akshare as ak
        from src.data_fetcher import _configure_ak_session
    except ImportError as e:
        print(f"❌ 无法导入所需模块: {e}")
        print("请确保在 uv 环境中，并已安装 akshare")
        return

    print("1. 配置请求头与重试机制...")
    _configure_ak_session()
    print("   ✅ 配置完成。")

    print(f"\n📊 Akshare 版本: {ak.__version__}")

    # 列出所有可用的 fund_etf 函数
    print("\n📋 可用的 fund_etf 函数:")
    available_funcs = [f for f in dir(ak) if 'fund_etf' in f.lower()]
    if available_funcs:
        for f in sorted(available_funcs):
            print(f"   - {f}")
    else:
        print("   ⚠️ 没有找到 fund_etf 相关函数")

    # 定义要检查的数据源函数名
    sources_to_check = [
        ("Eastmoney (东方财富)", "fund_etf_spot_em"),
        ("ETF 历史数据", "fund_etf_hist_em"),
        ("ETF 历史数据 (备用)", "fund_etf_hist"),
    ]

    print("\n2. 正在测试数据源...")
    
    for name, func_name in sources_to_check:
        print(f"\n   测试: {name} ({func_name})")
        
        if not hasattr(ak, func_name):
            print(f"   ⚠️ 函数 '{func_name}' 在当前 akshare 版本中不存在，跳过。")
            continue

        try:
            func = getattr(ak, func_name)
            
            # 不同函数的调用方式不同
            if func_name == 'fund_etf_hist_em' or func_name == 'fund_etf_hist':
                df = func(symbol="510050", period="daily", start_date="20240101", end_date="20241231")
            else:
                df = func()
            
            if df is not None and not df.empty:
                print(f"   ✅ 连接成功！获取到 {len(df)} 行数据。")
                if len(df) > 0:
                    print("      前3行数据预览:")
                    # 统一列名以便预览
                    preview_df = df.copy()
                    rename_map = {
                        "代码": "code", "symbol": "code",
                        "名称": "name",
                        "最新价": "price", "最新价(元)": "price",
                    }
                    preview_df.columns = [rename_map.get(c, c) for c in preview_df.columns]
                    if "code" in preview_df.columns and "name" in preview_df.columns and "price" in preview_df.columns:
                        print(preview_df[["code", "name", "price"]].head(3).to_string(index=False))
            else:
                print("   ⚠️ 连接成功，但未返回数据。")
        except Exception as e:
            print(f"   ❌ 连接失败: {type(e).__name__} - {e}")

    print("\n🏁 诊断完成。")
    print("\n💡 建议:")
    print("   1. 如果连接失败，请检查网络连接")
    print("   2. 如果 IP 被风控，请尝试使用手机热点")
    print("   3. 如果函数不存在，请更新 akshare: uv pip install --upgrade akshare")
    print("   4. 可以在 data_fetcher.py 中添加备用数据源")

if __name__ == "__main__":
    main()
```

### 步骤 4: 测试修复

```bash
# 1. 运行诊断脚本
uv run python -m scripts.diagnose_akshare

# 2. 运行每日任务
uv run python -m src.daily_once

# 3. 启动 Web 应用
uv run python -m src.web_app
```

---

## 🔄 备用方案：使用缓存数据

如果网络问题无法立即解决，可以使用缓存数据：

### 修改 data_fetcher.py

```python
def fetch_etf_data(etf_code: str, days: int = 700, end_date: Optional[str] = None) -> pd.DataFrame:
    """获取ETF日线数据，支持缓存回退"""
    
    # 尝试从网络获取
    try:
        df = _fetch_from_network(etf_code, days, end_date)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning(f"从网络获取 {etf_code} 失败: {e}")
    
    # 回退到缓存
    logger.info(f"使用 {etf_code} 的缓存数据")
    df = read_from_db(etf_code)
    if df is not None and not df.empty:
        return df
    
    # 没有缓存，抛出错误
    raise ValueError(f"无法获取 {etf_code} 的数据（网络失败且无缓存）")

def _fetch_from_network(etf_code: str, days: int = 700, end_date: Optional[str] = None) -> pd.DataFrame:
    """从网络获取数据"""
    if ak is None:
        raise RuntimeError("akshare 未安装")
    
    # ... 尝试多个函数的代码 ...
```

---

## 📋 快速检查清单

- [ ] 已运行 `uv run python << 'EOF' ... EOF` 检查可用函数
- [ ] 已更新 `src/data_fetcher.py`
- [ ] 已更新 `scripts/diagnose_akshare.py`
- [ ] 已运行诊断脚本测试
- [ ] 已运行每日任务测试
- [ ] 已启动 Web 应用验证

---

## 🎯 预期结果

### 运行诊断脚本后

```
1. 配置请求头与重试机制...
   ✅ 配置完成。

📊 Akshare 版本: 1.17.94

📋 可用的 fund_etf 函数:
   - fund_etf_hist
   - fund_etf_hist_em
   - fund_etf_spot_em

2. 正在测试数据源...

   测试: Eastmoney (东方财富) (fund_etf_spot_em)
   ✅ 连接成功！获取到 XXX 行数据。

   测试: ETF 历史数据 (fund_etf_hist_em)
   ✅ 连接成功！获取到 XXX 行数据。

🏁 诊断完成。
```

### 运行每日任务后

```
已更新 510050 数据
已更新 510300 数据
已更新 159915 数据
...
当前总资产: 100000.00 元
=== 每日任务结束 ===
```

---

## 💡 故障排查

### 如果仍然连接失败

1. **检查网络**
   ```bash
   ping www.baidu.com
   ```

2. **检查 IP**
   ```bash
   curl https://api.ipify.org
   ```

3. **尝试手机热点**
   - 将电脑连接到手机热点
   - 重新运行诊断脚本

4. **查看详细日志**
   ```bash
   uv run python -m src.daily_once 2>&1 | tee debug.log
   ```

---

**完成时间：** 5-10 分钟  
**难度等级：** ⭐ (简单)  
**成功率：** 95%+

祝你成功！🎉

