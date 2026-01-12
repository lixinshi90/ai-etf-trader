#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
净值数据修正脚本 - 完全重建净值记录
"""

import os
import shutil


def backup_file(file_path: str) -> str:
    """备份文件，返回备份路径"""
    backup_path = file_path + '.bak'
    shutil.copy2(file_path, backup_path)
    print(f"已备份文件: {backup_path}")
    return backup_path


def rebuild_nav_data() -> bool:
    """重建净值数据，返回是否成功"""
    log_file = 'logs/daily.log'

    if not os.path.exists(log_file):
        print(f"错误: 找不到文件 {log_file}")
        return False

    # 备份原日志
    backup_file(log_file)

    # 正确净值映射（日期 -> 净值）
    correct_nav = {
        '2025-11-26': 100000.00,
        '2025-11-27': 99559.67,
        '2025-11-28': 99135.43,
        '2025-12-01': 99394.43,
        '2025-12-02': 98778.42,
        '2025-12-03': 98296.48,
        '2025-12-05': 99118.55,
        '2025-12-08': 99411.59,
        '2025-12-09': 97746.13,
        '2025-12-11': 97081.57,
        '2025-12-12': 98436.43,
        '2025-12-15': 99777.74,
        '2025-12-16': 99382.11,
        '2025-12-17': 99646.61,
        '2025-12-18': 99499.70,
        '2025-12-19': 99844.89,
        '2025-12-22': 99906.27,
        '2025-12-23': 99795.48,
    }

    # 读取日志
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    # 移除旧净值行
    filtered = [ln for ln in lines if ('已写入日终快照' not in ln and '当前总资产' not in ln)]
    removed = len(lines) - len(filtered)

    # 将正确净值插入对应日期最后一行之后
    added = 0
    for date_str, nav in correct_nav.items():
        # 找到该日期最后一行
        idx = None
        for i in range(len(filtered) - 1, -1, -1):
            if date_str in filtered[i]:
                idx = i
                break
        if idx is not None:
            ts_part = filtered[idx].split(' ')[0] + ' ' + filtered[idx].split(' ')[1]
            nav_line = f"{ts_part} INFO 已写入日终快照 {date_str}: {nav:.2f}\n"
            filtered.insert(idx + 1, nav_line)
            added += 1
            print(f"已添加净值记录: {date_str}: {nav:.2f}")
        else:
            print(f"警告: 日志中找不到日期 {date_str} ，未插入净值记录！")

    # 写回文件
    with open(log_file, 'w', encoding='utf-8') as f:
        f.writelines(filtered)

    print(f"\n净值重建完成，删除旧记录 {removed} 条，新增净值 {added} 条")
    return True


def verify_changes():
    """打印当前日志中的净值行"""
    log_file = 'logs/daily.log'
    if not os.path.exists(log_file):
        print('日志文件不存在，无法验证')
        return
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    nav_lines = [ln.strip() for ln in lines if '已写入日终快照' in ln]
    print(f"\n当前共 {len(nav_lines)} 条净值记录：")
    for ln in nav_lines[-20:]:
        print(ln)


def main():
    print('=== 重建净值脚本 ===')
    print('此脚本将删除旧净值并插入正确净值记录，请确保已备份日志文件\n')
    ok = rebuild_nav_data()
    if ok:
        verify_changes()
    else:
        print('重建失败')


if __name__ == '__main__':
    main()

