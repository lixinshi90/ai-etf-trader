# -*- coding: utf-8 -*-
"""
数据获取模块：使用 akshare 拉取ETF日线数据并保存到SQLite
"""
import os
import sqlite3
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
from src.indicators import add_kdj, add_macd

try:
    import akshare as ak
except Exception as e:
    ak = None

def _configure_ak_session():
    """为 akshare 配置浏览器头和重试机制，提高成功率。"""
    global ak
    if ak is None:
        return
    try:
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://quote.eastmoney.com/",
            "Connection": "keep-alive",
        }
        ak.headers = headers

        session = requests.Session()
        retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        ak.session = session
    except Exception:
        pass # 如果配置失败，则使用默认设置

# 模块加载时自动配置
_configure_ak_session()

_trade_cal_cache = None
_trade_cal_last_fetch = None

def is_trading_day(date_to_check: pd.Timestamp) -> bool:
    """检查给定日期是否为A股交易日。"""
    global _trade_cal_cache, _trade_cal_last_fetch
    if ak is None:
        # 如果akshare未安装，则退回到一个基于周一到周五的简单判断
        return date_to_check.weekday() < 5

    now = datetime.now()
    # 每日最多更新一次缓存
    if _trade_cal_cache is None or _trade_cal_last_fetch is None or (now - _trade_cal_last_fetch) > timedelta(days=1):
        try:
            trade_cal = ak.tool_trade_date_hist_sina()
            # trade_cal 返回的DataFrame中，'trade_date'列是datetime.date类型
            _trade_cal_cache = set(pd.to_datetime(trade_cal['trade_date']).dt.date)
            _trade_cal_last_fetch = now
        except Exception:
            # 如果API失败，则退回到一个基于周一到周五的简单判断
            return date_to_check.weekday() < 5

    return date_to_check.date() in _trade_cal_cache

def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _ensure_dir(p: str):
    os.makedirs(p, exist_ok=True)


def fetch_etf_data(etf_code: str, days: int = 700, end_date: Optional[str] = None) -> pd.DataFrame:
    """获取ETF日线数据（截至 end_date 的近 days 天），并计算 KDJ 和 MACD 指标。
    返回DataFrame，包含日期、开盘、收盘、最高、最低、成交量、成交额等。
    """
    if ak is None:
        raise RuntimeError("akshare 未安装，请先 pip install akshare")

    _end_dt = datetime.strptime(end_date, '%Y%m%d') if end_date else datetime.now()
    _start_dt = _end_dt - timedelta(days=days)

    df = None
    # 优先东方财富日线，失败则回退新浪
    try:
        if hasattr(ak, 'fund_etf_hist_em'):
            df = ak.fund_etf_hist_em(
                symbol=etf_code,
                period="daily",
                start_date=_start_dt.strftime('%Y%m%d'),
                end_date=_end_dt.strftime('%Y%m%d'),
                adjust="qfq"
            )
    except Exception:
        df = None

    # 回退：新浪（需要带交易所前缀 sh/sz；大多数版本不支持 period/start/end 参数）
    if (df is None or df.empty) and hasattr(ak, 'fund_etf_hist_sina'):
        try:
            def _pref(code: str) -> str:
                c = str(code)
                return ('sh' + c) if c.startswith(('5','6')) else ('sz' + c)
            df = ak.fund_etf_hist_sina(symbol=_pref(etf_code))
            # 仅保留时间窗内数据
            if df is not None and not df.empty and '日期' in df.columns:
                df['日期'] = pd.to_datetime(df['日期'], errors='coerce')
                df = df[(df['日期'] >= _start_dt) & (df['日期'] <= _end_dt)].copy()
        except Exception:
            df = None

    if df is None or df.empty:
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


def _db_path(default_name: str = 'etf_data.db') -> str:
    data_dir = os.path.join(_project_root(), 'data')
    _ensure_dir(data_dir)
    return os.path.join(data_dir, default_name)


def save_to_db(df: pd.DataFrame, etf_code: str, db_path: Optional[str] = None):
    """保存数据到SQLite，表名：etf_{etf_code}
    """
    if db_path is None:
        db_path = _db_path()

    _ensure_dir(os.path.dirname(db_path))

    conn = sqlite3.connect(db_path)
    try:
        # 确保日期列存在并为字符串以避免类型问题
        if '日期' in df.columns:
            df = df.copy()
            df['日期'] = pd.to_datetime(df['日期']).dt.strftime('%Y-%m-%d')
        df.to_sql(f'etf_{etf_code}', conn, if_exists='replace', index=False)
    finally:
        conn.close()

    print(f"已保存 {etf_code} 数据到数据库: {db_path}")


if __name__ == '__main__':
    etf_list = ["510050", "159915", "510300"]
    for code in etf_list:
        data = fetch_etf_data(code)
        save_to_db(data, code)

