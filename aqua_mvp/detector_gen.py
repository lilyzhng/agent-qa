"""Speed-limit sign detector / reader for traffic-sign crops.

Pipeline
--------
1. A colour profile of the crop nominates a candidate class:
     * yellow dominant                   -> advisory plaque
     * significant red ring              -> regulatory circle
     * pale sign with a dark diagonal slash -> end-of-speed-limit
2. The number is read with tesseract using the classic tricks:
   4x upscale, autocontrast, a sweep of binarisation thresholds, a digit
   whitelist, and only numbers that repeat across thresholds are trusted.
3. A second OCR sweep without a whitelist hunts for units / decimals
   ("3,5t", "30m", "70M", "10%") so weight limits, length limits,
   distance plaques and grade plaques can be vetoed.
4. Anything uncertain becomes "not_a_speed_limit" -- precision first.
"""

import os
import re
from collections import Counter

import numpy as np
from PIL import Image, ImageOps
import pytesseract

_THRESHOLDS = (100, 120, 140, 160, 180)
_VETO_THRESHOLDS = (110, 140, 170)
_PSMS = (7, 6)
_MIN_SPEED = 5
_MAX_SPEED = 140

_RE_DIGITS = re.compile(r"\d+")
_RE_WEIGHT = re.compile(r"\d(?:[.,]\d)?\s*[tT]\b")          # 3,5t / 10t
_RE_LENGTH = re.compile(r"\d(?:[.,]\d)?\s*[mM](?![pP][hH])")  # 30m / 70M (not MPH)
_RE_DECIMAL = re.compile(r"\d[.,]\d")                       # 3,5 / 4.2
_RE_PERCENT = re.compile(r"\d\s*%")                         # 10% grade plaques


# --------------------------------------------------------------------------- #
# IO
# --------------------------------------------------------------------------- #
def _crop_path(item_id):
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(here, "..", "traffic_signs", "review", "crops",
                        "crop_{:03d}.png".format(item_id))


def _load_image(item_id):
    path = _crop_path(item_id)
    if not os.path.isfile(path):
        return None
    try:
        return Image.open(path).convert("RGB")
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Colour / shape analysis
# --------------------------------------------------------------------------- #
def _colour_profile(arr):
    r = arr[..., 0].astype(np.int16)
    g = arr[..., 1].astype(np.int16)
    b = arr[..., 2].astype(np.int16)
    mx = np.maximum(np.maximum(r, g), b)
    mn = np.minimum(np.minimum(r, g), b)
    mean = (r + g + b) / 3.0

    red = (r > 120) & (r - g > 55) & (r - b > 55) & (g < 130)
    yellow = (r > 140) & (g > 115) & (b < 150) & (r - b > 50) & (g - b > 25)
    white = (mn > 145) & (mx - mn < 65)
    grey = (mx - mn < 45) & (mean > 55) & (mean < 210)

    return {
        "red": float(red.mean()),
        "yellow": float(yellow.mean()),
        "white": float(white.mean()),
        "grey": float(grey.mean()),
        "brightness": float(mean.mean()),
        "pale_mask": white | grey,
    }


def _slash_score(gray):
    """Excess darkness along either diagonal band, measured in an outer
    annulus so the central digits cannot fake a slash."""
    h, w = gray.shape
    yy, xx = np.mgrid[0:h, 0:w]
    u = xx / float(max(w - 1, 1))
    v = yy / float(max(h - 1, 1))
    r2 = (u - 0.5) ** 2 + (v - 0.5) ** 2
    outer = (r2 < 0.42 ** 2) & (r2 > 0.24 ** 2)
    if int(outer.sum()) < 200:
        return 0.0
    dark = 255.0 - gray
    band_main = np.abs(u - v) < 0.085
    band_anti = np.abs(u + v - 1.0) < 0.085
    bands = band_main | band_anti
    rest = outer & ~bands
    base = float(dark[rest].mean()) if rest.any() else float(dark[outer].mean())
    best = 0.0
    for band in (band_main, band_anti):
        region = outer & band
        if int(region.sum()) < 60:
            continue
        if float((gray[region] < 90).mean()) < 0.10:
            continue  # no genuinely dark stroke along this diagonal
        best = max(best, float(dark[region].mean()) - base)
    return best


def _circleish(mask):
    """True if the pale pixels look like a circle (not a rectangular plaque)."""
    ys, xs = np.nonzero(mask)
    if xs.size < 200:
        return False
    x0, x1 = int(xs.min()), int(xs.max())
    y0, y1 = int(ys.min()), int(ys.max())
    bw = x1 - x0 + 1
    bh = y1 - y0 + 1
    if bw < 24 or bh < 24:
        return False
    aspect = bw / float(bh)
    if not (0.72 < aspect < 1.38):
        return False
    sub = mask[y0:y1 + 1, x0:x1 + 1]
    fill = float(sub.mean())
    if not (0.50 < fill < 0.93):
        return False
    ch = max(int(bh * 0.14), 2)
    cw = max(int(bw * 0.14), 2)
    corners = np.concatenate([
        sub[:ch, :cw].ravel(), sub[:ch, -cw:].ravel(),
        sub[-ch:, :cw].ravel(), sub[-ch:, -cw:].ravel()])
    if corners.size and float(corners.mean()) > 0.25:
        return False  # filled corners -> rectangle, not a circle
    return True


