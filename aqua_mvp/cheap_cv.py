"""Cheap local analysis for sign crops. No VLM, no network.

Two signals:
  1. OCR (tesseract): text tokens + per-token confidence + extracted numbers.
  2. Color profile: does the crop look like a white/red-circle regulatory sign,
     a yellow advisory plaque, or a grey end-of-limit sign?

These are deliberately crude. The point (per the design doc) is that cheap
tools produce evidence; the orchestrator reasons over it.
"""
import os
import re
import subprocess

import numpy as np
import pytesseract
from PIL import Image

CROPS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "..", "traffic_signs", "review", "crops")
HERE = os.path.dirname(os.path.abspath(__file__))
PADDLE_PY = os.path.join(HERE, ".venv-paddle", "bin", "python")
PADDLE_SCRIPT = os.path.join(HERE, "paddle_ocr.py")

PLAUSIBLE_SPEEDS = {5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75,
                    80, 85, 90, 95, 100, 110, 120, 130}


def _color_profile(path):
    img = Image.open(path).convert("RGB")
    a = np.asarray(img).reshape(-1, 3).astype(float)
    n = len(a)
    r, g, b = a[:, 0], a[:, 1], a[:, 2]
    sat = (a.max(axis=1) - a.min(axis=1)) / (a.max(axis=1) + 1e-6)
    yellow = ((r > 150) & (g > 110) & (b < 110) & (sat > 0.3)).mean()
    red = ((r > 130) & (g < 90) & (b < 90) & (sat > 0.35)).mean()
    whiteish = ((r > 185) & (g > 185) & (b > 185)).mean()
    grey = ((sat < 0.15) & (r > 90) & (r < 200)).mean()
    dark = (a.mean(axis=1) < 70).mean()
    return {"yellow_frac": round(float(yellow), 3),
            "red_frac": round(float(red), 3),
            "white_frac": round(float(whiteish), 3),
            "grey_frac": round(float(grey), 3),
            "dark_frac": round(float(dark), 3)}


def _paddle_ocr(path):
    """Primary OCR: PaddleOCR via subprocess bridge (py3.13 venv).
    Returns list of {"text", "conf"} or None if unavailable."""
    try:
        out = subprocess.run([PADDLE_PY, PADDLE_SCRIPT, path],
                             capture_output=True, text=True, timeout=120)
        for line in out.stdout.strip().splitlines()[::-1]:
            line = line.strip()
            if line.startswith("{"):
                import json as _json
                return _json.loads(line)["texts"]
    except Exception:
        pass
    return None


def _ocr(path):
    """PaddleOCR first; multi-threshold tesseract as fallback."""
    paddle_texts = _paddle_ocr(path)
    if paddle_texts is not None:
        votes = {}
        has_mph = False
        unit_hint = {}
        for t in paddle_texts:
            txt = t["text"]
            if "mph" in txt.lower():
                has_mph = True
            for m in re.finditer(r"\d+", txt):
                v = int(m.group())
                if v > 200:
                    continue
                # conf-weighted votes: high-conf counts double
                votes[v] = votes.get(v, 0) + (2 if t["conf"] >= 0.9 else 1)
                if re.search(rf"\b{v}\s*t\b", txt, re.I):
                    unit_hint[v] = "tonnes"
                elif re.search(rf"\b{v}\s*m\b", txt) and "mph" not in txt.lower():
                    unit_hint.setdefault(v, "meters")
        numbers = [{"value": v, "votes": n, "plausible_speed": v in PLAUSIBLE_SPEEDS,
                    "trusted": n >= 2, "source": "paddleocr",
                    **({"unit_hint": unit_hint[v]} if v in unit_hint else {})}
                   for v, n in sorted(votes.items(), key=lambda x: -x[1])]
        return {"numbers": numbers, "has_mph": has_mph}

    # fallback: tesseract sweep
    img = Image.open(path).convert("L")
    if max(img.size) < 300:
        img = img.resize((img.width * 4, img.height * 4), Image.LANCZOS)
    from PIL import ImageOps
    img = ImageOps.autocontrast(img)
    a = np.array(img)
    votes = {}
    has_mph = False
    unit_hint = {}
    for th in (None, 100, 128, 160, 180):
        b = (a > th).astype(np.uint8) * 255 if th is not None else a
        text = pytesseract.image_to_string(
            Image.fromarray(b),
            config="--psm 6 -c tessedit_char_whitelist=0123456789MPHmphTt ")
        if "mph" in text.lower():
            has_mph = True
        for m in re.finditer(r"\d+", text):
            v = int(m.group())
            if v > 200:
                continue
            votes[v] = votes.get(v, 0) + 1
            if re.search(rf"\b{v}\s*t\b", text, re.I):
                unit_hint[v] = "tonnes"
            elif re.search(rf"\b{v}\s*m\b", text) and "mph" not in text.lower():
                unit_hint.setdefault(v, "meters")
    numbers = [{"value": v, "votes": n, "plausible_speed": v in PLAUSIBLE_SPEEDS,
                "trusted": n >= 2, "source": "tesseract",
                **({"unit_hint": unit_hint[v]} if v in unit_hint else {})}
               for v, n in sorted(votes.items(), key=lambda x: -x[1])]
    return {"numbers": numbers, "has_mph": has_mph}


def analyze(item_id: int) -> dict:
    path = os.path.join(CROPS, f"crop_{item_id:03d}.png")
    if not os.path.exists(path):
        return {"error": f"no crop for id {item_id}"}
    return {"item_id": item_id, "ocr": _ocr(path), "color": _color_profile(path)}


if __name__ == "__main__":
    import json, sys
    print(json.dumps(analyze(int(sys.argv[1])), indent=1))
