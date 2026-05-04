"""
WorldQuant Alpha 变体生成器
基于 E1 基准表达式生成 2000 个变体，写入 to_test.txt 开头
"""

import random
import itertools

# ═══════════════════════════════════════════════════════
# 1. 字段维度（10 类 × price 组合 = 大量变体）
# ═══════════════════════════════════════════════════════

# 分子：财务因子
fundamentals = [
    "ebit",
    "ebitda",
    "operating_income",
    "net_profit_growth",      # 净利润增速
    "fnd6_pe_ratio",          # P/E
    "fnd6_pb_ratio",          # P/B
    "fnd6_ps_ratio",          # P/S
    "fnd6_pc_ratio",          # P/CF
    "fnd6_dividend_yield",     # 股息率
    "roe",
    "roa",
    "gross_margin",           # 毛利率
    "net_margin",             # 净利率
    "asset_turnover",        # 资产周转率
    "debt_to_equity",        # 资产负债率
    "quick_ratio",           # 速动比率
    "current_ratio",         # 流动比率
    "revenue_growth",        # 营收增速
    "anl4_eps_high",         # EPS 高
    "anl4_eps_median",       # EPS 中
    "fn_netprofit",          # 净利润
    "fn_opeprofit",          # 营业利润
    "fn_totass",             # 总资产
    "fn_cps",                # 每股现金流
    "fn_ev_ebitda",          # EV/EBITDA
    "fnd6_peg_ratio",        # PEG
    "fnd6_ncf_chg",          # 经营现金流变化
    "fnd6_roe_high",         # ROE 高
    "fnd6_roe_median",       # ROE 中
]

# 分母：价格/规模字段
denominators = [
    "open",
    "close",
    "vwap",
    "high",
    "low",
    "cap",
    "sharesout",
    "volume",
]

# ═══════════════════════════════════════════════════════
# 2. ts_rank/ts_zscore 窗口
# ═══════════════════════════════════════════════════════

windows = [20, 30, 40, 60, 90, 120, 180, 252]

# ═══════════════════════════════════════════════════════
# 3. group_rank 的分组
# ═══════════════════════════════════════════════════════

groups = ["sector", "subindustry", "industry"]

# ═══════════════════════════════════════════════════════
# 4. Decay 参数
# ═══════════════════════════════════════════════════════

decays = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60]

# ═══════════════════════════════════════════════════════
# 5. Neutralization
# ═══════════════════════════════════════════════════════

neutralizations = ["sector", "subindustry", "industry", "market"]

# ═══════════════════════════════════════════════════════
# 6. Truncation
# ═══════════════════════════════════════════════════════

truncations = [0.05, 0.06, 0.07, 0.08, 0.10, 0.12]

# ═══════════════════════════════════════════════════════
# 7. 表达式结构模板（8 种）
# ═══════════════════════════════════════════════════════

def make_expr(fund, denom, window, struct_type):
    """生成 8 种不同结构的表达式"""

    inner = f"ts_rank({fund}/{denom}, {window})"

    if struct_type == 0:
        # 原始模板：group_rank(ts_rank(f/d, N), group)
        return f"group_rank({inner}, sector)"

    elif struct_type == 1:
        # group_rank + 纯中性化
        return f"group_rank({inner}, subindustry)"

    elif struct_type == 2:
        # group_rank + industry
        return f"group_rank({inner}, industry)"

    elif struct_type == 3:
        # 双中性化：group_neutralize(..., bucket(cap))
        return f"group_neutralize(group_rank({inner}, sector), bucket(rank(cap), range=\"0.1,1,0.1\"))"

    elif struct_type == 4:
        # 双中性化 subindustry
        return f"group_neutralize(group_rank({inner}, subindustry), bucket(rank(cap), range=\"0.1,1,0.1\"))"

    elif struct_type == 5:
        # 双中性化 industry
        return f"group_neutralize(group_rank({inner}, industry), bucket(rank(cap), range=\"0.1,1,0.1\"))"

    elif struct_type == 6:
        # ts_zscore 代替 ts_rank
        zscore_inner = f"ts_zscore({fund}/{denom}, {window})"
        return f"group_rank({zscore_inner}, sector)"

    elif struct_type == 7:
        # ts_av_diff：变化率信号
        avdiff_inner = f"ts_av_diff({fund}/{denom}, {window})"
        return f"group_rank({avdiff_inner}, sector)"

# ═══════════════════════════════════════════════════════
# 8. 组合因子：盈利因子 + 量价因子
# ═══════════════════════════════════════════════════════