# --------------------------------------------------------------------------- #
# OCR
# --------------------------------------------------------------------------- #
def _prep_gray(img, border=0.14, scale=4):
    w, h = img.size
    dx = int(round(w * border))
    dy = int(round(h * border))
    if w - 2 * dx > 8 and h - 2 * dy > 8:
        img = img.crop((dx, dy, w - dx, h - dy))
    img = img.resize((max(img.width * scale, 1), max(img.height * scale, 1)),
                     Image.LANCZOS)
    gray = img.convert("L")
    return ImageOps.autocontrast(gray, cutoff=1)


def _binarize(gray, t):
    return gray.point(lambda p, t=t: 255 if p > t else 0)


def _tess(img, config):
    try:
        return pytesseract.image_to_string(img, config=config) or ""
    except Exception:
        return ""


def _read_digits(gray):
    """Digit-whitelisted OCR over a threshold sweep; count repeats."""
    counts = Counter()
    for t in _THRESHOLDS:
        bw = _binarize(gray, t)
        for psm in _PSMS:
            cfg = "--psm %d -c tessedit_char_whitelist=0123456789" % psm
            for tok in _RE_DIGITS.findall(_tess(bw, cfg)):
                try:
                    n = int(tok)
                except ValueError:
                    continue
                if _MIN_SPEED <= n <= _MAX_SPEED:
                    counts[n] += 1
    return counts


def _unit_hits(gray):
    """Unwhitelisted OCR sweep looking for t / m / % / decimals."""
    blob = []
    for t in _VETO_THRESHOLDS:
        bw = _binarize(gray, t)
        for psm in _PSMS:
            blob.append(_tess(bw, "--psm %d" % psm))
    text = "\n".join(blob)
    units = (len(_RE_WEIGHT.findall(text))
             + len(_RE_LENGTH.findall(text))
             + len(_RE_PERCENT.findall(text)))
    decimals = len(_RE_DECIMAL.findall(text))
    return units, decimals


def _vetoed(units, decimals, best):
    if units >= 2 or decimals >= 2:
        return True
    if units >= 1 and decimals >= 1:
        return True
    # A single weak unit/decimal sighting is enough when the candidate is a
    # classic weight/length value (3,5t -> "35", 10t -> "10", 12t -> "12").
    if units + decimals >= 1 and best is not None:
        if best % 10 == 5 or best in (10, 12):
            return True
    return False


def _pick_number(counts, min_repeats):
    cands = [(n, c) for n, c in counts.items() if c >= min_repeats]
    if not cands:
        return None

    def rank(item):
        n, c = item
        digits = len(str(n))
        pref = 0 if digits == 2 else (1 if digits == 3 else 2)
        return (-c, pref, n)

    cands.sort(key=rank)
    return cands[0][0]


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
def detect(item_id: int) -> dict:
    negative = {"is_speed_limit": False, "fine_label": "not_a_speed_limit"}

    img = _load_image(item_id)
    if img is None:
        return dict(negative)
    arr = np.asarray(img)
    if arr.size == 0:
        return dict(negative)

    prof = _colour_profile(arr)

    kind = None
    if prof["yellow"] > 0.18 and prof["yellow"] > 1.5 * prof["red"]:
        kind = "advisory"
    elif prof["red"] > 0.05:
        kind = "regulatory"
    else:
        pale = prof["brightness"] > 95 and (prof["white"] + prof["grey"]) > 0.30
        if pale and prof["red"] < 0.04 and prof["yellow"] < 0.08:
            gray_full = np.asarray(img.convert("L")).astype(np.float32)
            if (_slash_score(gray_full) > 22.0
                    and _circleish(prof["pale_mask"])):
                kind = "end"

    if kind is None:
        return dict(negative)

    gray = _prep_gray(img)
    counts = _read_digits(gray)
    # Grey end-of-limit digits are the hardest read, so accept a single
    # sighting there; everywhere else demand repetition across thresholds.
    best = _pick_number(counts, min_repeats=1 if kind == "end" else 2)

    if kind in ("regulatory", "advisory"):
        units, decimals = _unit_hits(gray)
        if _vetoed(units, decimals, best):
            return dict(negative)

    if best is None:
        return dict(negative)

    label = {
        "regulatory": "speed_limit_%d" % best,
        "advisory": "advisory_%d" % best,
        "end": "end_of_speed_limit_%d" % best,
    }[kind]
    return {"is_speed_limit": True, "fine_label": label}