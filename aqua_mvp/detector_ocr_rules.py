"""Pure-code binary detector: is_speed_limit + is_numbered. $0, no LLM.

Evidence: cached PaddleOCR, two passes per crop (base + 4x-upscale/autocontrast).
Color/shape was tested and rejected: crops are too small/faded for red-ring or
yellow-plaque detection (true circles score red_frac 0.0, negatives 0.3).

Decision rules:
  is_speed_limit:
    a) speed word (SPEED/LIMIT/MAXIMUM/MPH/km/h) + plausible speed number, or
    b) bare plausible number CONFIRMED BY BOTH OCR passes (conf >= 0.85 each),
       no veto word, no physical unit attached (30 m, 3,5t, A100m).
    Cross-pass agreement is the key precision guard: hallucinated or
    route-marker numbers ('55' shield, '130' plate) appear in one pass only.
  is_numbered:
    any digit token at conf >= 0.99, or a 2+ digit run at conf >= 0.65,
    or is_speed_limit. Single low-conf digits are junk ('7' @ 0.985 on an
    unnumbered sign) - the 0.99 bar is deliberate.

Interface matches score_detector.py: detect(item_id) -> dict.
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = json.load(open(os.path.join(HERE, "data", "paddle_cache.json")))
UP = json.load(open(os.path.join(HERE, "data", "paddle_cache_up.json")))
_p8 = os.path.join(HERE, "data", "paddle_cache_8x.json")
UP8 = json.load(open(_p8)) if os.path.exists(_p8) else {}

PLAUSIBLE = {5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75,
             80, 85, 90, 95, 100, 110, 120, 130}
SPEED_WORDS = re.compile(r"speed|limit|maximum|mph|m\.p\.h|km/h|kmh|km/", re.I)
VETO_WORDS = re.compile(r"stop|closed|lane|turn|drive|ave|street|route|west|east|"
                        r"north|south|mile|ton|frei|priority|oncoming", re.I)


def _pass_numbers(toks, min_conf):
    """Plausible standalone numbers in one OCR pass.

    A digit run embedded in longer numeric junk ('2000-10.00') or glued to a
    physical unit ('30 m', '3,5t', 'A100m') does not count.
    """
    out = set()
    for t in toks:
        if t["conf"] < min_conf:
            continue
        for m in re.finditer(r"(?<![\d.,-])(\d+)(?![\d.]|\s*[mMtT]\b)", t["text"]):
            v = int(m.group(1))
            if v in PLAUSIBLE:
                out.add(v)
    return out


def detect(item_id: int) -> dict:
    base = BASE.get(str(item_id), [])
    up = UP.get(str(item_id), [])
    up8 = UP8.get(str(item_id), [])
    passes = [base, up, up8]
    joined = " ".join(t["text"] for p in passes for t in p if t["conf"] >= 0.6)

    has_speed_word = bool(SPEED_WORDS.search(joined))
    has_veto = bool(VETO_WORDS.search(joined))
    nums = [_pass_numbers(p, 0.85) for p in passes]
    # a number is confirmed when at least 2 of the 3 passes read it
    confirmed = {v for v in set().union(*nums)
                 if sum(v in n for n in nums) >= 2}

    if has_speed_word and set().union(*nums):
        is_speed = True
    elif confirmed and not has_veto:
        is_speed = True
    else:
        # upscale-only rescue: upscaling strictly adds readability, so a
        # single high-conf plausible number found only at 4x/8x on a
        # base-blind crop is real ('65', '25', '40' on tiny circles). The
        # reverse (base-only, lost on upscale) stays negative - those reads
        # are noise or route markers.
        base_blind = not any(t["conf"] >= 0.6 and re.search(r"[A-Za-z0-9]{2,}",
                                                            t["text"])
                             for t in base)
        strong_up = _pass_numbers(up, 0.95) | _pass_numbers(up8, 0.95)
        is_speed = base_blind and len(strong_up) == 1 and not has_veto

    pass_digits = [{m.group() for t in p
                    for m in re.finditer(r"\d+(?:\.\d+)?", t["text"])
                    if t["conf"] >= 0.65}
                   for p in passes]
    all_digits = [(m.group(), t["conf"])
                  for p in passes for t in p
                  for m in re.finditer(r"\d+", t["text"])]
    # 2+ digit runs from the base/4x passes stand alone; the 8x pass
    # hallucinates on blank signs, so its reads need a second pass to agree.
    # A single-digit token needs conf >= 0.99 regardless of pass.
    solid_run = any(len(d) >= 2 for pd in pass_digits[:2] for d in pd) \
        or any(len(d) >= 2 and d in pass_digits[0] | pass_digits[1]
               for d in pass_digits[2])
    is_numbered = is_speed \
        or any(c >= 0.99 for d, c in all_digits) \
        or solid_run

    return {"is_speed_limit": is_speed, "is_numbered": is_numbered,
            "evidence": {"base": [(t["text"], t["conf"]) for t in base],
                         "up": [(t["text"], t["conf"]) for t in up],
                         "up8": [(t["text"], t["conf"]) for t in up8],
                         "confirmed_numbers": sorted(confirmed)}}
