import sys, io, json, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

with open('data/alphas/qualified_alphas.json', 'r', encoding='utf-8') as f:
    alphas = json.load(f)

print(f"Total: {len(alphas)}")
print()

# Print all 94 with full expressions
for i, a in enumerate(alphas, 1):
    aid = a.get('id', '')
    expr = a.get('expression', '')
    sh = a.get('sharpe', 0)
    fi = a.get('fitness', 0)
    to = a.get('turnover', 0)
    gr = a.get('grade', '')
    st = a.get('status', '')
    settings = a.get('settings', {})
    univ = settings.get('universe', '?')
    delay = settings.get('delay', '?')
    neut = settings.get('neutralization', '?')
    decay = settings.get('decay', '?')
    trunc = settings.get('truncation', '?')
    print(f"{i:3d}. [{aid}] S={sh:.2f} F={fi:.2f} T={to:.4f} {gr}")
    print(f"     {expr}")
    print(f"     U={univ} D={delay} N={neut} Dec={decay} Tr={trunc}")
    print()
