# -*- coding: utf-8 -*-
"""
日志查询脚本
功能：
1. 按日期查询指定日志文件。
2. 筛选特定级别的日志（如 WARNING）。
3. 按ETF代码或其他关键词过滤日志内容。

用法：
  uv run python scripts/query_log.py --date 20251217 --level WARNING --keyword 510050
"""
import os
import argparse
import re

# --- Constants ---
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
LOG_DIR = os.path.join(ROOT, 'logs')

def query_logs(date: str, level: str | None = None, keyword: str | None = None):
    """Queries and filters the resimulation log file."""
    log_file = os.path.join(LOG_DIR, f"resimulation_{date}.log")

    if not os.path.exists(log_file):
        print(f"Error: Log file not found for date {date} at '{log_file}'")
        return

    print(f"--- Querying Log File: {os.path.basename(log_file)} ---")
    print(f"Filters: Level='{level or 'ANY'}' | Keyword='{keyword or 'ANY'}'\n")

    match_count = 0
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            for line in f:
                line_upper = line.upper()
                level_match = True
                keyword_match = True

                if level and f" - {level.upper()} - " not in line_upper:
                    level_match = False
                
                if keyword and not re.search(re.escape(keyword), line, re.IGNORECASE):
                    keyword_match = False
                
                if level_match and keyword_match:
                    print(line.strip())
                    match_count += 1
        
        print(f"\n--- Found {match_count} matching log entries. ---")

    except Exception as e:
        print(f"An error occurred while reading the log file: {e}")

def main():
    parser = argparse.ArgumentParser(description="Query and filter re-simulation log files.")
    parser.add_argument(
        "--date",
        type=str,
        required=True,
        help="The date of the log file to query, in YYYYMMDD format (e.g., '20251217')."
    )
    parser.add_argument(
        "--level",
        type=str,
        choices=['INFO', 'WARNING', 'ERROR'],
        help="Filter by log level (e.g., 'WARNING')."
    )
    parser.add_argument(
        "--keyword",
        type=str,
        help="Filter by a keyword or ETF code (case-insensitive)."
    )
    args = parser.parse_args()

    query_logs(args.date, args.level, args.keyword)

if __name__ == "__main__":
    main()

