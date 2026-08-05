"""PaddleOCR subprocess bridge (runs in .venv-paddle, py3.13).

Usage: paddle_ocr.py <image_path>
Prints JSON: {"texts": [{"text": str, "conf": float}]}

The main venv (py3.14) cannot host paddlepaddle (no 3.14 wheel), so the agent
calls this script via subprocess instead of importing the library.
"""
import json
import sys
import warnings

warnings.filterwarnings("ignore")

_ocr = None

def get_ocr():
    global _ocr
    if _ocr is None:
        from paddleocr import PaddleOCR
        _ocr = PaddleOCR(use_doc_orientation_classify=False,
                         use_doc_unwarping=False,
                         use_textline_orientation=False,
                         lang="en")
    return _ocr

def main(path):
    r = get_ocr().predict(path)
    texts = []
    for res in (r or []):
        # paddleocr 3.x result object: dict-like with rec_texts / rec_scores
        try:
            rt = res["rec_texts"]; sc = res["rec_scores"]
        except Exception:
            rt = getattr(res, "rec_texts", []); sc = getattr(res, "rec_scores", [1.0] * len(rt))
        for t, s in zip(rt, sc):
            texts.append({"text": t, "conf": round(float(s), 3)})
    print(json.dumps({"texts": texts}))

if __name__ == "__main__":
    main(sys.argv[1])
