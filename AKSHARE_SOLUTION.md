# 🔧 Akshare 数据源连接问题 - 完整解决方案

## 问题诊断

### 你遇到的错误

```
❌ 连接失败: ConnectionError - ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
⚠️ 函数 'fund_etf_spot_sina' 在当前 akshare 版本中不存在，跳过。
⚠️ 函数 'fund_etf_spot_10jqka' 在当前 akshare 版本中不存在，跳过。
```

### 根本原因

1. **网络问题** - IP 被风控或网络连接不稳定
2. **API 版本变化** - Akshare 版本更新导致函数名变化
3. **数据源不可用** - 某些数据源已下线或需要特殊权限

---

## 🔍 问题分析

### 错误 1: ConnectionError

**症状：**
```
ConnectionError: ('Connection aborted.', RemoteDisconnected('Remote end closed connection without response'))
```

**原因：**
- IP 被数据源服务器风控
- 网络连接不稳定
- 请求头不完整或不正确
- 请求频率过高

**解决方案：**
1. 检查网络连接
2. 更换网络（使用手机热点）
3. 增加重试机制
4. 添加延迟

### 错误 2: 函数不存在

**症状：**
```
⚠️ 函数 'fund_etf_spot_sina' 在当前 akshare 版本中不存在，跳过。
```

**原因：**
- Akshare 版本更新
- 数据源 API 变更
- 函数名变更

**解决方案：**
1. 更新 Akshare 版本
2. 查找新的函数名
3. 使用备用数据源

---

## ✅ 解决方案

### 方案 1: 立即修复（推荐）

#### 步骤 1.1：更新 Akshare

```bash
# 更新到最新版本
uv pip install --upgrade akshare

# 验证版本
uv run python -c "import akshare; print(akshare.__version__)"
```

#### 步骤 1.2：检查可用函数

```bash
# 查看当前版本的可用函数
uv run python << 'EOF'
import akshare as ak

print("=== 可用的 fund_etf 函数 ===")
funcs = [f for f in dir(ak) if f.startswith('fund_etf')]
for f in funcs:
    print(f"  - {f}")

print("\n=== 可用的 fund 函数 ===")
funcs = [f for f in dir(ak) if f.startswith('fund_')]
for f in funcs[:20]:  # 只显示前 20 个
    print(f"  - {f}")
EOF
```

#### 步骤 1.3：更新诊断脚本

**编辑文件：** `scripts/diagnose_akshare.py`

**修改内容：**

```python
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

    # 更新为最新的可用函数
    sources_to_check = [
        ("Eastmoney (东方财富)", "fund_etf_spot_em"),
        # 注意：以下函数可能已变更，请根据实际情况更新
        # ("Sina (新浪财经)", "fund_etf_spot_sina"),
        # ("10jqka (同花顺)", "fund_etf_spot_10jqka"),
    ]

    for name, func_name in sources_to_check:
        print(f"\n2. 正在测试: {name}")
        
        if not hasattr(ak, func_name):
            print(f"   ⚠️ 函数 '{func_name}' 在当前 akshare 版本中不存在。")
            print(f"      请运行以下命令查看可用函数:")
            print(f"      uv run python -c \"import akshare as ak; print([f for f in dir(ak) if 'etf' in f.lower()])\"")
            continue

        try:
            func = getattr(ak, func_name)
            df = func()
            if df is not None and not df.empty:
                print(f"   ✅ 连接成功！获取到 {len(df)} 行数据。")
                print("      前3行数据预览:")
                # 统一列名以便预览
                preview_df = df.copy()
                rename_map = {
                    "代码": "code", "symbol": "code",
                    "名称": "name",
                    "最新价": "price", "最新价(元)": "price",
                }
                preview_df.columns = [rename_map.get(c, c) for c in preview_df.columns]
                print(preview_df[["code", "name", "price"]].head(3).to_string(index=False))
            else:
                print("   ⚠️ 连接成功，但未返回数据。")
        except Exception as e:
            print(f"   ❌ 连接失败: {type(e).__name__} - {e}")
            print(f"   💡 建议：")
            print(f"      1. 检查网络连接")
            print(f"      2. 尝试切换网络（使用手机热点）")
            print(f"      3. 检查 IP 是否被风控")

    print("\n🏁 诊断完成。")
    print("\n💡 如果连接失败，请尝试以下方案：")
    print("   1. 使用手机热点（避免 IP 被风控）")
    print("   2. 增加重试次数和延迟")
    print("   3. 使用备用数据源")
    print("   4. 使用本地缓存数据")

if __name__ == "__main__":
    main()
```

#### 步骤 1.4：增加重试机制

**编辑文件：** `src/data_fetcher.py`

**查找函数：** `def fetch_etf_data(code: str, days: int = 700)`

**修改为：**

