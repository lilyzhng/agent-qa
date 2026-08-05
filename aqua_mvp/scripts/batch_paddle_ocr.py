"""Batch PaddleOCR over all eval crops -> data/paddle_cache.json.

Run with the paddle venv python (py3.13): .venv-paddle/bin/python.
Caches FULL text tokens + conf per crop (cheap_cv keeps only digits; the
detector needs words like SPEED/EXIT/WEST too). Incremental: skips ids
already in the cache.
"""
import json, os, sys, warnings
warnings.filterwarnings("ignore")

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROPS = os.path.join(HERE, "..", "traffic_signs", "review", "crops")
CACHE = os.path.join(HERE, "data", "paddle_cache.json")

gt = json.load(open(os.path.join(HERE, "..", "traffic_signs", "clean", "eval_set_100.json")))
ids = sorted(r["id"] for r in gt)
cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}

from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, lang="en")

for n, i in enumerate(ids):
    if str(i) in cache:
        continue
    path = os.path.join(CROPS, f"crop_{i:03d}.png")
    r = ocr.predict(path)
    texts = []
    for res in (r or []):
        try:
            rt = res["rec_texts"]; sc = res["rec_scores"]
        except Exception:
            rt = getattr(res, "rec_texts", []); sc = getattr(res, "rec_scores", [1.0] * len(rt))
        texts += [{"text": t, "conf": round(float(s), 3)} for t, s in zip(rt, sc)]
    cache[str(i)] = texts
    json.dump(cache, open(CACHE, "w"))  # incremental save
    print(f"[{n+1}/{len(ids)}] id={i}: {[t['text'] for t in texts]}", flush=True)
print(f"done: {len(cache)} crops cached")
