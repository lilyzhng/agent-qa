"""Score a detector function against GT on a given split.

A detector is a Python file with a top-level function:
    detect(item_id: int) -> dict
        {"is_speed_limit": bool, "fine_label": str}

The detector may read crop images from ../traffic_signs/review/crops/ and use
any local library. It must NOT read the GT file (it has no path to it anyway).
"""
import importlib.util
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
GT_PATH = os.path.join(HERE, "..", "traffic_signs", "clean", "eval_set_100.json")


def _gt_is_speed(rec):
    return rec["is_speed_limit"]


def _num(s):
    m = re.search(r"(\d+)", str(s))
    return m.group(1) if m else None


def load_detector(path):
    spec = importlib.util.spec_from_file_location("detector_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.detect


def score(detector_path, split="dev"):
    gt = {r["id"]: r for r in json.load(open(GT_PATH))}
    ids = json.load(open(os.path.join(HERE, "data", f"{split}_ids.json")))
    detect = load_detector(detector_path)

    tp = fp = fn = tn = 0
    label_ok = label_bad = 0
    errors = []
    for i in ids:
        g = gt[i]
        try:
            p = detect(i)
        except Exception as e:
            p = {"is_speed_limit": False, "fine_label": f"error:{e}"}
        truth = _gt_is_speed(g)
        guess = bool(p.get("is_speed_limit"))
        if truth and guess:
            tp += 1
            if _num(p.get("fine_label")) == _num(g["label"]):
                label_ok += 1
            else:
                label_bad += 1
                errors.append({"id": i, "gt": g.get("fine_label") or "?", "pred": p.get("fine_label"), "kind": "wrong_number"})
        elif not truth and guess:
            fp += 1
            errors.append({"id": i, "gt": "not_a_speed_limit", "pred": p.get("fine_label"), "kind": "FP"})
        elif truth and not guess:
            fn += 1
            errors.append({"id": i, "gt": g.get("fine_label") or "?", "pred": p.get("fine_label") or "missed", "kind": "FN"})
        else:
            tn += 1

    prec = tp / (tp + fp) if tp + fp else 0
    rec = tp / (tp + fn) if tp + fn else 0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0
    return {"split": split, "n": len(ids), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3),
            "number_accuracy": round(label_ok / tp, 3) if tp else 0,
            "errors": errors}


if __name__ == "__main__":
    import sys
    print(json.dumps(score(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "dev"), indent=1))
