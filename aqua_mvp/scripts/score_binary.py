"""Score a detector on BOTH binary tasks (is_speed_limit, is_numbered) per split."""
import importlib.util, json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GT_PATH = os.path.join(HERE, "..", "traffic_signs", "clean", "eval_set_100.json")


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0
    r = tp / (tp + fn) if tp + fn else 0
    f = 2 * p * r / (p + r) if p + r else 0
    return p, r, f


def main(detector_path, split):
    sys.path.insert(0, HERE)
    spec = importlib.util.spec_from_file_location("det", detector_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    gt = {r["id"]: r for r in json.load(open(GT_PATH))}
    ids = json.load(open(os.path.join(HERE, "data", f"{split}_ids.json")))

    stats = {k: [0, 0, 0, 0] for k in ("is_speed_limit", "is_numbered")}  # tp fp fn tn
    errors = []
    for i in ids:
        p = mod.detect(i)
        for k in stats:
            truth, guess = bool(gt[i][k]), bool(p[k])
            if truth and guess: stats[k][0] += 1
            elif not truth and guess: stats[k][1] += 1; errors.append((k, i, "FP"))
            elif truth: stats[k][2] += 1; errors.append((k, i, "FN"))
            else: stats[k][3] += 1
    print(f"split={split} n={len(ids)}")
    for k, (tp, fp, fn, tn) in stats.items():
        p, r, f = prf(tp, fp, fn)
        print(f"  {k:15s} TP={tp} FP={fp} FN={fn} TN={tn}  P={p:.3f} R={r:.3f} F1={f:.3f}")
    for e in sorted(errors):
        print("   ", e)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "dev")
