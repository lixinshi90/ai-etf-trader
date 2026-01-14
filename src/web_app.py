# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import yaml
from typing import List, Dict, Any
from datetime import datetime, time
import glob
import re

import pandas as pd
import numpy as np
from flask import Flask, render_template, jsonify, request
from flask_caching import Cache
from dotenv import load_dotenv

from src.performance import calculate_performance_from_data
from src.vegas import compute_vega_proxy_series, latest_summary as get_vega_summary
from src.data_fetcher import fetch_etf_data, save_to_db
from src.options import get_option_chain_with_iv_greeks, fetch_etf_latest_price
from src.validation import (
    validate_financial_value, 
    validate_ohlcv_data, 
    sanitize_api_response,
    validate_percentage,
    validate_positive_number
)

# --- Akshare Lazy Import ---
try:
    import akshare as ak
except ImportError:
    ak = None

# --- Project Paths & Config Loading ---
def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

CONFIG_PATH = os.path.join(_project_root(), "config.yaml")

# Load .env first to allow environment overrides
try:
    load_dotenv(override=True)
except Exception:
    pass

# Load configuration from YAML file (graceful fallback)
try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f) or {}
except FileNotFoundError:
    config = {}
# Defaults
config.setdefault('strategy', {}).setdefault('initial_capital', float(os.getenv('INITIAL_CAPITAL', '100000')))
config.setdefault('flask', {})

# --- File Paths from Config ---
COMPLIANT_TRADES_CSV = os.path.join(_project_root(), "out", "resimulated_trades_fully_compliant.csv")
COMPLIANT_EQUITY_CSV = os.path.join(_project_root(), "out", "resimulated_daily_equity.csv")
COMPLIANT_PERF_CSV = os.path.join(_project_root(), "out", "resimulated_daily_performance.csv")
ETF_DB_PATH = os.path.join(_project_root(), "data", "etf_data.db")
QLIB_FACTORS_DIR = os.path.join(_project_root(), "data", "qlib_factors")
DECISIONS_DIR = os.path.join(_project_root(), "decisions")
QLIB_DIR = os.path.join(_project_root(), "data", "qlib", "cn_etf")
LOGS_DIR = os.path.join(_project_root(), "logs")

# --- Flask App Initialization ---
app = Flask(
    __name__,
    static_folder=os.path.join(_project_root(), "static"),
    template_folder=os.path.join(_project_root(), "templates"),
)
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0

# --- Error Handlers (JSON for API routes) ---
@app.errorhandler(404)
def handle_404(e):
    if request.path.startswith('/api/'):
        return jsonify({"ok": False, "msg": "Not Found", "path": request.path}), 404
    return e

@app.errorhandler(405)
def handle_405(e):
    if request.path.startswith('/api/'):
        return jsonify({"ok": False, "msg": "Method Not Allowed", "path": request.path}), 405
    return e

@app.errorhandler(500)
def handle_500(e):
    if request.path.startswith('/api/'):
        return jsonify({"ok": False, "msg": "Internal Server Error", "path": request.path}), 500
    return e

# --- Cache Configuration ---
CACHE_DIR = os.path.join(_project_root(), ".cache")
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

cache_config = {
    "CACHE_TYPE": "FileSystemCache",
    "CACHE_DIR": CACHE_DIR,
    "CACHE_DEFAULT_TIMEOUT": 300,  # Cache timeout in seconds (5 minutes)
}
app.config.from_mapping(cache_config)
cache = Cache(app)

@app.after_request
def add_no_cache_headers(resp):
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp

# --- Helper Functions ---
import sqlite3

def _read_latest_price(code: str) -> float | None:
    if not os.path.exists(ETF_DB_PATH):
        return None
    conn = sqlite3.connect(ETF_DB_PATH)
    try:
        try:
            df = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY 日期 DESC LIMIT 1", conn)
        except Exception:
            df = pd.read_sql_query(f"SELECT * FROM etf_{code} ORDER BY date DESC LIMIT 1", conn)
        if df.empty:
            return None
        for col in ("收盘", "close"):
            if col in df.columns:
                price = df.iloc[0][col]
                # Validate the price to prevent inflated values
                validated_price = validate_financial_value(price, 'price', code)
                return validated_price
        return None
    except Exception:
        return None
    finally:
        conn.close()

def _default_codes() -> List[str]:
    return ["510300","159915","159928","513100"]

def _infer_etf_codes(max_n: int = 50) -> List[str]:
    # 1) ENV
    etf_list_str = os.getenv("ETF_LIST", "")
    codes = [c.strip() for c in etf_list_str.split(',') if c.strip()]
    if codes:
        return codes[:max_n]
    # 2) From qlib_factors filenames
    try:
        if os.path.exists(QLIB_FACTORS_DIR):
            files = [f for f in os.listdir(QLIB_FACTORS_DIR) if f.endswith('.csv')]
            got = [os.path.splitext(f)[0] for f in files]
            if got:
                return got[:max_n]
    except Exception:
        pass
    # 3) From SQLite table names
    try:
        if os.path.exists(ETF_DB_PATH):
            conn = sqlite3.connect(ETF_DB_PATH)
            try:
                tdf = pd.read_sql_query("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'etf_%'", conn)
                if not tdf.empty:
                    got = [str(n).replace('etf_', '', 1) for n in tdf['name'].tolist()]
                    got = [g for g in got if g]
                    if got:
                        return got[:max_n]
            finally:
                conn.close()
    except Exception:
        pass
    # Final fallback to a small common ETF set
    return _default_codes()

def is_market_open() -> bool:
    now = datetime.now().time()
    market_open = time(9, 30)
    market_close = time(15, 0)
    return market_open <= now <= market_close