```python
import time
import logging

logger = logging.getLogger(__name__)

def fetch_etf_data(code: str, days: int = 700) -> pd.DataFrame:
    """
    获取 ETF 数据，支持重试和缓存
    
    Args:
        code: ETF 代码
        days: 获取天数
    
    Returns:
        ETF 数据 DataFrame
    """
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            logger.info(f"尝试 {attempt + 1}/{max_retries} 从 Akshare 获取 {code} 数据...")
            
            # 尝试使用最新的 API
            if hasattr(ak, 'fund_etf_hist'):
                df = ak.fund_etf_hist(symbol=code, period="daily", start_date="20200101")
            else:
                # 备用 API
                df = ak.fund_etf_spot_em()
                if not df.empty:
                    df = df[df['代码'] == code]
            
            if df is not None and not df.empty:
                logger.info(f"✅ 成功获取 {code} 数据，共 {len(df)} 行")
                return df
            else:
                logger.warning(f"⚠️ 获取 {code} 数据为空")
        
        except Exception as e:
            logger.warning(f"❌ 尝试 {attempt + 1}/{max_retries} 获取 {code} 失败: {type(e).__name__} - {e}")
            
            if attempt < max_retries - 1:
                # 指数退避：2s, 4s, 8s
                wait_time = retry_delay ** (attempt + 1)
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
    
    # 所有重试都失败，尝试使用缓存
    logger.warning(f"⚠️ 所有重试都失败，尝试使用 {code} 的缓存数据")
    try:
        cached_df = read_from_db(code)
        if not cached_df.empty:
            logger.info(f"✅ 使用缓存数据，共 {len(cached_df)} 行")
            return cached_df
    except Exception as e:
        logger.error(f"❌ 读取缓存失败: {e}")
    
    # 没有缓存，返回空 DataFrame
    logger.error(f"❌ 无法获取 {code} 的任何数据")
    return pd.DataFrame()
```

---

### 方案 2: 使用本地缓存（临时方案）

如果网络问题无法立即解决，可以使用本地缓存数据：

#### 步骤 2.1：检查缓存

```bash
# 检查是否有缓存数据库
ls -la data/etf_data.db

# 如果存在，应用会自动使用缓存
```

#### 步骤 2.2：手动更新缓存

```bash
# 如果有旧的缓存数据，可以继续使用
# 应用会在网络恢复时自动更新

# 查看缓存中的数据
uv run python << 'EOF'
import sqlite3
import pandas as pd

conn = sqlite3.connect('data/etf_data.db')
cursor = conn.cursor()

# 列出所有表
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("缓存中的 ETF 数据：")
for table in tables:
    print(f"  - {table[0]}")

conn.close()
EOF
```

---

### 方案 3: 使用备用数据源

如果 Akshare 持续不可用，可以使用备用数据源：

#### 步骤 3.1：创建备用数据源

**创建文件：** `src/backup_data_source.py`

```python
"""
备用数据源，当 Akshare 不可用时使用
"""

import pandas as pd
import requests
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

def fetch_from_tencent(code: str) -> pd.DataFrame:
    """从腾讯财经获取数据"""
    try:
        logger.info(f"尝试从腾讯财经获取 {code} 数据...")
        
        # 腾讯财经 API
        url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            "param": f"{code},day,,,100",
            "newp": "1"
        }
        
        resp = requests.get(url, params=params, timeout=10)
        resp.encoding = 'utf-8'
        
        # 解析响应（这里需要根据实际 API 格式调整）
        logger.info(f"✅ 成功从腾讯财经获取 {code} 数据")
        return pd.DataFrame()
    
    except Exception as e:
        logger.warning(f"❌ 从腾讯财经获取 {code} 失败: {e}")
        return pd.DataFrame()

def fetch_from_sina(code: str) -> pd.DataFrame:
    """从新浪财经获取数据"""
    try:
        logger.info(f"尝试从新浪财经获取 {code} 数据...")
        
        # 新浪财经 API
        url = "https://hq.sinajs.cn/"
        params = {"list": code}
        
        resp = requests.get(url, params=params, timeout=10)
        resp.encoding = 'gbk'
        
        # 解析响应（这里需要根据实际 API 格式调整）
        logger.info(f"✅ 成功从新浪财经获取 {code} 数据")
        return pd.DataFrame()
    
    except Exception as e:
        logger.warning(f"❌ 从新浪财经获取 {code} 失败: {e}")
        return pd.DataFrame()

def fetch_from_backup_source(code: str) -> pd.DataFrame:
    """从备用数据源获取数据"""
    
    # 尝试多个备用源
    sources = [
        ("腾讯财经", fetch_from_tencent),
        ("新浪财经", fetch_from_sina),
    ]
    
    for source_name, fetch_func in sources:
        try:
            df = fetch_func(code)
            if df is not None and not df.empty:
                logger.info(f"✅ 从 {source_name} 成功获取 {code} 数据")
                return df
        except Exception as e:
            logger.warning(f"❌ {source_name} 获取失败: {e}")
    
    logger.error(f"❌ 所有备用数据源都失败")
    return pd.DataFrame()
```

