# -*- coding: utf-8 -*-
"""检查表达式中是否有无效的变量

基于 WorldQuant Brain API 官方数据集验证
参考: data/api_valid_variables.py
"""
import re

# ✅ 有效的 WorldQuant Brain API 变量
VALID_VARS = {
    # 价格变量 (pv1 数据集)
    'close', 'open', 'high', 'low', 'vwap', 'volume', 'cap',
    # 收益率 (pv1 数据集)
    'returns',
    # 财务变量 (fundamental6 数据集)
    'assets', 'liabilities', 'revenue', 'netincome', 'cash', 'debt', 'equity', 'eps',
    'pe_ratio', 'pb_ratio', 'market_cap', 'dividend_yield',
    # 分析师预测 (analyst4 数据集)
    'anl4_tbvps_low', 'anl4_tbvps_high', 'anl4_tbvps_mean', 'anl4_tbvps_median',
    # 分组变量
    'sector', 'industry', 'subindustry',
    # 数字和希腊字母（用于公式）
    'a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm',
    'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z',
    # 数学常数
    'pi', 'e',
}

# ⚠️ 无效变量 (会报 unknown variable 错误)
INVALID_VARS = {
    'vwp',              # 用 vwap 替代
    'adv', 'adv5', 'adv10', 'adv20',  # 用 ts_mean(volume, N) 替代
    'turnover',         # 用 volume/cap 替代
    'bid', 'ask',       # 部分数据集不支持
    'bidsize', 'asksize',
    'ret_20d', 'ret_60d', 'ret_120d', 'ret_252d',  # 用 ts_delta(close, N)/close 替代
    'rel_ret_all', 'rel_ret_industry', 'rel_ret_sector',
    'fcf', 'ebit', 'net_income', 'gross_profit',  # 未验证
    'ebitda', 'operating_income', 'total_revenue', 'book_value', 'retained_earnings',
    'est_eps', 'ebit_margin', 'roe', 'roa',
    'implied_volatility', 'iv_call', 'iv_put',
    'pcr_oi', 'pcr_volume',
    'scl12_buzz',
}


def check_expression(expr: str) -> list:
    """检查表达式中的无效变量

    Returns:
        list: 无效变量列表
    """
    # 提取函数调用中的变量
    func_vars = re.findall(r'(?:ts_\w+|group_\w+|rank|delay|log|abs|sign|decay_linear)\s*\(([^)]+)\)', expr)
    found_vars = set()

    for fv in func_vars:
        # 分割参数
        parts = re.split(r'[\+\-\*\/\,\s\(\)]+', fv)
        for p in parts:
            p = p.strip()
            if p and not p.isdigit() and not re.match(r'^[<>]=?', p):
                found_vars.add(p)

    # 也提取顶层变量
    tokens = re.findall(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b', expr)
    found_vars.update(tokens)

    # 过滤掉函数名
    functions = {'ts', 'group', 'rank', 'delay', 'log', 'abs', 'sign', 'mean', 'sum',
                 'std', 'dev', 'delta', 'corr', 'cov', 'rank', 'scale', 'zscore',
                 'decay', 'linear', 'min', 'max', 'sign', 'power', 'sqrt', 'fill',
                 'group_rank', 'group_neutralize', 'group_mean', 'group_sum',
                 'ts_rank', 'ts_mean', 'ts_sum', 'ts_std_dev', 'ts_delta',
                 'ts_corr', 'ts_cov', 'ts_zscore', 'ts_decay_linear', 'ts_delay',
                 'ts_max', 'ts_min', 'ts_product', 'ts_argmax', 'ts_argmin',
                 'trade_when', 'neutralize', 'regression_neut', 'vector_neut',
                 'hump', 'signed_power', 'bucket', 'cap', 'sector', 'industry',
                 'subindustry', 'returns', 'close', 'open', 'high', 'low', 'vwap',
                 'volume', 'and', 'or', 'not', 'if', 'else', 'true', 'false'}
    found_vars = {v for v in found_vars if v not in functions}

    # 检查无效变量
    return sorted(found_vars & INVALID_VARS)


def main():
    """检查 to_test.txt 中的无效变量"""
    with open(r'd:/python_repo/worldquant-autocommit-alpha-master/data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
        lines = f.readlines()

    invalid_count = 0
    invalid_examples = {}

    for i, line in enumerate(lines, 1):
        expr = line.strip().split('|')[0]
        if not expr or expr.startswith('#'):
            continue

        invalid_vars = check_expression(expr)
        if invalid_vars:
            invalid_count += 1
            for v in invalid_vars:
                if v not in invalid_examples:
                    invalid_examples[v] = (expr[:60], i)

    print(f"检查文件: data/alphas/to_test.txt")
    print(f"总行数: {len(lines)}")
    print(f"包含无效变量的行数: {invalid_count}")
    print()

    if invalid_examples:
        print("发现无效变量:")
        for var, (expr, line_num) in sorted(invalid_examples.items()):
            print(f"  [{var}] 行 {line_num}: {expr}...")
    else:
        print("✅ 未发现无效变量")


if __name__ == "__main__":
    main()
