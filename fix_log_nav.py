#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fix_log_nav.py

目的：
- 修正 logs/daily.log 中“日终快照/净值”相关日志的乱码与虚高数值
- 将指定日期的净值强制替换为用户给定的 correct_nav
- 对同一天出现多条“日终快照”记录：仅保留最后一条（或可配置保留第一条）

说明：
- 本脚本只改 logs/daily.log（会先备份为 logs/daily.log.bak2，避免覆盖你已有的 .bak）
- 仅处理包含“日终快照”语义的行：
  - 正常："已写入日终快照 YYYY-MM-DD: <nav>"
  - 乱码：例如 "宸插啓鍏ユ棩缁堝揩鐓?YYYY-MM-DD: <nav>"（常见 UTF-8 被按 GBK 解读）

使用：
  python fix_log_nav.py

"""

from __future__ import annotations

import os
import re
import shutil
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


# 你确认的“正确净值”（9万~10万区间）
CORRECT_NAV: Dict[str, float] = {
    '2025-11-26': 100000.00,
    '2025-11-27': 99559.67,
    '2025-11-28': 99135.43,
    '2025-11-30': 99344.03,
    '2025-12-01': 99394.43,
    '2025-12-02': 98778.42,
    '2025-12-03': 98296.48,
    '2025-12-05': 99118.55,
    '2025-12-07': 99411.59,
    '2025-12-08': 99411.59,
    '2025-12-09': 97746.13,
    '2025-12-11': 97081.57,
    '2025-12-12': 98436.43,
    '2025-12-14': 99777.74,
    '2025-12-15': 99777.74,
    '2025-12-16': 99382.11,
    '2025-12-17': 99646.61,
    '2025-12-18': 99499.70,
    '2025-12-19': 99844.89,
    '2025-12-22': 99906.27,
    '2025-12-23': 99795.48,
}

LOG_PATH = os.path.join('logs', 'daily.log')

# 识别“日终快照”行（兼容乱码前缀）
# 例：2025-12-23 19:21:21,204 INFO 宸插啓鍏ユ棩缁堝揩鐓?2025-12-23: 109925.68
SNAPSHOT_RE = re.compile(
    r'^(?P<ts>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2},\d{3})\s+INFO\s+(?P<prefix>.*?)(?P<date>\d{4}-\d{2}-\d{2})\s*:\s*(?P<nav>-?\d+(?:\.\d+)?)\s*$'
)

# 判断 prefix 是否表示“已写入日终快照”（正常/乱码都算）
# 常见乱码：宸插啓鍏ユ棩缁堝揩鐓?
SNAPSHOT_PREFIX_KEYWORDS = [
    '已写入日终快照',
    '日终快照',
    '宸插啓鍏ユ棩缁堝揩鐓',
]


def _is_snapshot_prefix(prefix: str) -> bool:
    p = (prefix or '').strip()
    return any(k in p for k in SNAPSHOT_PREFIX_KEYWORDS)


def backup_file(src: str) -> str:
    """备份到 .bak2（避免覆盖用户已有 .bak）"""
    dst = src + '.bak2'
    shutil.copy2(src, dst)
    print(f'[fix_log_nav] 已备份: {dst}')
    return dst


@dataclass
class SnapshotLine:
    idx: int
    ts: str
    date: str
    raw_nav: float
    raw_line: str


def load_lines(path: str) -> List[str]:
    # 这里用 errors='replace'，避免遇到未知编码直接炸
    with open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.readlines()


def parse_snapshot_lines(lines: List[str]) -> List[SnapshotLine]:
    out: List[SnapshotLine] = []
    for i, ln in enumerate(lines):
        m = SNAPSHOT_RE.match(ln.strip('\n'))
        if not m:
            continue
        prefix = m.group('prefix') or ''
        if not _is_snapshot_prefix(prefix):
            continue
        date = m.group('date')
        try:
            nav = float(m.group('nav'))
        except Exception:
            continue
        out.append(SnapshotLine(idx=i, ts=m.group('ts'), date=date, raw_nav=nav, raw_line=ln))
    return out


def fix_snapshots(lines: List[str], keep: str = 'last') -> Tuple[List[str], Dict[str, int]]:
    """修正快照行：
    - 同日多条：仅保留 keep=last/first
    - 快照行改为统一中文格式，并替换为 CORRECT_NAV 中的值
    """
    snaps = parse_snapshot_lines(lines)

    # 按日期聚合
    by_date: Dict[str, List[SnapshotLine]] = {}
    for s in snaps:
        by_date.setdefault(s.date, []).append(s)

    stats = {
        'found_snapshot_lines': len(snaps),
        'dates_with_multiple_snapshots': 0,
        'removed_duplicate_snapshot_lines': 0,
        'updated_snapshot_values': 0,
        'kept_snapshot_lines': 0,
    }

    # 计算要保留的索引集合
    keep_indices = set()
    for d, arr in by_date.items():
        arr_sorted = sorted(arr, key=lambda x: x.idx)
        if len(arr_sorted) > 1:
            stats['dates_with_multiple_snapshots'] += 1
        chosen = arr_sorted[-1] if keep == 'last' else arr_sorted[0]
        keep_indices.add(chosen.idx)
        stats['kept_snapshot_lines'] += 1
        stats['removed_duplicate_snapshot_lines'] += max(0, len(arr_sorted) - 1)

    new_lines: List[str] = []
    for i, ln in enumerate(lines):
        if i in {s.idx for s in snaps}:
            # 这是快照行：如果不是被选择保留的那条 -> 丢弃
            if i not in keep_indices:
                continue

            m = SNAPSHOT_RE.match(ln.strip('\n'))
            if not m:
                # 理论不会发生
                continue
            date = m.group('date')
            ts = m.group('ts')

            # 使用 correct_nav 覆盖；如果没有提供该日，则保留原值但规范格式
            nav_val = CORRECT_NAV.get(date)
            if nav_val is None:
                try:
                    nav_val = float(m.group('nav'))
                except Exception:
                    nav_val = 0.0
            else:
                stats['updated_snapshot_values'] += 1

            fixed = f"{ts} INFO 已写入日终快照 {date}: {nav_val:.2f}\n"
            new_lines.append(fixed)
        else:
            new_lines.append(ln)

    return new_lines, stats


def main():
    if not os.path.exists(LOG_PATH):
        raise SystemExit(f'[fix_log_nav] 找不到日志文件: {LOG_PATH}')

    lines = load_lines(LOG_PATH)
    backup_file(LOG_PATH)

    new_lines, stats = fix_snapshots(lines, keep='last')

    # 写回（统一 UTF-8）
    with open(LOG_PATH, 'w', encoding='utf-8', newline='') as f:
        f.writelines(new_lines)

    print('[fix_log_nav] 完成。统计信息:')
    for k, v in stats.items():
        print(f'  - {k}: {v}')

    # 额外校验：检查是否仍有 > 100000 的快照值（理论上不应出现）
    check_lines = load_lines(LOG_PATH)
    snaps = parse_snapshot_lines(check_lines)
    too_high = [(s.date, s.raw_nav, s.raw_line.strip()) for s in snaps if s.raw_nav > 100000.0 + 1e-6]
    if too_high:
        print('\n[fix_log_nav] 警告：仍发现 > 100000 的快照值。')
        print('[fix_log_nav] 这些日期未在 CORRECT_NAV 中，或你需要为这些日期提供“正确净值”。')
        for d, nav, ln in too_high[:50]:
            print(f'  {d} {nav:.2f} | {ln}')
        print('\n[fix_log_nav] 你可以把这些日期加入 CORRECT_NAV 后再运行一次。')
    else:
        print('\n[fix_log_nav] 校验通过：未发现 > 100000 的日终快照值。')


if __name__ == '__main__':
    main()