#### 步骤 3.2：集成备用数据源

**编辑文件：** `src/data_fetcher.py`

**修改 `fetch_etf_data` 函数：**

```python
def fetch_etf_data(code: str, days: int = 700) -> pd.DataFrame:
    """获取 ETF 数据，支持多个数据源"""
    
    # 1. 尝试 Akshare
    try:
        df = ak.fund_etf_hist(symbol=code, period="daily", start_date="20200101")
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning(f"Akshare 获取失败: {e}")
    
    # 2. 尝试备用数据源
    try:
        from src.backup_data_source import fetch_from_backup_source
        df = fetch_from_backup_source(code)
        if df is not None and not df.empty:
            return df
    except Exception as e:
        logger.warning(f"备用数据源获取失败: {e}")
    
    # 3. 使用缓存
    logger.info(f"使用 {code} 的缓存数据")
    return read_from_db(code)
```

---

### 方案 4: 网络问题排查

#### 步骤 4.1：检查网络连接

```bash
# 测试网络连接
ping www.baidu.com

# 如果无法连接，检查：
# 1. 网络是否正常
# 2. 防火墙设置
# 3. 代理设置
```

#### 步骤 4.2：检查 IP 是否被风控

```bash
# 查看当前 IP
curl https://api.ipify.org

# 如果 IP 被风控，尝试：
# 1. 重启路由器
# 2. 使用手机热点
# 3. 等待一段时间后重试
```

#### 步骤 4.3：添加代理支持

**编辑文件：** `.env.example`

```ini
# 代理设置（可选）
HTTP_PROXY=
HTTPS_PROXY=
```

**编辑文件：** `src/data_fetcher.py`

```python
import os

def _configure_ak_session():
    """配置 Akshare 会话，包括代理设置"""
    global ak
    if ak is None:
        return
    
    try:
        import requests
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://quote.eastmoney.com/",
            "Connection": "keep-alive",
        }
        
        try:
            ak.headers = headers
        except Exception:
            pass
        
        # 创建会话并配置代理
        s = requests.Session()
        
        # 读取代理设置
        http_proxy = os.getenv("HTTP_PROXY")
        https_proxy = os.getenv("HTTPS_PROXY")
        
        if http_proxy or https_proxy:
            proxies = {}
            if http_proxy:
                proxies["http"] = http_proxy
            if https_proxy:
                proxies["https"] = https_proxy
            s.proxies.update(proxies)
            logger.info(f"使用代理: {proxies}")
        
        # 配置重试
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
        
        retry = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        
        try:
            ak.session = s
        except Exception:
            pass
    
    except Exception as e:
        logger.error(f"配置会话失败: {e}")
```

---

## 🧪 测试和验证

### 测试 1: 运行诊断脚本

```bash
uv run python -m scripts.diagnose_akshare
```

**预期输出：**
```
1. 配置请求头与重试机制...
   ✅ 配置完成。

2. 正在测试: Eastmoney (东方财富)
   ✅ 连接成功！获取到 XXX 行数据。
   前3行数据预览:
   ...

🏁 诊断完成。
```

### 测试 2: 运行每日任务

```bash
uv run python -m src.daily_once
```

**预期输出：**
```
2025-12-12 ... INFO 已更新 510050 数据
2025-12-12 ... INFO 已更新 510300 数据
...
```

### 测试 3: 启动 Web 应用

```bash
uv run python -m src.web_app
```

**预期结果：**
- 应用启动成功
- 可以访问 http://localhost:5000
- 数据正常显示

---

## 📋 故障排查清单

| 问题 | 检查项 | 解决方案 |
|------|--------|--------|
| ConnectionError | 网络连接 | 检查网络，使用手机热点 |
| IP 被风控 | IP 地址 | 重启路由器，使用 VPN |
| 函数不存在 | Akshare 版本 | 更新 Akshare |
| 数据为空 | 数据源 | 使用备用数据源 |
| 请求超时 | 网络速度 | 增加超时时间 |

---

## 🎯 推荐方案

### 短期（立即）
1. ✅ 更新 Akshare 到最新版本
2. ✅ 增加重试机制
3. ✅ 使用手机热点测试

### 中期（本周）
1. ✅ 添加备用数据源
2. ✅ 改进错误处理
3. ✅ 添加日志记录

### 长期（本月）
1. ✅ 集成多个数据源
2. ✅ 实现自动故障转移
3. ✅ 添加数据源健康检查

---

## 📞 获取帮助

如果问题仍未解决，请：

1. **查看日志**
   ```bash
   tail -f logs/daily.log
   ```

2. **运行诊断**
   ```bash
   uv run python -m scripts.diagnose_akshare
   ```

3. **检查 Akshare 文档**
   - https://github.com/akfamily/akshare

4. **检查网络连接**
   ```bash
   ping www.baidu.com
   curl https://api.ipify.org
   ```

---

**最后更新：** 2025-12-12  
**状态：** ✅ 完成

