"""Score predictions against the hidden GT.

The agent never sees this file. Metrics:
  - detection: precision / recall / F1 on is_speed_limit
  - label accuracy: on true positives, did fine_label get the number right?
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
GT_PATH = os.path.join(HERE, "..", "traffic_signs", "clean", "eval_set_100.json")
PRED_PATH = os.path.join(HERE, "data", "predictions.json")


def gt_is_speed(rec):
    return rec["is_speed_limit"]


def num(s):
    m = re.search(r"(\d+)", str(s))
    return m.group(1) if m else None


def main():
    gt = {r["id"]: r for r in json.load(open(GT_PATH))}
    pred = {int(k): v for k, v in json.load(open(PRED_PATH)).items()}

    tp = fp = fn = tn = 0
    label_ok = label_bad = 0
    errors = []
    for i, g in gt.items():
        p = pred.get(i)
        truth = gt_is_speed(g)
        guess = bool(p and p["is_speed_limit"])
        if truth and guess:
            tp += 1
        elif not truth and guess:
            fp += 1
            errors.append((i, "not_a_speed_limit", "flagged", "FP"))
        elif truth and not guess:
            fn += 1
            errors.append((i, g.get("fine_label") or "not_a_speed_limit", "missed", "FN"))
        else:
            tn += 1

    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    num_acc = label_ok / tp if tp else 0

    print(f"evaluated {len(gt)} items (predictions: {len(pred)})")
    print(f"detection:  TP={tp} FP={fp} FN={fn} TN={tn}")
    print(f"precision={prec:.3f} recall={rec:.3f} f1={f1:.3f}")
    is_num = sum(1 for p_ in pred.values() if p_.get("is_numbered"))
    print(f"is_numbered=true on {is_num}/{len(pred)} predictions")
    print("\nerrors:")
    for e in errors:
        print(" ", e)

    res = {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
           "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
           "is_numbered_count": is_num,
           "errors": [{"id": i, "gt": g, "pred": p, "kind": k} for i, g, p, k in errors]}
    json.dump(res, open(os.path.join(HERE, "data", "last_eval.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