def make_combined_expr(fund, denom, window, weight):
    """双信号组合：盈利 + 动量"""
    # 盈利信号
    profit_signal = f"ts_rank({fund}/{denom}, {window})"
    # 动量信号（不同窗口）
    mom_window = min(window // 2, 20) if window >= 20 else 10
    mom_signal = f"ts_rank(returns, {mom_window})"
    # 加权组合
    if weight == 0.7:
        combined = f"{weight}*{profit_signal}+{1-weight}*{mom_signal}"
    elif weight == 0.8:
        combined = f"{weight}*{profit_signal}+{1-weight}*{mom_signal}"
    else:
        combined = f"0.6*{profit_signal}+0.4*{mom_signal}"
    return f"group_neutralize(group_rank({combined}, sector), bucket(rank(cap), range=\"0.1,1,0.1\"))"

# ═══════════════════════════════════════════════════════
# 9. ts_rank 内部窗口 + 外部中性化组合
# ═══════════════════════════════════════════════════════

def make_multi_window_expr(fund, denom):
    """多窗口平均：减少噪声"""
    w1, w2 = 30, 60
    inner = f"ts_rank(({fund}/{denom} + ts_zscore({fund}/{denom}, {w1}))/2, {w2})"
    return f"group_neutralize(group_rank({inner}, sector), bucket(rank(cap), range=\"0.1,1,0.1\"))"

# ═══════════════════════════════════════════════════════
# 10. 生成变体
# ═══════════════════════════════════════════════════════

variants = []

# —— 基础变体：fund/denom × window × group × struct = 大量变体 ——
for fund, denom in itertools.product(fundamentals, denominators):
    for window in [20, 30, 40, 60, 90, 120, 180]:
        for struct in [0, 1, 2, 3, 4, 5]:
            expr = make_expr(fund, denom, window, struct)
            variants.append(expr)
            if len(variants) >= 1600:
                break
        if len(variants) >= 1600:
            break
    if len(variants) >= 1600:
        break

# —— 特殊结构：ts_zscore 和 ts_av_diff 变体（补充 ~200 条）——
count_before = len(variants)
for fund, denom in itertools.product(fundamentals[:10], denominators[:5]):
    for window in [20, 40, 60, 90]:
        expr = make_expr(fund, denom, window, 6)  # ts_zscore
        variants.append(expr)
        if len(variants) >= count_before + 100:
            break
        expr2 = make_expr(fund, denom, window, 7)  # ts_av_diff
        variants.append(expr2)
        if len(variants) >= count_before + 200:
            break
    if len(variants) >= count_before + 200:
        break

# —— 双信号组合（盈利+动量）~100 条 ——
count_before = len(variants)
for fund, denom in itertools.product(fundamentals[:10], denominators[:5]):
    for window in [30, 60, 90, 120]:
        for weight in [0.7, 0.8, 0.6]:
            expr = make_combined_expr(fund, denom, window, weight)
            variants.append(expr)
            if len(variants) >= count_before + 100:
                break
    if len(variants) >= count_before + 100:
        break

# —— 多窗口平均 ~50 条 ——
count_before = len(variants)
for fund, denom in itertools.product(fundamentals[:8], denominators[:5]):
    expr = make_multi_window_expr(fund, denom)
    variants.append(expr)
    if len(variants) >= count_before + 50:
        break

print('Total variants generated: %d' % len(variants))

# ═══════════════════════════════════════════════════════
# 11. 生成完整测试行（表达式 + 管道参数）
# ═══════════════════════════════════════════════════════

# 管道参数矩阵（Decay × Neutralization × Truncation）
param_combos = []
for decay in decays:
    for neut in neutralizations:
        for trunc in truncations:
            param_combos.append((decay, neut, trunc))

random.seed(42)
random.shuffle(variants)

lines = []
for i, expr in enumerate(variants):
    decay, neut, trunc = param_combos[i % len(param_combos)]
    line = f"{expr}|TOP3000|{decay}|{neut.upper()}|{trunc}"
    lines.append(line)

# 读取原有内容（本次只写新变体，替换旧内容）
try:
    with open("data/alphas/to_test.txt", "r", encoding="utf-8") as f:
        existing = f.read().strip().split("\n")
except:
    existing = []

# 写入：新变体在最前面（替换旧内容）
output_lines = lines + existing[:len(existing)]  # keep old entries after new ones
# 如果用户要完全覆盖（替换），用下面这行代替上面：
# output_lines = lines

with open("data/alphas/to_test.txt", "w", encoding="utf-8") as f:
    f.write("\n".join(output_lines))

print('[OK] Written %d NEW variants to to_test.txt' % len(lines))
print('     Total in file: %d lines' % len(output_lines))
print('\nFirst 5 examples:')
for line in lines[:5]:
    print('  ' + line[:120])

# 同时写入清单文件
with open("data/alphas/variant_manifest.txt", "w", encoding="utf-8") as f:
    f.write('# Variant manifest, %d entries\n' % len(lines))
    for i, line in enumerate(lines):
        f.write(f"{i+1}. {line}\n")

print('[*] Manifest written to variant_manifest.txt')
