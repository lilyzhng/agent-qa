"""Assign the 28 eval ids added after the 103-item split to dev/holdout (seeded, ~70/30)."""
import json, os, random

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
gt = json.load(open(os.path.join(HERE, "..", "traffic_signs", "clean", "eval_set_100.json")))
dev = json.load(open(os.path.join(HERE, "data", "dev_ids.json")))
hold = json.load(open(os.path.join(HERE, "data", "holdout_ids.json")))
new = sorted({r["id"] for r in gt} - set(dev) - set(hold))
rng = random.Random(20260727)
rng.shuffle(new)
cut = round(len(new) * 0.7)
dev += sorted(new[:cut]); hold += sorted(new[cut:])
json.dump(sorted(dev), open(os.path.join(HERE, "data", "dev_ids.json"), "w"))
json.dump(sorted(hold), open(os.path.join(HERE, "data", "holdout_ids.json"), "w"))
print(f"added {cut} to dev ({len(dev)}), {len(new)-cut} to holdout ({len(hold)})")
