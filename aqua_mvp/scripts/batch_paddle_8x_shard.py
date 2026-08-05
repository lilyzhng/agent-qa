"""8x OCR pass, one shard: batch_paddle_8x_shard.py <shard_idx> <n_shards>.
Writes data/paddle_cache_8x.shard<idx>.json. Merge with merge_8x_shards.py."""
import json, os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
from PIL import Image

shard, nshards = int(sys.argv[1]), int(sys.argv[2])
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROPS = os.path.join(HERE, "..", "traffic_signs", "review", "crops")
OUT = os.path.join(HERE, "data", f"paddle_cache_8x.shard{shard}.json")

gt = json.load(open(os.path.join(HERE, "..", "traffic_signs", "clean", "eval_set_100.json")))
ids = [i for n, i in enumerate(sorted(r["id"] for r in gt)) if n % nshards == shard]
cache = json.load(open(OUT)) if os.path.exists(OUT) else {}

from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, lang="en")

for n, i in enumerate(ids):
    if str(i) in cache:
        continue
    img = Image.open(os.path.join(CROPS, f"crop_{i:03d}.png")).convert("RGB")
    img = img.resize((min(img.width * 8, 2600), min(img.height * 8, 2600)), Image.LANCZOS)
    r = ocr.predict(np.asarray(img))
    texts = []
    for res in (r or []):
        try: rt, sc = res["rec_texts"], res["rec_scores"]
        except Exception: rt, sc = [], []
        texts += [{"text": t, "conf": round(float(s), 3)} for t, s in zip(rt, sc)]
    cache[str(i)] = texts
    json.dump(cache, open(OUT, "w"))
    print(f"shard{shard} [{n+1}/{len(ids)}] id={i}", flush=True)
print(f"shard{shard} done: {len(cache)}")
