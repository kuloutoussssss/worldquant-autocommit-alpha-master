# -*- coding: utf-8 -*-
"""
Alpha 合并去重与验证脚本
1. 合并三个版本的 Alpha
2. 按表达式去重
3. 验证表达式语法正确性
4. 保存到 to_test_max.txt
"""

import re
from pathlib import Path
import json
from datetime import datetime
import sys

# 设置控制台编码
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# Alpha 文件路径
ALPHA_FILES = [
    "data/alphas/to_test_max.txt",       # 原始 Max (12,878)
    "data/alphas/to_test_v2_max.txt",    # V2 Max (47,520)
    "data/alphas/to_test_v3_max.txt",     # V3 Max (30,614)
]

# 已验证有效的函数
VALID_NUMERIC_FUNCS = [
    "rank", "ts_rank", "ts_mean", "ts_sum", "ts_zscore",
    "ts_corr", "ts_av_diff", "ts_decay", "delay",
    "decay_linear", "log", "abs", "sign", "delta", "sum",
    "group_rank", "ts_product", "ts_max", "ts_min"
]

# 已验证有效的字段
VALID_FIELDS = set([
    # 财务字段
    "revenue", "sales", "assets", "equity", "debt", "cash",
    "ebitda", "ebit", "net_income", "gross_profit",
    "operating_income", "total_revenue", "book_value", 
    "retained_earnings", "free_cash_flow", "eps", "est_eps",
    # 价格/市场字段
    "close", "open", "high", "low", "vwap", "volume",
    "returns", "cap",
    # 分组字段
    "sector", "subindustry", "industry",
])


