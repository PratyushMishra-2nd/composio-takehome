"""Pick the human-verification sample: 2 apps per category, fixed seed (reproducible, not cherry-picked).
Writes data/gold_template.csv for a human to fill BLIND (without looking at agent output)."""
import csv, random
from collections import defaultdict
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
apps = list(csv.DictReader(open(ROOT / "data/apps.csv", encoding="utf-8")))
by = defaultdict(list)
for a in apps: by[a["category"]].append(a)
rng = random.Random(42)
sample = sorted((a for cat in by.values() for a in rng.sample(cat, 2)), key=lambda a: int(a["id"]))
cols = ["id", "app", "hint", "auth_methods", "access", "mcp_exists", "mcp_official", "verdict", "source_urls", "minutes", "notes"]
with open(ROOT / "data/gold_template.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for a in sample: w.writerow({"id": a["id"], "app": a["app"], "hint": a["hint"]})
print(", ".join(f"{a['id']} {a['app']}" for a in sample))
