import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, '.')
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from pathlib import Path
import os, time, json

load_dotenv(Path('.env'))
BASE_URL = "https://api.worldquantbrain.com"
email = os.getenv("BRAIN_EMAIL", "") or os.getenv("WQ_USERNAME", "")
password = os.getenv("BRAIN_PASSWORD", "") or os.getenv("WQ_PASSWORD", "")

s = requests.Session()
s.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Origin": "https://platform.worldquantbrain.com",
    "Referer": "https://platform.worldquantbrain.com/",
    "Accept": "application/json;version=2.0",
    "Content-Type": "application/json"
})

r = s.post(BASE_URL + "/authentication", auth=HTTPBasicAuth(email, password), timeout=30)
print(f"Auth: {r.status_code}")

# Fetch all pages
all_qualified = []
total_fetched = 0
offset = 0
limit = 100

while True:
    r2 = s.get(
        BASE_URL + "/users/self/alphas",
        params={"limit": limit, "offset": offset, "order": "-is.fitness"},
        timeout=30
    )
    
    if r2.status_code != 200:
        print(f"HTTP {r2.status_code} at offset {offset}")
        break
    
    data = r2.json()
    results = data.get("results", [])
    total_count = data.get("count", 0)
    total_fetched += len(results)
    
    for a in results:
        is_d = a.get("is") or {}
        sh = is_d.get("sharpe", 0) or 0
        fi = is_d.get("fitness", 0) or 0
        to = is_d.get("turnover", 0) or 0
        re = is_d.get("returns", 0) or 0
        
        if sh >= 1.25 and fi >= 1.0:
            expr = a.get("regular", {}).get("code", a.get("code", a.get("expression", "")))
            all_qualified.append({
                "id": a.get("id", ""),
                "expression": expr,
                "sharpe": round(sh, 4),
                "fitness": round(fi, 4),
                "turnover": round(to, 4),
                "returns": round(re, 4),
                "grade": a.get("grade", ""),
                "settings": a.get("settings", {}),
            })
    
    if not results or total_fetched >= total_count:
        break
    
    offset += limit
    time.sleep(0.2)

# Sort and save
all_qualified.sort(key=lambda x: -x["fitness"])

os.makedirs("data/alphas", exist_ok=True)
with open("data/alphas/qualified_alphas.json", "w", encoding="utf-8") as f:
    json.dump(all_qualified, f, ensure_ascii=False, indent=2)
with open("data/alphas/qualified_expressions.txt", "w", encoding="utf-8") as f:
    for q in all_qualified:
        s2 = q.get("settings", {})
        univ = s2.get("universe", "TOP3000")
        delay = s2.get("delay", 1)
        neut = s2.get("neutralization", "MARKET")
        trunc = s2.get("truncation", 0.08)
        f.write(q["expression"] + "|" + str(univ) + "|" + str(delay) + "|" + str(neut) + "|" + str(trunc) + "\n")

print(f"Total fetched: {total_fetched}")
print(f"QUALIFIED (Sharpe>=1.25, Fitness>=1.0): {len(all_qualified)}")

for i, q in enumerate(all_qualified, 1):
    print(f"  {i:3d}. S={q['sharpe']:.2f} F={q['fitness']:.2f} T={q['turnover']:.4f} | {q['expression'][:80]}")

# Stats
grades = {}
for q in all_qualified:
    g = q.get("grade", "NONE") or "NONE"
    grades[g] = grades.get(g, 0) + 1
print(f"\nGrades: {grades}")
