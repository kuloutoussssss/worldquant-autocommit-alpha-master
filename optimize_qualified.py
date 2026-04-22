#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
176 个 qualified Alpha 优化方案
核心：去重选优 + 降相关改造 + 优先级排序
"""
import sys, io, json, re, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('data/alphas/qualified_alphas.json', 'r', encoding='utf-8') as f:
    alphas = json.load(f)

print(f"Total qualified alphas: {len(alphas)}")

# ====================================================================
# Step 1: 按"结构族"聚类 — 同族只留最优
# ====================================================================

# 族定义：
# A: trade_when(pcr_oi_* < *, IV_call - IV_put, -1) 
# B: group_rank(ts_rank(X/Y, N), G) - ts_std_dev(scl12_buzz, M)
# C: group_rank(ts_rank(X/Y, N), G)  [无buzz]
# D: -ts_std_dev(scl12_buzz, M)
# E: group_rank(fnd6_* / cap, subindustry)
# F: reverse(ts_std_dev(fn_*, M))
# G: rank(IV/parkinson)
# H: liabilities/assets
# I: trade_when(ts_rank(ts_std_dev(returns)...), anl4_*, -1)
# J: 其他

def classify(expr):
    if 'pcr_oi_' in expr and 'implied_volatility' in expr:
        # 提取 pcr_oi 窗口和 IV 结构
        m1 = re.search(r'pcr_oi_(\d+)', expr)
        m2 = re.search(r'implied_volatility_call_(\d+)-implied_volatility_put_(\d+)', expr)
        pcr_w = m1.group(1) if m1 else '?'
        iv_c = m2.group(1) if m2 else '?'
        iv_p = m2.group(2) if m2 else '?'
        return ('A', f'pcr{pcr_w}_IVc{iv_c}p{iv_p}')
    elif 'group_rank(ts_rank(' in expr and 'ts_std_dev(scl12_buzz' in expr:
        m = re.search(r'ts_rank\((\w+)/(\w+),\s*(\d+)\)', expr)
        if m:
            return ('B', f'{m.group(1)}/{m.group(2)}')
        return ('B', expr[:30])
    elif 'group_rank(ts_rank(' in expr and 'ts_std_dev(scl12_buzz' not in expr:
        m = re.search(r'ts_rank\((\w+)/(\w+),\s*(\d+)\)', expr)
        if m:
            return ('C', f'{m.group(1)}/{m.group(2)}')
        return ('C', expr[:30])
    elif expr.strip().startswith('-ts_std_dev(scl12_buzz'):
        return ('D', 'buzz_only')
    elif 'fnd6_' in expr:
        m = re.search(r'fnd6_(\w+)', expr)
        field = m.group(1) if m else '?'
        return ('E', f'fnd6_{field}')
    elif 'reverse(ts_std_dev(fn_' in expr:
        m = re.search(r'fn_(\w+)', expr)
        field = m.group(1) if m else '?'
        return ('F', f'fn_{field}')
    elif 'parkinson_volatility' in expr:
        return ('G', 'iv_parkinson')
    elif expr.strip() == 'liabilities/assets':
        return ('H', 'liab_assets')
    elif 'anl4_' in expr:
        return ('I', 'anl4_vol_filter')
    else:
        return ('J', expr[:30])

# 聚类
families = {}
for a in alphas:
    fam_type, fam_key = classify(a['expression'])
    full_key = f"{fam_type}:{fam_key}"
    if full_key not in families:
        families[full_key] = []
    families[full_key].append(a)

print(f"\n=== Step 1: 结构族聚类 ({len(families)} 个族) ===\n")

# 每族只保留 fitness 最高的
best_per_family = {}
for key, members in families.items():
    best = max(members, key=lambda x: x['fitness'])
    best_per_family[key] = best
    fam_type = key.split(':')[0]
    print(f"  {key}: {len(members)} 个 → 最优 S={best['sharpe']:.2f} F={best['fitness']:.2f} T={best['turnover']:.4f}")

print(f"\n去重后: {len(best_per_family)} 个")

# ====================================================================
# Step 2: 按自相关风险排序
# ====================================================================

# 风险评估：
# A族 (pcr_iv): 平台已有大量同类 → 自相关极高 → 最多留2个
# B族 (group_rank ts_rank - buzz): 同模板 → 自相关高 → 每族只留1个
# C族 (group_rank ts_rank): 可能比B族低相关
# D族 (buzz only): 太简单 → 必撞
# E族 (fnd6): 冷门 → 低相关 ✅
# F族 (fn IFRS): 极冷门 → 低相关 ✅
# G族 (IV/parkinson): 不太常见 → 中等
# H族 (liabilities): 简单但独特 → 低相关 ✅
# I族 (anl4): 条件过滤 → 低相关 ✅

risk_scores = {
    'A': 0.9,   # pcr_iv_skew — 高风险
    'B': 0.85,  # group_rank ts_rank - buzz — 高风险
    'C': 0.6,   # group_rank ts_rank 无buzz — 中等
    'D': 0.95,  # pure buzz — 必撞
    'E': 0.2,   # fnd6 — 冷门
    'F': 0.15,  # fn IFRS — 极冷门
    'G': 0.5,   # IV/parkinson — 中等
    'H': 0.25,  # liabilities — 低风险
    'I': 0.3,   # anl4 — 条件过滤
    'J': 0.4,   # 其他
}

# 排序：低风险 + 高fitness 优先
sorted_alphas = sorted(
    best_per_family.items(),
    key=lambda x: (-risk_scores.get(x[0].split(':')[0], 0.5), -x[1]['fitness'])
)

print(f"\n=== Step 2: 按自相关风险排序 (低风险优先) ===\n")

priority1_submit = []  # 直接提交
priority2_modify = []  # 需改造后提交
priority3_drop = []    # 放弃

for key, a in sorted_alphas:
    fam_type = key.split(':')[0]
    risk = risk_scores.get(fam_type, 0.5)
    
    if risk <= 0.3:
        priority1_submit.append(a)
        tag = "✅ 直接提交"
    elif risk <= 0.6:
        priority2_modify.append(a)
        tag = "🔧 改造后提交"
    else:
        priority3_drop.append(a)
        tag = "❌ 高风险"

print(f"  ✅ 直接提交: {len(priority1_submit)}")
print(f"  🔧 改造后提交: {len(priority2_modify)}")
print(f"  ❌ 高风险: {len(priority3_drop)}")

# ====================================================================
# Step 3: 生成改造版本
# ====================================================================

modified_alphas = []

for a in priority2_modify + priority3_drop:
    expr = a['expression']
    fam_type = classify(expr)[0]
    
    # B族: group_rank(ts_rank(X, N), G) - ts_std_dev(buzz, M)
    # 改造: 去掉buzz → 加 regression_neut
    if fam_type == 'B':
        m = re.search(r'group_rank\(ts_rank\((\w+)/(\w+),\s*(\d+)\),\s*(\w+)\)', expr)
        if m:
            x, y, w, g = m.group(1), m.group(2), m.group(3), m.group(4)
            base = f"group_rank(ts_rank({x}/{y}, {w}), {g})"
            # 变体1: 加regression_neut降cap暴露
            modified_alphas.append(f"regression_neut({base}, log(cap))")
            # 变体2: 换分组
            other_grps = [gp for gp in ['sector', 'industry', 'subindustry'] if gp != g]
            for og in other_grps:
                new_base = f"group_rank(ts_rank({x}/{y}, {w}), {og})"
                modified_alphas.append(f"regression_neut({new_base}, log(cap))")
            # 变体3: trade_when + 条件 (adv20 → ts_mean(volume, 20))
            modified_alphas.append(f"trade_when(volume > ts_mean(volume, 20), {base}, -1)")
            modified_alphas.append(f"trade_when(ts_std_dev(returns, 10) > ts_mean(ts_std_dev(returns, 20), 40), {base}, -1)")
            # 变体4: vector_neut (scl12_buzz → ts_zscore(volume, 20))
            modified_alphas.append(f"vector_neut({base}, ts_zscore(volume, 20))")

    # C族: group_rank(ts_rank(X, N), G) [无buzz]
    elif fam_type == 'C':
        m = re.search(r'group_rank\(ts_rank\((\w+)/(\w+),\s*(\d+)\),\s*(\w+)\)', expr)
        if m:
            x, y, w, g = m.group(1), m.group(2), m.group(3), m.group(4)
            base = f"group_rank(ts_rank({x}/{y}, {w}), {g})"
            modified_alphas.append(f"regression_neut({base}, log(cap))")
            modified_alphas.append(f"trade_when(volume > ts_mean(volume, 20), {base}, -1)")
    
    # A族: pcr_iv_skew
    elif fam_type == 'A':
        m = re.search(r'trade_when\(pcr_oi_(\d+)\s*<\s*([\d.]+),\s*\((implied_volatility_call_\d+-implied_volatility_put_\d+)\),\s*-1\)', expr)
        if m:
            pcr_w, pcr_t, iv_diff = m.group(1), m.group(2), m.group(3)
            base_signal = iv_diff
            # 改造1: 加group_neutralize
            modified_alphas.append(f"trade_when(pcr_oi_{pcr_w} < {pcr_t}, group_neutralize({base_signal}, sector), -1)")
            # 改造2: regression_neut with log(cap)
            modified_alphas.append(f"trade_when(pcr_oi_{pcr_w} < {pcr_t}, regression_neut({base_signal}, log(cap)), -1)")
            # 改造3: signed_power 非线性变换
            modified_alphas.append(f"trade_when(pcr_oi_{pcr_w} < {pcr_t}, signed_power({base_signal}, 0.5), -1)")
    
    # D族: pure buzz → 放弃，不改造
    # G族: IV/parkinson
    elif fam_type == 'G':
        modified_alphas.append(f"regression_neut({expr}, log(cap))")
        modified_alphas.append(f"group_neutralize({expr}, sector)")

# 去重
modified_unique = list(dict.fromkeys(modified_alphas))

print(f"\n=== Step 3: 改造版本 ===\n")
print(f"  原始需改造: {len(priority2_modify) + len(priority3_drop)}")
print(f"  生成改造版本: {len(modified_unique)}")

# ====================================================================
# Step 4: 输出最终方案
# ====================================================================

output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "alphas")
os.makedirs(output_dir, exist_ok=True)

# 方案1: 直接提交的 (低风险)
with open(os.path.join(output_dir, "submit_direct.txt"), "w", encoding="utf-8") as f:
    for a in sorted(priority1_submit, key=lambda x: -x['fitness']):
        s = a.get('settings', {})
        univ = s.get('universe', 'TOP3000')
        delay = s.get('delay', 1)
        neut = s.get('neutralization', 'MARKET')
        decay = s.get('decay', 4)
        trunc = s.get('truncation', 0.08)
        f.write(f"{a['expression']}|{univ}|{delay}|{neut}|{decay}|{trunc}\n")

# 方案2: 改造后测试的
with open(os.path.join(output_dir, "submit_modified.txt"), "w", encoding="utf-8") as f:
    for expr in modified_unique:
        f.write(f"{expr}|TOP3000|1|SUBINDUSTRY|30|0.08\n")

# 总结报告
print(f"\n{'='*70}")
print(f"  📋 最终方案")
print(f"{'='*70}")
print(f"\n  ✅ 直接提交 ({len(priority1_submit)} 个):")
for a in sorted(priority1_submit, key=lambda x: -x['fitness']):
    print(f"     S={a['sharpe']:.2f} F={a['fitness']:.2f} T={a['turnover']:.4f} | {a['expression'][:70]}")

print(f"\n  🔧 改造后测试 ({len(modified_unique)} 个):")
for expr in modified_unique[:10]:
    print(f"     {expr[:70]}")
if len(modified_unique) > 10:
    print(f"     ... +{len(modified_unique)-10} more")

print(f"\n  ❌ 放弃 ({len(priority3_drop)} 个高风险)")
print(f"     主要是 pcr_iv_skew ({sum(1 for a in priority3_drop if 'pcr_oi_' in a['expression'])}) 和 pure_buzz ({sum(1 for a in priority3_drop if '-ts_std_dev(scl12_buzz' in a['expression'])})")

print(f"\n  📁 文件:")
print(f"     data/alphas/submit_direct.txt — 直接提交列表")
print(f"     data/alphas/submit_modified.txt — 改造后测试列表")
