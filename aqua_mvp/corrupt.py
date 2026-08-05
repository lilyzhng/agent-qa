"""Corrupt the curated GT labels to simulate the SLIFF failure mode (design 3.1.4).

GT lives in ../traffic_signs/clean/eval_set_100.json and is NEVER read by the agent.
Every instance is relabeled as `other_sign`, which is exactly the real-world
failure mode: speed limits filed under the catch-all class.

Output: data/corrupted_labels.json (the only label store the agent may load).
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
GT_PATH = os.path.join(HERE, "..", "traffic_signs", "clean", "eval_set_100.json")
OUT_PATH = os.path.join(HERE, "data", "corrupted_labels.json")

def main():
    gt = json.load(open(GT_PATH))
    corrupted = []
    for rec in gt:
        corrupted.append({
            "id": rec["id"],
            "image": rec["image"],
            "bbox_id": rec["bbox_id"],
            "label": "other_sign",  # the corruption: everything lands in the catch-all
        })
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    json.dump(corrupted, open(OUT_PATH, "w"), indent=1)
    print(f"corrupted {len(corrupted)} labels -> {OUT_PATH}")
    print("GT stays at", GT_PATH, "(agent must not read this)")

if __name__ == "__main__":
    main()
