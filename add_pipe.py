# -*- coding: utf-8 -*-
"""给没有管道参数的 alpha 行追加默认参数"""

INPUT = 'data/alphas/to_test.txt'
DEFAULT_PIPE = '|TOP3000|30|SECTOR|0.08'

with open(INPUT, 'r', encoding='utf-8') as f:
    lines = f.readlines()

added = 0
new_lines = []
for line in lines:
    stripped = line.strip()
    if not stripped:
        new_lines.append(line)
        continue
    # 已有管道参数的行（包含 |TOP 或 |1000 等）跳过
    if '|' in stripped and ('TOP' in stripped or '1000' in stripped or '500' in stripped or '3000' in stripped):
        new_lines.append(line)
        continue
    # 追加默认参数
    new_lines.append(stripped + DEFAULT_PIPE + '\n')
    added += 1

with open(INPUT, 'w', encoding='utf-8') as f:
    f.writelines(new_lines)

print(f'追加参数: {added} 行')
print(f'总计: {len([l for l in new_lines if l.strip()])} 行')
