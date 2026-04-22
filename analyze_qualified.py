import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def parse_alpha_line(line):
    """解析带参数的表达式行"""
    parts = line.strip().split('|')
    if len(parts) >= 5:
        return {
            'expression': parts[0],
            'universe': parts[1],
            'decay': parts[2],
            'neutralization': parts[3],
            'truncation': parts[4],
            'sharpe': float(parts[5]) if len(parts) > 5 else 0.0,
            'fitness': float(parts[6]) if len(parts) > 6 else 0.0,
            'turnover': float(parts[7]) if len(parts) > 7 else 0.0,
        }
    elif len(parts) == 1:
        return {'expression': parts[0]}
    return None

# 从文件读取（支持带参数格式）
alphas = []
with open('data/alphas/to_test_v4_fixed.txt', 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line and '|' in line:
            a = parse_alpha_line(line)
            if a:
                alphas.append(a)

print(f'读取到 {len(alphas)} 个 Alpha')
print()

categories = {
    'ts_rank_std_dev': [],
    'volatility_spread': [],
    'momentum': [],
    'mean_reversion': [],
    'corr_pattern': [],
    'regression': [],
    'other': []
}

for a in alphas:
    expr = a['expression']
    if 'group_rank(ts_rank(' in expr and 'ts_std_dev(' in expr:
        categories['ts_rank_std_dev'].append(a)
    elif 'ts_std_dev(close' in expr and ('-' in expr or '/' in expr):
        categories['volatility_spread'].append(a)
    elif 'ts_sum(returns' in expr or 'ts_mean(returns' in expr:
        categories['momentum'].append(a)
    elif 'ts_mean(' in expr and 'close' in expr and '-' in expr:
        categories['mean_reversion'].append(a)
    elif 'ts_corr(' in expr:
        categories['corr_pattern'].append(a)
    elif 'ts_regression(' in expr:
        categories['regression'].append(a)
    else:
        categories['other'].append(a)

for cat, items in categories.items():
    print(f'{cat}: {len(items)}')
    for a in items[:5]:
        expr = a['expression'][:80]
        s = a.get('sharpe', 0)
        fi = a.get('fitness', 0)
        to = a.get('turnover', 0)
        print(f'  S={s:.2f} F={fi:.2f} T={to:.4f} | {expr}')
    if len(items) > 5:
        print(f'  ... +{len(items)-5} more')
    print()

# 按模板类型统计
print('=' * 60)
print('模板类型统计')
print('=' * 60)
for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
    print(f'{cat}: {len(items)}')
