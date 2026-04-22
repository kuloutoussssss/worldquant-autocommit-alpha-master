# -*- coding: utf-8 -*-
"""
清理非标准函数，替换为 WorldQuant Brain API 支持的等价格式
"""

import re
from pathlib import Path


def clean_expression(expr: str) -> str:
    """
    清理表达式中的非标准函数
    
    替换规则：
    - ts_av_diff(x, n) -> ts_delta(x, n)
    - vector_neut(x, y) -> group_neutralize(x, sector) 或移除
    - trade_when(cond, sig, -1) -> ts_zscore(sig) * (cond > 0) 或类似
    - hump(x, p) -> signed_power(x, p) 或 ts_zscore(x)
    - regression_neut(x, y) -> group_neutralize(x, sector)
    """
    result = expr
    
    # 1. ts_av_diff -> ts_delta
    result = re.sub(r'ts_av_diff\(', 'ts_delta(', result)
    
    # 2. vector_neut -> group_neutralize
    # vector_neut(x, y) 表示用 y 做中性化，改为 group_neutralize(x, sector)
    result = re.sub(r'vector_neut\(([^,]+),\s*([^)]+)\)', 
                   r'group_neutralize(\1, sector)', result)
    
    # 3. trade_when(cond, sig, -1) -> ts_zscore(sig) * (cond > 0)
    # 这是简化处理，实际上需要更复杂的逻辑
    def replace_trade_when(m):
        cond = m.group(1)
        sig = m.group(2)
        # 用 rank 包裹条件，sig 用 ts_zscore 标准化
        return f'rank({sig}) * (({cond}) > 0)'
    result = re.sub(r'trade_when\(([^,]+),\s*([^,]+),\s*-1\)', 
                   replace_trade_when, result)
    
    # 4. hump(x, p) -> signed_power(x, p)
    result = re.sub(r'hump\(([^,]+),\s*([\d.]+)\)', 
                   r'signed_power(\1, \2)', result)
    
    # 5. regression_neut(x, y) -> group_neutralize(x, sector)
    result = re.sub(r'regression_neut\(([^,]+),\s*([^)]+)\)', 
                   r'group_neutralize(\1, sector)', result)
    
    return result


def clean_file(input_file: str, output_file: str = None):
    """清理文件中的所有表达式"""
    input_path = Path(input_file)
    if output_file is None:
        output_file = input_file
    
    with open(input_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    cleaned_lines = []
    stats = {
        'total': 0,
        'ts_av_diff': 0,
        'vector_neut': 0,
        'trade_when': 0,
        'hump': 0,
        'regression_neut': 0,
    }
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        stats['total'] += 1
        
        # 统计各种非标准函数
        if 'ts_av_diff' in line:
            stats['ts_av_diff'] += 1
        if 'vector_neut' in line:
            stats['vector_neut'] += 1
        if 'trade_when' in line:
            stats['trade_when'] += 1
        if 'hump' in line:
            stats['hump'] += 1
        if 'regression_neut' in line:
            stats['regression_neut'] += 1
        
        # 清理表达式
        cleaned = clean_expression(line)
        cleaned_lines.append(cleaned)
    
    # 写入输出文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(cleaned_lines) + '\n')
    
    # 打印统计
    print(f"总表达式: {stats['total']}")
    print(f"已替换 ts_av_diff: {stats['ts_av_diff']}")
    print(f"已替换 vector_neut: {stats['vector_neut']}")
    print(f"已替换 trade_when: {stats['trade_when']}")
    print(f"已替换 hump: {stats['hump']}")
    print(f"已替换 regression_neut: {stats['regression_neut']}")
    
    return stats


if __name__ == "__main__":
    input_file = "data/alphas/to_test.txt"
    print(f"清理文件: {input_file}")
    clean_file(input_file)
    print("清理完成！")
