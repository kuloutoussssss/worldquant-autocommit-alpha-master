# -*- coding: utf-8 -*-
"""清理 evcf_optimized.txt 并插入到 to_test.txt 开头"""

# 读取并清理
with open('data/alphas/evcf_optimized.txt', 'r', encoding='utf-8') as f:
    lines = [l.strip() for l in f if l.strip()]

seen = set()
clean = []
for line in lines:
    # 跳过残缺行
    if line.startswith('52))'):
        continue
    # 跳过重复行
    if line in seen:
        continue
    seen.add(line)
    clean.append(line)

print(f'清理后 EVCF: {len(clean)} 条 (原始 {len(lines)} 条)')

# 读取现有
with open('data/alphas/to_test.txt', 'r', encoding='utf-8') as f:
    existing = f.read()

existing_count = len([l for l in existing.strip().split('\n') if l.strip()])
print(f'现有 to_test.txt: {existing_count} 条')

# 写入：clean + 现有
combined = '\n'.join(clean) + '\n' + existing
with open('data/alphas/to_test.txt', 'w', encoding='utf-8') as f:
    f.write(combined)

total = len([l for l in combined.strip().split('\n') if l.strip()])
print(f'写入完成，总计: {total} 条')
