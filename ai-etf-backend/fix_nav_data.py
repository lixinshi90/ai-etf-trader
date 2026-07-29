#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
修正净值数据脚本 - 修复历史日志中的虚高净值问题
"""

import re
import os
from datetime import datetime
import shutil

def backup_file(file_path):
    """备份文件"""
    backup_path = file_path + '.bak'
    shutil.copy2(file_path, backup_path)
    print(f"已备份文件: {backup_path}")
    return backup_path

def fix_nav_data():
    """修正净值数据"""
    log_file = 'logs/daily.log'
    
    # 检查文件是否存在
    if not os.path.exists(log_file):
        print(f"错误: 找不到文件 {log_file}")
        return False
    
    # 备份原文件
    backup_file(log_file)
    
    # 净值修正映射 (旧净值 -> 新净值)
    nav_corrections = {
        '99085.04': '99135.43',  # 2025-11-28
        '99344.03': '99394.43',  # 2025-12-01
        '98692.21': '98778.42',  # 2025-12-02
        '98167.49': '98296.48',  # 2025-12-03
        '98975.58': '99118.55',  # 2025-12-05
        '99127.74': '99411.59',  # 2025-12-08
        '98363.53': '97746.13',  # 2025-12-09
        '97762.21': '97081.57',  # 2025-12-11
        '98213.94': '98436.43',  # 2025-12-12
        '99444.53': '99777.74',  # 2025-12-15
        '99152.09': '99382.11',  # 2025-12-16
        '99962.97': '99646.61',  # 2025-12-17
        '99040.38': '99499.70',  # 2025-12-18
    }
    
    # 读取日志文件
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            log_lines = f.readlines()
    except Exception as e:
        print(f"读取文件失败: {e}")
        return False
    
    # 处理每一行日志
    new_lines = []
    changes_made = 0
    
    for line in log_lines:
        original_line = line
        modified_line = line
        
        # 查找并替换净值数据
        for old_nav, new_nav in nav_corrections.items():
            if old_nav in line:
                modified_line = modified_line.replace(old_nav, new_nav)
                if modified_line != line:
                    print(f"修改: {old_nav} -> {new_nav}")
                    print(f"  原行: {line.strip()}")
                    print(f"  新行: {modified_line.strip()}")
                    changes_made += 1
                    break
        
        new_lines.append(modified_line)
    
    # 写回文件
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
        print(f"\n净值数据修改完成！共修改 {changes_made} 处")
        return True
    except Exception as e:
        print(f"写入文件失败: {e}")
        return False

def verify_changes():
    """验证修改结果"""
    log_file = 'logs/daily.log'
    
    print("\n=== 验证修改结果 ===")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"读取文件失败: {e}")
        return
    
    # 查找包含净值信息的行
    nav_lines = []
    for line in lines:
        if '已写入日终快照' in line or '当前总资产' in line:
            nav_lines.append(line.strip())
    
    print(f"找到 {len(nav_lines)} 条净值记录:")
    for i, line in enumerate(nav_lines[-10:], 1):  # 显示最后10条
        print(f"{i:2d}. {line}")
    
    # 检查特定的日期
    target_dates = ['2025-11-28', '2025-12-01', '2025-12-02', '2025-12-22']
    print(f"\n=== 检查特定日期的净值 ===")
    
    for date in target_dates:
        for line in nav_lines:
            if date in line:
                print(f"{date}: {line}")
                break

def show_current_nav():
    """显示当前净值信息"""
    log_file = 'logs/daily.log'
    
    print("=== 当前净值信息 ===")
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except Exception as e:
        print(f"读取文件失败: {e}")
        return
    
    # 查找净值行
    nav_lines = []
    for line in lines:
        if '已写入日终快照' in line or '当前总资产' in line:
            nav_lines.append(line.strip())
    
    if nav_lines:
        print(f"共找到 {len(nav_lines)} 条净值记录")
        print("\n最近10条记录:")
        for i, line in enumerate(nav_lines[-10:], 1):
            print(f"{i:2d}. {line}")
    else:
        print("未找到净值记录")

def main():
    """主函数"""
    print("=== 净值数据修正工具 ===")
    print("此脚本将修正历史日志中的虚高净值问题")
    print()
    
    # 显示当前净值
    show_current_nav()
    
    # 询问是否继续
    response = input("\n是否继续修正净值数据? (y/N): ").strip().lower()
    if response not in ['y', 'yes']:
        print("操作已取消")
        return
    
    # 执行修正
    if fix_nav_data():
        # 验证结果
        verify_changes()
        print("\n=== 修正完成 ===")
        print("请检查修改结果，如需恢复，请使用备份文件: logs/daily.log.bak")
    else:
        print("\n=== 修正失败 ===")
        print("请检查错误信息并重试")

if __name__ == "__main__":
    main()