def parse_alpha_line(line):
    """解析 Alpha 行"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    
    parts = line.split("|")
    if len(parts) < 1:
        return None
    
    return {
        "expression": parts[0].strip(),
        "universe": parts[1].strip() if len(parts) > 1 else "TOP3000",
        "decay": parts[2].strip() if len(parts) > 2 else "30",
        "neutralization": parts[3].strip() if len(parts) > 3 else "SECTOR",
        "truncation": parts[4].strip() if len(parts) > 4 else "0.08"
    }


def validate_expression(expr):
    """
    验证 Alpha 表达式是否正确
    返回: (is_valid, error_msg)
    """
    if not expr or len(expr) < 5:
        return False, "Expression too short"
    
    # 检查括号匹配
    open_count = expr.count("(")
    close_count = expr.count(")")
    if open_count != close_count:
        return False, f"Unbalanced parentheses: ( {open_count} vs ) {close_count}"
    
    # 检查是否有非法字符(只允许字母、数字、运算符、括号、点、空格、逗号)
    illegal_chars = re.findall(r'[^a-zA-Z0-9_\+\-\*\/\(\)\.\s\,\?\:\>\<]', expr)
    if illegal_chars:
        return False, f"Illegal characters: {illegal_chars[:3]}"
    
    # 检查是否有连续运算符
    if re.search(r'[\+\-\*\/]{2,}', expr):
        return False, "Consecutive operators"
    
    # 检查是否以运算符开头或结尾
    if re.match(r'^[\+\*\/]', expr) or re.search(r'[\+\-\*\/]$', expr):
        return False, "Starts/ends with operator"
    
    # 检查 ts_* 函数格式
    ts_funcs = re.findall(r'(ts_\w+)\(', expr)
    for func in ts_funcs:
        if func not in VALID_NUMERIC_FUNCS:
            return False, f"Unknown function: {func}"
    
    # 检查字段(提取单词,排除函数名和数字)
    words = re.findall(r'\b([a-z_][a-z_0-9]*)\b', expr, re.IGNORECASE)
    unknown_count = 0
    for word in words:
        if (word not in VALID_FIELDS and 
            not word.startswith("ts_") and 
            word not in ["and", "or", "not", "if", "else", "true", "false"]):
            # 检查是否是数字
            if not word.replace(".", "").replace("-", "").isdigit():
                unknown_count += 1
    
    # 允许少量未知字段(可能有新字段)
    if unknown_count > 15:
        return False, f"Too many unknown fields: {unknown_count}"
    
    return True, "OK"


def merge_and_deduplicate(files):
    """合并并去重"""
    print("=" * 60)
    print("Alpha Merge & Deduplicate Script")
    print("=" * 60)
    print()
    
    all_alphas = []
    seen_expressions = {}
    stats = {"valid": 0, "invalid": 0, "duplicate": 0, "read": 0}
    
    for filepath in files:
        path = Path(filepath)
        if not path.exists():
            print(f"[WARN] File not found: {filepath}")
            continue
        
        file_count = 0
        print(f"\n[READ] {filepath}")
        
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                alpha = parse_alpha_line(line)
                if not alpha:
                    continue
                
                expr = alpha["expression"]
                file_count += 1
                stats["read"] += 1
                
                # 验证表达式
                is_valid, msg = validate_expression(expr)
                if not is_valid:
                    stats["invalid"] += 1
                    continue
                
                stats["valid"] += 1
                
                # 去重(保留第一个出现的)
                if expr not in seen_expressions:
                    seen_expressions[expr] = alpha
                    all_alphas.append(alpha)
                else:
                    stats["duplicate"] += 1
        
        print(f"   -> {file_count} lines read")
    
    return all_alphas, stats


def save_alphas(alphas, filepath):
    """保存 Alpha 到文件"""
    Path(filepath).parent.mkdir(parents=True, exist_ok=True)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("# Alpha Expressions - Merged & Deduplicated\n")
        f.write(f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total: {len(alphas)} alphas\n")
        f.write("# Format: expression|universe|decay|neutralization|truncation\n")
        f.write("#" + "=" * 60 + "\n")
        
        for alpha in alphas:
            line = (f"{alpha['expression']}|{alpha['universe']}|{alpha['decay']}|"
                   f"{alpha['neutralization']}|{alpha['truncation']}\n")
            f.write(line)
    
    return filepath


def show_sample(alphas, count=10):
    """显示示例"""
    print(f"\n[SAMPLE] First {count} expressions:")
    for i, alpha in enumerate(alphas[:count], 1):
        expr = alpha["expression"]
        display = expr[:70] + ('...' if len(expr) > 70 else '')
        print(f"   {i:2}. {display}")


def main():
    print("Starting merge and deduplication...")
    print()
    
    # 合并去重
    all_alphas, stats = merge_and_deduplicate(ALPHA_FILES)
    
    # 统计
    print("\n" + "=" * 60)
    print("[STATISTICS]")
    print("=" * 60)
    print(f"   Total read:     {stats['read']:,}")
    print(f"   Valid:          {stats['valid']:,} [OK]")
    print(f"   Invalid:        {stats['invalid']:,} [SKIP]")
    print(f"   Duplicates:     {stats['duplicate']:,} [REMOVED]")
    print(f"   Final unique:   {len(all_alphas):,} [TOTAL]")
    
    # 按表达式长度和类型分类
    type_counts = {
        "group_rank": 0,
        "ts_rank": 0,
        "ts_mean/sum": 0,
        "ts_zscore": 0,
        "ts_decay": 0,
        "other": 0
    }
    
    for alpha in all_alphas:
        expr = alpha["expression"]
        if "group_rank" in expr:
            type_counts["group_rank"] += 1
        elif "ts_rank" in expr:
            type_counts["ts_rank"] += 1
        elif "ts_zscore" in expr:
            type_counts["ts_zscore"] += 1
        elif "ts_mean" in expr or "ts_sum" in expr:
            type_counts["ts_mean/sum"] += 1
        elif "ts_decay" in expr:
            type_counts["ts_decay"] += 1
        else:
            type_counts["other"] += 1
    
    print("\n[TYPE DISTRIBUTION]")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = count / len(all_alphas) * 100 if all_alphas else 0
        bar = "#" * int(pct / 5)
        print(f"   {t:15} {count:6,} ({pct:5.1f}%) {bar}")
    
    # 保存
    output_file = "data/alphas/to_test_max.txt"
    save_alphas(all_alphas, output_file)
    
    # 示例
    show_sample(all_alphas)
    
    print("\n" + "=" * 60)
    print(f"[DONE] Saved {len(all_alphas):,} unique alphas")
    print(f"       File: {output_file}")
    print("=" * 60)
    
    return all_alphas


if __name__ == "__main__":
    main()
