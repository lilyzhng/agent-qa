"""Probe OCR-blind crops with aggressive preprocessing variants (paddle venv)."""
import os, warnings
warnings.filterwarnings("ignore")
import numpy as np
from PIL import Image, ImageOps, ImageFilter

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CROPS = os.path.join(HERE, "..", "traffic_signs", "review", "crops")
BLIND = [50, 71, 170, 178, 456, 746, 701, 714, 744]

from paddleocr import PaddleOCR
ocr = PaddleOCR(use_doc_orientation_classify=False, use_doc_unwarping=False,
                use_textline_orientation=False, lang="en")

def variants(img):
    v = {}
    big = img.resize((img.width * 8, img.height * 8), Image.LANCZOS)
    v["8x"] = big
    v["8x_eq"] = ImageOps.equalize(big)
    v["8x_sharp"] = big.filter(ImageFilter.UnsharpMask(radius=6, percent=200))
    g = ImageOps.autocontrast(big.convert("L"), cutoff=2)
    v["8x_gray_ac"] = g.convert("RGB")
    return v

for i in BLIND:
    img = Image.open(os.path.join(CROPS, f"crop_{i:03d}.png")).convert("RGB")
    print(f"id={i} size={img.size}")
    for name, im in variants(img).items():
        r = ocr.predict(np.asarray(im))
        toks = []
        for res in (r or []):
            try: rt, sc = res["rec_texts"], res["rec_scores"]
            except Exception: rt, sc = [], []
            toks += [(t, round(float(s), 2)) for t, s in zip(rt, sc)]
        print(f"   {name:12s} {toks}", flush=True)
