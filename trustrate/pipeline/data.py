"""Public-style import and deterministic synthetic review/attack data."""
from __future__ import annotations
import csv, json, random
from pathlib import Path

def synthetic_reviews(n_genuine=240, n_attack=80, seed=42):
    rng=random.Random(seed); rows=[]
    phrases=["Clear sound and comfortable fit.","Battery lasts all day.","Great value, would recommend.","Noise cancelling is impressive."]
    for i in range(n_genuine):
        rows.append(dict(id=i, user=f"user{i}", rating=rng.choice([3,4,4,5]), body=rng.choice(phrases), ip=f"192.0.2.{i%80+1}", ua="Safari", timestamp=i*97, label=0))
    attack="Amazing product! Best sound ever! Highly recommend this amazing product!"
    for i in range(n_attack):
        rows.append(dict(id=n_genuine+i,user=f"bot{i}",rating=5,body=attack,ip=f"198.51.100.{i%5+1}",ua="HeadlessChrome/1.0",timestamp=10000+i*3,label=1))
    return rows

def write_jsonl(rows, path):
    with open(path,"w",encoding="utf8") as f:
        for row in rows: f.write(json.dumps(row)+"\n")

def load_reviews(path):
    p=Path(path)
    if p.suffix.lower()=='.csv':
        with p.open(newline='',encoding='utf8') as f: return [{**r,'label':int(r.get('label',0))} for r in csv.DictReader(f)]
    with p.open(encoding='utf8') as f: return [json.loads(x) for x in f if x.strip()]
