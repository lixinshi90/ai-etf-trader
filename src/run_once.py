# -*- coding: utf-8 -*-
"""
一次性初始化脚本：创建绩效起始日期标记 perf_start.json
用法：
    python -m src.run_once
说明：
- 若文件已存在，则不会覆盖，只打印现有起始日。
- 若不存在，则以今天作为起始日写入项目根目录 perf_start.json。
"""
from __future__ import annotations

import json
import os
from datetime import datetime


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def main():
    root = _project_root()
    fp = os.path.join(root, "perf_start.json")
    if os.path.exists(fp):
        with open(fp, "r", encoding="utf-8") as f:
            obj = json.load(f)
        print("已存在绩效起始日：", obj)
        return
    today = datetime.now().strftime("%Y-%m-%d")
    obj = {"start_date": today}
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    print("已创建绩效起始日：", obj)


if __name__ == "__main__":
    main()

