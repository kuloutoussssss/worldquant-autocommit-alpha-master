# -*- coding: utf-8 -*-
import json

with open(r'd:/python_repo/worldquant-autocommit-alpha-master/data/alphas/generated_alphas_20260412_175834.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('Type:', type(data))
if isinstance(data, dict):
    print('Keys:', list(data.keys())[:10])
    if 'alphas' in data:
        print('Alphas count:', len(data['alphas']))
        if data['alphas']:
            print('First alpha:', str(data['alphas'][0])[:200])
elif isinstance(data, list):
    print('Count:', len(data))
    if data:
        print('First item:', str(data[0])[:200])