# Strategy snapshot for factor table
def _strategy_snapshot() -> Dict[str, Any]:
    # Prefer environment overrides
    mode = os.getenv('STRATEGY_MODE')
    breakout_n = os.getenv('BREAKOUT_N')
    rsi_n = os.getenv('RSI_N')
    rsi_low = os.getenv('RSI_LOW')
    rsi_high = os.getenv('RSI_HIGH')

    # Fallback to config.yaml (possible lowercase keys)
    st = config.get('strategy', {}) if isinstance(config, dict) else {}
    def _get(k_env, k_cfg, default=None, cast=float):
        val = k_env if k_env is not None else st.get(k_cfg)
        if val is None:
            return default
        try:
            return cast(val)
        except Exception:
            return val

    out = {
        'mode': (mode or st.get('mode') or 'AGGRESSIVE'),
        'breakout_n': _get(breakout_n, 'breakout_n', 20, int),
        'rsi_n': _get(rsi_n, 'rsi_n', 2, int),
        'rsi_low': _get(rsi_low, 'rsi_low', 10, int),
        'rsi_high': _get(rsi_high, 'rsi_high', 95, int),
    }
    return out

# --- API Endpoints ---
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/health")
def health_check():
    return "ok"

@app.route("/api/trades")
@cache.cached(timeout=60)
def get_trades():
    import sqlite3 as _sql
    import json
    # Prefer DB trades (robust to schema differences and NaN strings)
    try:
        db_path = os.path.join(_project_root(), "data", "trade_history.db")
        if os.path.exists(db_path):
            conn = _sql.connect(db_path)
            try:
                # Return all trades by default; optionally limit via ?limit=...
                limit = request.args.get('limit', type=int)
                if limit is not None and limit > 0:
                    df = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date) DESC LIMIT ?", conn, params=(limit,))
                else:
                    df = pd.read_sql_query("SELECT * FROM trades ORDER BY datetime(date) DESC", conn)
            finally:
                conn.close()
            if df is not None and not df.empty:
                # Step 1: Drop 'id' column if exists
                if 'id' in df.columns:
                    df = df.drop(columns=['id'])
                # Step 2: Replace string NaNs
                df = df.replace(to_replace=["NaN", "nan", "None", "null", "NaT", ""], value=None)
                # Step 3: Fill all NaN with appropriate defaults
                df = df.fillna({
                    'prev_cash': 0,
                    'trade_pct': 0,
                    'constraint_triggered': 0,
                    'trade_cost': 0,
                })
                # Step 4: Convert any remaining NaN to None
                df = df.where(pd.notna(df), None)
                # Step 5: Convert to records and validate each trade
                recs = df.to_dict("records")
                validated_recs = []
                
                for trade in recs:
                    validated_trade = trade.copy()
                    
                    # Validate key financial fields
                    for field in ['price', 'value', 'capital_after', 'prev_cash']:
                        if field in trade:
                            validated_value = validate_financial_value(trade[field], 'price', f"trade_{field}")
                            if validated_value is not None:
                                validated_trade[field] = validated_value
                            else:
                                print(f"Warning: Invalid {field} value in trade: {trade[field]}")
                    
                    # Validate quantity
                    if 'quantity' in trade:
                        validated_qty = validate_positive_number(trade['quantity'], 'quantity')
                        if validated_qty is not None:
                            validated_trade['quantity'] = validated_qty
                        else:
                            print(f"Warning: Invalid quantity in trade: {trade['quantity']}")
                    
                    # Validate percentage fields
                    for field in ['trade_pct']:
                        if field in trade:
                            validated_pct = validate_percentage(trade[field], field)
                            if validated_pct is not None:
                                validated_trade[field] = validated_pct
                            else:
                                print(f"Warning: Invalid percentage {field} in trade: {trade[field]}")
                    
                    validated_recs.append(validated_trade)
                
                # Sanitize the response before returning
                sanitized_recs = sanitize_api_response(validated_recs)
                return jsonify(sanitized_recs)
    except Exception as e:
        print(f"Error in /api/trades DB path: {e}")
        import traceback
        traceback.print_exc()
        # Return empty array instead of failing
        return jsonify([])
    # Fallback to CSV with strict NA parsing
    try:
        if not os.path.exists(COMPLIANT_TRADES_CSV):
            return jsonify([])
        trades = pd.read_csv(COMPLIANT_TRADES_CSV, na_values=["NaN", "nan", "None", "null", "NaT", ""], keep_default_na=True)
        trades = trades.sort_values("date", ascending=False).head(200)
        trades = trades.where(pd.notna(trades), None)
        if 'id' in trades.columns:
            trades = trades.drop(columns=['id'])
        recs = trades.to_dict("records")
        safe_json = json.loads(json.dumps(recs, allow_nan=False, default=str))
        return jsonify(safe_json)
    except Exception as e:
        print(f"Error in /api/trades CSV fallback: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([])

@app.route("/api/backtest")
@cache.cached(timeout=60, query_string=True)
def api_backtest():
    """Run an in-memory backtest (rule-only) for a given date range and ETF codes.

    Query params:
      - start: YYYY-MM-DD
      - end: YYYY-MM-DD
      - codes: comma-separated, e.g. 510300,159915,510050

    Returns:
      { equity:{dates,values}, kpis:{...}, trades:[...], daily_trades:[...] }
    """
    try:
        start = (request.args.get('start') or '').strip()
        end = (request.args.get('end') or '').strip()
        codes_str = (request.args.get('codes') or '').strip()
        if not start or not end:
            return jsonify({"ok": False, "msg": "missing start/end"}), 400
        if not codes_str:
            return jsonify({"ok": False, "msg": "missing codes"}), 400

        codes = [c.strip() for c in codes_str.split(',') if c.strip()]
        if not codes:
            return jsonify({"ok": False, "msg": "no valid codes"}), 400

        from src.backtest import run_backtest
        res = run_backtest(codes, start, end)
        return jsonify({"ok": True, **res})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500


@app.route("/api/performance")
@cache.cached(timeout=60)
def get_performance():
    """Performance series for the dashboard with data validation.
    Plan B: Prefer DB daily_equity (written by daily task), fallback to CSV.
    """
    initial_capital = validate_positive_number(
        config['strategy'].get('initial_capital'), 
        'initial_capital'
    ) or 100000.0  # Default to 100,000 if invalid

    # 1) Prefer DB daily_equity from data/trade_history.db
    try:
        db_path = os.path.join(_project_root(), "data", "trade_history.db")
        if os.path.exists(db_path):
            import sqlite3 as _sql
            conn = _sql.connect(db_path)
            try:
                df_db = pd.read_sql_query("SELECT date, equity FROM daily_equity ORDER BY date ASC", conn)
            finally:
                conn.close()
                
            if df_db is not None and not df_db.empty:
                # Convert and validate data
                df_db['date'] = pd.to_datetime(df_db['date'], errors='coerce')
                df_db['equity'] = pd.to_numeric(df_db['equity'], errors='coerce')
                
                # Remove rows with invalid dates or equity values
                df_db = df_db.dropna(subset=['date', 'equity'])
                
                # Ensure equity values are reasonable
                df_db = df_db[
                    (df_db['equity'] > 0) & 
                    (df_db['equity'] < initial_capital * 1000)  # Max 1000x initial capital
                ]
                
                if not df_db.empty:
                    # Optional start-date filter (perf_start.json or PERF_START_DATE)
                    try:
                        start_date = os.getenv('PERF_START_DATE')
                        if not start_date:
                            fp = os.path.join(_project_root(), 'perf_start.json')
                            if os.path.exists(fp):
                                import json as _json
                                with open(fp, 'r', encoding='utf-8') as _f:
                                    start_date = (_json.load(_f) or {}).get('start_date')
                        if start_date:
                            start_date = pd.to_datetime(start_date)
                            if pd.notna(start_date):
                                df_db = df_db[df_db['date'] >= start_date]
                    except Exception as e:
                        print(f"Error applying start date filter: {e}")
                    
                    # Sort by date to ensure proper time series
                    df_db = df_db.sort_values('date')
                    
                    # Detect and remove outliers using IQR (optional)
                    # 注意：回撤/大波动本身也是绩效的一部分。默认关闭该过滤，避免误删真实交易日（例如 12/11 低谷）。
                    iqr_filter = os.getenv('PERF_IQR_FILTER', 'false').lower() == 'true'
                    if iqr_filter:
                        q1 = df_db['equity'].quantile(0.25)
                        q3 = df_db['equity'].quantile(0.75)
                        iqr = q3 - q1
                        lower_bound = q1 - 1.5 * iqr
                        upper_bound = q3 + 1.5 * iqr
                        df_db = df_db[
                            (df_db['equity'] >= lower_bound) &
                            (df_db['equity'] <= upper_bound)
                        ]

                    # --- Optional: Resample to calendar days, forward-filling weekends/holidays ---
                    resample = request.args.get('resample_to_calendar_days', 'false').lower() == 'true'
                    if resample and not df_db.empty:
                        try:
                            df_db = df_db.set_index('date')
                            # Create a full date range from the first date to the last
                            full_date_range = pd.date_range(start=df_db.index.min(), end=df_db.index.max(), freq='D')
                            # Reindex the dataframe to the full date range and forward-fill missing values
                            df_db = df_db.reindex(full_date_range).ffill()
                            df_db.reset_index(inplace=True)
                            df_db.rename(columns={'index': 'date'}, inplace=True)
                            app.logger.info("Resampled performance data to calendar days.")
                        except Exception as e:
                            app.logger.error(f"Failed to resample performance data: {e}")
                            # On failure, fall back to non-resampled data
                    # --- End Resample ---

                    # Format output
                    out_dates = df_db['date'].dt.strftime('%Y-%m-%d').tolist()
                    out_vals = df_db['equity'].round(2).tolist()

                    return jsonify({
                        "dates": out_dates,
                        "values": out_vals,
                        "initial_capital": initial_capital
                    })
    except Exception:
        pass

    # 2) Fallback to compliant CSV (resimulated)
    try:
        if not os.path.exists(COMPLIANT_EQUITY_CSV):
            today = pd.Timestamp.today().strftime('%Y-%m-%d')
            return jsonify({
                "dates": [today], 
                "values": [initial_capital],
                "initial_capital": initial_capital,
                "source": "fallback_today"
            })

        # Read and validate the CSV data
        equity_df = pd.read_csv(COMPLIANT_EQUITY_CSV)
        if equity_df.empty:
            today = pd.Timestamp.today().strftime('%Y-%m-%d')
            return jsonify({
                "dates": [today], 
                "values": [initial_capital],
                "initial_capital": initial_capital,
                "source": "fallback_empty_csv"
            })

        # Column compatibility: support 'equity' or 'total_assets'
        val_col = 'equity' if 'equity' in equity_df.columns else 'total_assets'
        
        # Extract and validate dates and values
        equity_df['date'] = pd.to_datetime(equity_df.get("date", equity_df.iloc[:,0]), errors='coerce')
        equity_df['value'] = pd.to_numeric(equity_df[val_col], errors='coerce')
        
        # Remove rows with invalid dates or values
        valid_data = equity_df.dropna(subset=['date', 'value'])
        
        # Filter out extreme values
        valid_data = valid_data[
            (valid_data['value'] > 0) & 
            (valid_data['value'] < initial_capital * 1000)  # Max 1000x initial capital
        ]
        
        if valid_data.empty:
            today = pd.Timestamp.today().strftime('%Y-%m-%d')
            return jsonify({
                "dates": [today], 
                "values": [initial_capital],
                "initial_capital": initial_capital,
                "source": "no_valid_data"
            })
        
        # Sort by date and remove duplicates
        valid_data = valid_data.sort_values('date').drop_duplicates('date')
        
        # Format output
        out_dates = valid_data['date'].dt.strftime('%Y-%m-%d').tolist()
        out_vals = valid_data['value'].tolist()
        
        return jsonify({
            "dates": out_dates, 
            "values": out_vals,
            "initial_capital": initial_capital,
            "source": "compliant_csv"
        })
        
    except Exception as e:
        print(f"Error in performance fallback: {e}")
        
    # 3) Ultimate fallback: today = initial_capital
    today = pd.Timestamp.today().strftime('%Y-%m-%d')
    return jsonify({
        "dates": [today], 
        "values": [initial_capital],
        "initial_capital": initial_capital,
        "source": "final_fallback"
    })

@app.route("/api/metrics")
@cache.cached(timeout=60)
def get_metrics():
    """Calculate KPIs from the authoritative DB source (trade_history.db)."""
    trades_df = pd.DataFrame()
    daily_perf_df = pd.DataFrame()

    try:
        db_path = os.path.join(_project_root(), "data", "trade_history.db")
        if not os.path.exists(db_path):
            raise FileNotFoundError("trade_history.db not found")

        import sqlite3 as _sql
        conn = _sql.connect(db_path)
        try:
            trades_df = pd.read_sql_query("SELECT date, etf_code, action, price, quantity, value, capital_after, reasoning FROM trades ORDER BY datetime(date)", conn)
            daily_perf_df = pd.read_sql_query("SELECT date, equity FROM daily_equity ORDER BY date", conn)
            if not daily_perf_df.empty:
                daily_perf_df = daily_perf_df.rename(columns={"equity":"total_assets"})
        finally:
            conn.close()

    except Exception as e:
        app.logger.error(f"Failed to load metrics from DB: {e}")
        # On failure, return empty metrics but log the error to make it visible
        metrics = calculate_performance_from_data(pd.DataFrame(), pd.DataFrame())
        return jsonify(sanitize_api_response(metrics))

    metrics = calculate_performance_from_data(trades_df, daily_perf_df)
    
    # Validate metrics to prevent inflated values
    validated_metrics = {}
    
    for key, value in metrics.items():
        if value is None:
            validated_metrics[key] = None
            continue
            
        # Apply appropriate validation based on metric type
        if key in ['total_return', 'annualized_return', 'max_drawdown', 'sharpe_ratio', 'sortino_ratio']:
            # Financial ratios and percentages
            if isinstance(value, (int, float)):
                if pd.isna(value) or np.isinf(value):
                    validated_metrics[key] = None
                else:
                    # Apply reasonable bounds
                    if key == 'total_return' or key == 'annualized_return':
                        if -100 <= value <= 1000:  # Allow up to 1000% returns
                            validated_metrics[key] = value
                        else:
                            print(f"Warning: {key} value {value} is outside expected range")
                            validated_metrics[key] = None
                    elif key == 'max_drawdown':
                        if -100 <= value <= 0:  # Drawdown should be negative or zero
                            validated_metrics[key] = value
                        else:
                            print(f"Warning: {key} value {value} is outside expected range")
                            validated_metrics[key] = None
                    elif key in ['sharpe_ratio', 'sortino_ratio']:
                        if -10 <= value <= 10:  # Reasonable range for risk metrics
                            validated_metrics[key] = value
                        else:
                            print(f"Warning: {key} value {value} is outside expected range")
                            validated_metrics[key] = None
                    else:
                        validated_metrics[key] = value
            else:
                validated_metrics[key] = None
        elif key == 'win_rate':
            # win_rate in calculate_performance_from_data is already in percentage [0,100]
            if isinstance(value, (int, float)):
                if pd.isna(value) or np.isinf(value):
                    validated_metrics[key] = None
                elif 0 <= value <= 100:
                    validated_metrics[key] = float(value)
                else:
                    print(f"Warning: win_rate value {value} is outside expected range")
                    validated_metrics[key] = None
            else:
                validated_metrics[key] = None
        elif key == 'profit_factor':
            # profit_factor is typically >=0 and often in [0, +inf), cap it for display sanity
            if isinstance(value, (int, float)):
                if pd.isna(value) or np.isinf(value):
                    validated_metrics[key] = None
                elif 0 <= value <= 100:
                    validated_metrics[key] = float(value)
                else:
                    print(f"Warning: profit_factor value {value} is outside expected range")
                    validated_metrics[key] = None
            else:
                validated_metrics[key] = None
        elif key in ['num_trades', 'num_winning_trades', 'num_losing_trades']:
            # Count metrics
            if isinstance(value, (int, float)) and value >= 0 and value < 10000:
                validated_metrics[key] = int(value)
            else:
                print(f"Warning: {key} value {value} is outside expected range")
                validated_metrics[key] = 0
        elif key in ['avg_win', 'avg_loss', 'largest_win', 'largest_loss']:
            # Monetary values
            validated_value = validate_financial_value(value, 'price', key)
            validated_metrics[key] = validated_value
        else:
            # For any other metrics, sanitize and validate as a number
            if isinstance(value, (int, float)):
                if pd.isna(value) or np.isinf(value):
                    validated_metrics[key] = None
                else:
                    validated_metrics[key] = value
            else:
                validated_metrics[key] = None
    
    # Sanitize the response before returning
    sanitized_metrics = sanitize_api_response(validated_metrics)
    return jsonify(sanitized_metrics)

@app.route("/api/portfolio")
@cache.cached(timeout=10)
def get_portfolio():
    """Portfolio overview: Use daily_equity as authoritative source."""
    initial_capital = config['strategy']['initial_capital']
    
    # SIMPLE STRATEGY: Use daily_equity table directly
    try:
        db_path = os.path.join(_project_root(), "data", "trade_history.db")
        if os.path.exists(db_path):
            import sqlite3 as _sql
            conn = _sql.connect(db_path)
            try:
                # Get latest equity - THIS IS THE SOURCE OF TRUTH
                df_equity = pd.read_sql_query(
                    "SELECT date, equity FROM daily_equity ORDER BY date DESC LIMIT 1",
                    conn
                )
                
                if not df_equity.empty:
                    total_value = float(df_equity.iloc[0]['equity'])
                    equity_date = df_equity.iloc[0]['date']
                    
                    # Get holdings from trades up to that date
                    trades_df = pd.read_sql_query(
                        "SELECT etf_code, action, quantity FROM trades WHERE date <= ? ORDER BY datetime(date)",
                        conn,
                        params=(equity_date + ' 23:59:59',)
                    )
                    
                    holdings = {}
                    for _, row in trades_df.iterrows():
                        code = str(row['etf_code']).strip()
                        if code:
                            qty = float(row['quantity'])
                            if str(row['action']).lower() == 'sell':
                                qty = -qty
                            holdings[code] = holdings.get(code, 0.0) + qty
                    
                    # Calculate holdings value
                    holdings_value = 0.0
                    positions = []
                    
                    if os.path.exists(ETF_DB_PATH):
                        etf_conn = _sql.connect(ETF_DB_PATH)
                        try:
                            for code, qty in holdings.items():
                                if qty > 1e-9:
                                    price = None
                                    try:
                                        df_p = pd.read_sql_query(
                                            f"SELECT 收盘 FROM etf_{code} WHERE 日期 <= ? ORDER BY 日期 DESC LIMIT 1",
                                            etf_conn, params=(equity_date,)
                                        )
                                        if not df_p.empty:
                                            price = float(df_p.iloc[0]['收盘'])
                                    except:
                                        try:
                                            df_p = pd.read_sql_query(
                                                f"SELECT close FROM etf_{code} WHERE date <= ? ORDER BY date DESC LIMIT 1",
                                                etf_conn, params=(equity_date,)
                                            )
                                            if not df_p.empty:
                                                price = float(df_p.iloc[0]['close'])
                                        except:
                                            pass
                                    
                                    # Validate price and quantity before calculation
                                    validated_price = validate_financial_value(price, 'price', code)
                                    validated_qty = validate_positive_number(qty, 'quantity')
                                    
                                    if validated_price and validated_qty and validated_price > 0 and validated_qty > 0:
                                        value = validated_qty * validated_price
                                        # Validate the calculated value to prevent potential overflow
                                        validated_value = validate_financial_value(value, 'price', code)
                                        
                                        if validated_value:
                                            holdings_value += validated_value
                                            positions.append({
                                                "etf_code": code,
                                                "quantity": validated_qty,
                                                "price": validated_price,
                                                "value": validated_value,
                                            })
                        finally:
                            etf_conn.close()
                    
                    # Cash = Total - Holdings, with validation
                    cash = total_value - holdings_value
                    validated_cash = validate_financial_value(cash, 'price', 'cash')
                    validated_holdings_value = validate_financial_value(holdings_value, 'price', 'holdings')
                    validated_total_value = validate_financial_value(total_value, 'price', 'total')
                    
                    conn.close()
                    portfolio_data = {
                        "cash": validated_cash if validated_cash is not None else 0.0,
                        "holdings_value": validated_holdings_value if validated_holdings_value is not None else 0.0,
                        "total_value": validated_total_value if validated_total_value is not None else config['strategy']['initial_capital'],
                        "positions": positions,
                    }
                    
                    # Sanitize the response before returning
                    sanitized_data = sanitize_api_response(portfolio_data)
                    return jsonify(sanitized_data)
                    
                conn.close()
            except Exception as e:
                print(f"[Portfolio] DB error: {e}")
                conn.close()
    except Exception as e:
        print(f"[Portfolio] Error: {e}")
    
    # Fallback
    return jsonify({
        "cash": initial_capital,
        "holdings_value": 0.0,
        "total_value": initial_capital,
        "positions": [],
    })

@app.route("/api/qlib/factors")
@cache.cached(timeout=10)
def get_qlib_factors():
    factors_data = []
    # 1) 优先从 data/qlib_factors 读最新一行
    try:
        if os.path.exists(QLIB_FACTORS_DIR):
            for filename in os.listdir(QLIB_FACTORS_DIR):
                if filename.endswith(".csv"):
                    file_path = os.path.join(QLIB_FACTORS_DIR, filename)
                    df = pd.read_csv(file_path)
                    if not df.empty:
                        latest_factors = df.iloc[-1].to_dict()
                        latest_factors['strategy'] = _strategy_snapshot()
                        factors_data.append(latest_factors)
    except Exception as e:
        print(f"Error reading qlib factors: {e}")

    # 2) 若为空，回退：从本地 SQLite 计算一行（ETF_LIST）
    try:
        if not factors_data:
            etf_list_str = os.getenv("ETF_LIST", "")
            etf_codes = [c.strip() for c in etf_list_str.split(',') if c.strip()]
            if not etf_codes:
                etf_codes = _infer_etf_codes()
            if etf_codes:
                import sqlite3
                conn = None
                try:
                    if os.path.exists(ETF_DB_PATH):
                        conn = sqlite3.connect(ETF_DB_PATH)
                    for code in etf_codes:
                        try:
                            df = None
                            if conn is not None:
                                try:
                                    df = pd.read_sql_query(f"SELECT * FROM etf_{code}", conn)
                                except Exception:
                                    df = None
                            if df is None or df.empty:
                                # 尝试即时拉取并落库
                                fetched = fetch_etf_data(code, days=800)
                                if fetched is not None and not fetched.empty:
                                    save_to_db(fetched, code, db_path=ETF_DB_PATH)
                                    df = fetched
                            if df is None or df.empty:
                                # Try to fetch and save data if it's missing
                                fetched = fetch_etf_data(code, days=800)
                                if fetched is not None and not fetched.empty:
                                    save_to_db(fetched, code, db_path=ETF_DB_PATH)
                                    df = fetched
                            
                            if df is None or df.empty:
                                # Placeholder if data is still unavailable
                                factors_data.append({
                                    'date': pd.Timestamp.today().strftime('%Y-%m-%d'),
                                    'symbol': code,
                                    'ret_1d_pct': None,
                                    'vol_20d_pct': None,
                                    'rsi_14': None,
                                })
                                continue
                            
                            # Validate OHLCV data to prevent inconsistencies
                            df, validation_stats = validate_ohlcv_data(df, symbol=code)
                            if df.empty:
                                print(f"Validation failed for {code}, stats: {validation_stats}")
                                continue
                            # 规范日期列与收盘列
                            dcol = '日期' if '日期' in df.columns else ('date' if 'date' in df.columns else None)
                            ccol = '收盘' if '收盘' in df.columns else ('收盘价' if '收盘价' in df.columns else ('close' if 'close' in df.columns else None))
                            if not dcol or not ccol:
                                continue
                            dts = pd.to_datetime(df[dcol], errors='coerce')
                            close = pd.to_numeric(df[ccol], errors='coerce').astype(float)
                            ok = pd.DataFrame({'date': dts, 'close': close}).dropna().sort_values('date')
                            # 即使样本少于20天也输出一行，部分因子可能为 NaN，前端会显示为 --
                            ret = ok['close'].pct_change() * 100.0
                            vol_20d = ret.rolling(20).std() * (252.0 ** 0.5)
                            delta = ok['close'].diff()
                            gain = delta.clip(lower=0.0)
                            loss = (-delta).clip(lower=0.0)
                            roll_up = gain.rolling(14).mean()
                            roll_down = loss.rolling(14).mean()
                            rs = roll_up / roll_down.replace(0.0, pd.NA)
                            rsi_14 = 100.0 - (100.0 / (1.0 + rs))
                            out = {
                                'date': ok['date'].iloc[-1].strftime('%Y-%m-%d'),
                                'symbol': code,
                                'ret_1d_pct': float(ret.iloc[-1]) if pd.notna(ret.iloc[-1]) else None,
                                'vol_20d_pct': float(vol_20d.iloc[-1]) if pd.notna(vol_20d.iloc[-1]) else None,
                                'rsi_14': float(rsi_14.iloc[-1]) if pd.notna(rsi_14.iloc[-1]) else None,
                                'strategy': _strategy_snapshot(),
                            }
                            factors_data.append(out)
                        except Exception:
                            continue
                finally:
                    if conn is not None:
                        conn.close()
    except Exception as e:
        print(f"Fallback factors from DB failed: {e}")

    return jsonify(factors_data)

@app.route("/api/decisions")
@cache.cached(timeout=3600)
def get_decisions():
    if not os.path.exists(DECISIONS_DIR):
        return jsonify([])

    decisions = []
    try:
        filenames = sorted([f for f in os.listdir(DECISIONS_DIR) if f.endswith(".json")], reverse=True)
        for filename in filenames[:200]:
            file_path = os.path.join(DECISIONS_DIR, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                decision_data = json.load(f)
                decision_data['filename'] = filename
                parts = filename.split('_')
                if len(parts) >= 2:
                    decision_data['date'] = parts[0]
                    decision_data['etf_code'] = parts[1]
                    decision_data.setdefault('etf', decision_data['etf_code'])
                # Basic defaults to avoid frontend errors
                decision_data.setdefault('decision', 'hold')
                decision_data.setdefault('confidence', 0.5)
                decisions.append(decision_data)
    except Exception as e:
        print(f"Error reading decisions: {e}")
        return jsonify({"error": "Failed to load AI decisions"}), 500

    return jsonify(decisions)

@app.route("/api/etf_tickers")
@cache.cached(timeout=60)  # Cache live data for 60 seconds
def get_etf_tickers():
    live = request.args.get('live') == '1'
    source = "history"
    etf_list_str = os.getenv("ETF_LIST", "")
    etf_codes = [code.strip() for code in etf_list_str.split(',') if code.strip()]
    etf_set = set(etf_codes)

    # Try live sources when requested (regardless of open/close)
    if live and ak is not None:
        # 1) Eastmoney
        try:
            df = ak.fund_etf_spot_em()
            source = "eastmoney"
            df = df[['代码', '名称', '最新价', '涨跌幅', '成交额']].copy()
            df.rename(columns={'代码':'code','名称':'name','最新价':'price','涨跌幅':'pct','成交额':'turnover'}, inplace=True)
            def _pct_to_float(x):
                try:
                    s = str(x).replace('%','').strip()
                    return float(s)
                except Exception:
                    return None
            df['pct_change'] = df['pct'].apply(_pct_to_float)
            # Filter to ETF_LIST if provided
            if etf_set:
                df = df[df['code'].astype(str).isin(etf_set)]
            rows = df[['code','name','price','pct_change','turnover']].to_dict('records')
            return jsonify({"market_open": is_market_open(), "source": source, "rows": rows})
        except Exception as e:
            print(f"Failed to fetch live tickers from eastmoney: {e}")
            # 2) Fallback to THS if available
            try:
                if hasattr(ak, 'fund_etf_spot_ths'):
                    df = ak.fund_etf_spot_ths()
                    source = "ths"
                    cols = df.columns
                    code_col = '代码' if '代码' in cols else ('symbol' if 'symbol' in cols else None)
                    name_col = '名称' if '名称' in cols else ('name' if 'name' in cols else None)
                    price_col = '最新价' if '最新价' in cols else ('price' if 'price' in cols else None)
                    pct_col = '涨跌幅' if '涨跌幅' in cols else ('pct_change' if 'pct_change' in cols else None)
                    turnover_col = '成交额' if '成交额' in cols else ('turnover' if 'turnover' in cols else None)
                    if code_col and name_col and price_col and pct_col:
                        dd = pd.DataFrame({
                            'code': df[code_col],
                            'name': df[name_col],
                            'price': df[price_col],
                            'pct': df[pct_col],
                            'turnover': df[turnover_col] if turnover_col in df.columns else 0,
                        })
                        def _pct_to_float(x):
                            try:
                                s = str(x).replace('%','').strip()
                                return float(s)
                            except Exception:
                                return None
                        dd['pct_change'] = dd['pct'].apply(_pct_to_float)
                        if etf_set:
                            dd = dd[dd['code'].astype(str).isin(etf_set)]
                        rows = dd[['code','name','price','pct_change','turnover']].to_dict('records')
                        return jsonify({"market_open": is_market_open(), "source": source, "rows": rows})
            except Exception as e2:
                print(f"Failed to fetch live tickers from ths: {e2}")
                # Fall through to history

    # If explicitly live and failed to fetch, do NOT fallback to history to avoid misleading source
    if live:
        return jsonify({"ok": False, "market_open": is_market_open(), "source": "live_failed", "rows": []})

    # Fallback -> history from DB when not requesting live
    rows = []
    for code in etf_codes:
        price = _read_latest_price(code)
        if price is not None:
            rows.append({"code": code, "name": "-", "price": float(price), "pct_change": 0.0, "turnover": 0})
    return jsonify({"ok": True, "market_open": False, "source": source, "rows": rows})

@app.route("/api/vega_risk")
@cache.cached(timeout=10, query_string=True)  # Cache based on query string
def get_vega_risk_api():
    code = request.args.get('code')
    period = request.args.get('period', type=int)
    if code:
        df = compute_vega_proxy_series(code, period=period)
        if df is None or df.empty:
            # Fallback: fetch & save then recompute
            try:
                fetched = fetch_etf_data(code, days=800)
                if fetched is not None and not fetched.empty:
                    save_to_db(fetched, code, db_path=ETF_DB_PATH)
                    df = compute_vega_proxy_series(code, period=period)
            except Exception:
                pass
        return jsonify({"rows": df.to_dict('records') if df is not None else []})
    else:
        etf_list_str = os.getenv("ETF_LIST", "")
        etf_codes = [c.strip() for c in etf_list_str.split(',') if c.strip()]
        if not etf_codes:
            etf_codes = _infer_etf_codes()
        summary = get_vega_summary(etf_codes)
        if (not summary) and etf_codes:
            # Fallback: pull data for all codes, then recompute summary
            for c in etf_codes:
                try:
                    fetched = fetch_etf_data(c, days=800)
                    if fetched is not None and not fetched.empty:
                        save_to_db(fetched, c, db_path=ETF_DB_PATH)
                except Exception:
                    continue
            summary = get_vega_summary(etf_codes)
        return jsonify(summary)

@app.route("/api/qlib/status")
def get_qlib_status():
    provider_ok = os.path.exists(os.path.join(QLIB_DIR, "instruments", "all.txt"))
    return jsonify({"provider_initialized": provider_ok, "path": QLIB_DIR})

@app.route("/api/refresh_prices", methods=["POST"]) 
def refresh_prices():
    etf_list_str = os.getenv("ETF_LIST", "")
    codes = []
    try:
        # Optional override from request JSON: {"codes": ["510300", ...]}
        body = request.get_json(silent=True) or {}
        if body and isinstance(body.get("codes"), list):
            codes = [str(c).strip() for c in body.get("codes") if str(c).strip()]
    except Exception:
        codes = []
    if not codes:
        codes = [c.strip() for c in etf_list_str.split(',') if c.strip()]
    if not codes:
        return jsonify({"ok": False, "msg": "No ETF codes configured (env ETF_LIST)."}), 400

    updated, errors = 0, []
    for code in codes:
        try:
            df = fetch_etf_data(code, days=800)
            if df is None or df.empty:
                errors.append({"code": code, "err": "empty data"})
                continue
            save_to_db(df, code, db_path=ETF_DB_PATH)
            updated += 1
        except Exception as e:
            errors.append({"code": code, "err": str(e)})
            continue
    # ok=True if at least one code updated; partial success returns 207 for visibility
    ok = updated > 0
    status = 200 if (ok and len(errors) == 0) else 207  # 207: multi-status (partial success)
    return jsonify({"ok": ok, "updated": updated, "failed": len(errors), "errors": errors, "msg": f"updated {updated}, failed {len(errors)}"}), status

@app.route("/api/options/atm_iv")
@cache.cached(timeout=120)
def api_options_atm_iv():
    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({"ok": False, "msg": "missing code"}), 400
    try:
        chain = get_option_chain_with_iv_greeks(code)
        if chain is None or chain.empty:
            return jsonify({"ok": True, "rows": []})
        # Determine ATM row (nearest strike to latest price)
        S = fetch_etf_latest_price(code)
        if S <= 0:
            # fallback: pick mid-row
            dd = chain.copy()
            row = dd.iloc[len(dd)//2]
        else:
            dd = chain.copy()
            dd["_dist"] = (pd.to_numeric(dd["strike"], errors="coerce") - S).abs()
            dd = dd.sort_values(["expiry", "_dist"]).reset_index(drop=True)
            row = dd.iloc[0]
        from datetime import datetime as _dt
        T_days = int(max(0, (pd.to_datetime(row.get("expiry")) - _dt.now()).days)) if pd.notna(row.get("expiry")) else None
        one = {
            "opt_type": str(row.get("option_type")),
            "K": float(row.get("strike")) if pd.notna(row.get("strike")) else None,
            "T_days": T_days,
            "mid": float(row.get("mid")) if pd.notna(row.get("mid")) else None,
            "iv": float(row.get("iv")) if pd.notna(row.get("iv")) else None,
        }
        return jsonify({"ok": True, "rows": [one]})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/api/options/chain")
@cache.cached(timeout=120)
def api_options_chain():
    code = request.args.get('code', '').strip()
    if not code:
        return jsonify({"ok": False, "msg": "missing code"}), 400
    try:
        chain = get_option_chain_with_iv_greeks(code)
        if chain is None or chain.empty:
            return jsonify({"ok": True, "rows": []})
        now_dt = datetime.now()
        out_rows = []
        for _, r in chain.iterrows():
            try:
                expiry = pd.to_datetime(r.get("expiry")) if pd.notna(r.get("expiry")) else None
                T_days = int(max(0, (expiry - now_dt).days)) if expiry is not None else None
                out_rows.append({
                    "opt_type": str(r.get("option_type")),
                    "K": float(r.get("strike")) if pd.notna(r.get("strike")) else None,
                    "expiry": str(expiry.date()) if expiry is not None else None,
                    "T_days": T_days,
                    "price_mid": float(r.get("mid")) if pd.notna(r.get("mid")) else None,
                    "iv": float(r.get("iv")) if pd.notna(r.get("iv")) else None,
                    "delta": float(r.get("delta")) if pd.notna(r.get("delta")) else None,
                    "gamma": float(r.get("gamma")) if pd.notna(r.get("gamma")) else None,
                    "vega": float(r.get("vega")) if pd.notna(r.get("vega")) else None,
                    "theta": float(r.get("theta")) if pd.notna(r.get("theta")) else None,
                })
            except Exception:
                continue
        return jsonify({"ok": True, "rows": out_rows})
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

@app.route("/api/audit/summary")
@cache.cached(timeout=60)
def api_audit_summary():
    try:
        pattern = os.path.join(LOGS_DIR, "resimulation_*.log")
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        if not files:
            return jsonify({"ok": True, "rows": [], "msg": "no logs"})
        fp = files[0]
        with open(fp, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        # Counters
        pos_constraint = 0
        adj_sell_qty = 0
        compliant_trades = None
        daily_equity_entries = None
        daily_perf_entries = None
        started_at = None
        finished_at = None
        for ln in lines:
            if started_at is None and "Starting trade history re-simulation" in ln:
                started_at = ln.split(' - ')[0]
            if "Position constraint triggered" in ln:
                pos_constraint += 1
            if "Adjusted sell qty to" in ln:
                adj_sell_qty += 1
            if "Saved" in ln and "compliant trades" in ln:
                # e.g., Saved 42 compliant trades
                try:
                    n = int(re.search(r"Saved\s+(\d+)\s+compliant trades", ln).group(1))
                    compliant_trades = n
                except Exception:
                    pass
            if "Saved daily equity report with" in ln:
                try:
                    n = int(re.search(r"with\s+(\d+)\s+entries", ln).group(1))
                    daily_equity_entries = n
                except Exception:
                    pass
            if "Saved daily performance report with" in ln:
                try:
                    n = int(re.search(r"with\s+(\d+)\s+entries", ln).group(1))
                    daily_perf_entries = n
                except Exception:
                    pass
            if "=== Audit and Re-simulation Process Finished ===" in ln:
                finished_at = ln.split(' - ')[0]
        out = {
            "ok": True,
            "latest_log": os.path.basename(fp),
            "started_at": started_at,
            "finished_at": finished_at,
            "position_constraint_count": pos_constraint,
            "adjusted_sell_qty_count": adj_sell_qty,
            "compliant_trades_saved": compliant_trades,
            "daily_equity_entries": daily_equity_entries,
            "daily_performance_entries": daily_perf_entries,
        }
        return jsonify(out)
    except Exception as e:
        return jsonify({"ok": False, "msg": str(e)}), 500

if __name__ == "__main__":
    server_config = config.get('flask', {})
    host = '0.0.0.0'  # Force listen on all interfaces for deployment
    port = int(os.getenv('FLASK_PORT', str(server_config.get('port', 5001))))
    debug_env = os.getenv('FLASK_DEBUG', '')
    debug = (debug_env.lower() == 'true') if debug_env else bool(server_config.get('debug', False))
    app.run(host=host, port=port, debug=debug)
