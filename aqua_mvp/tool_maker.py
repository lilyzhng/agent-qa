"""Toolmaker loop (design 3.5): Kimi K3 authors a detector, we score it on the
dev split, feed the error classes back, iterate up to K rounds, freeze the best.

Anti-overfit: K3 sees aggregate metrics and error CATEGORIES (counts + at most
3 example crop filenames per category), never the GT labels themselves.
Final number is reported on the held-out split.
"""
import json
import os
import re
import sys

import litellm
from dotenv import load_dotenv

import score_detector

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
litellm.api_key = os.environ["OPENROUTER_API_KEY"]

AUTHOR_MODEL = os.environ.get("AQUA_TOOLMAKER_MODEL", "openrouter/moonshotai/kimi-k3")
K_ROUNDS = 3

AUTHOR_PROMPT = """You are a toolmaker. Write a Python function that detects
whether a traffic-sign crop actually contains a speed-limit sign, and if so
reads the number.

Contract:
- File must define: detect(item_id: int) -> dict
  returns {"is_speed_limit": bool, "fine_label": str}
  fine_label is "speed_limit_<N>", "advisory_<N>", "end_of_speed_limit_<N>",
  or "not_a_speed_limit".
- The crop image is at ../traffic_signs/review/crops/crop_{item_id:03d}.png
  relative to the file. Use PIL, numpy, and pytesseract (tesseract binary is
  installed). No network calls. No torch/cv2.
- Regulatory signs are white or red circles; advisory plaques are yellow;
  end-of-limit signs are grey with a diagonal slash. Weight limits (3.5t),
  length limits (30m), distance plaques (70M), route markers, and exit
  numbers are NOT speed limits.
- Tesseract is weak on scene text. Winning tricks: upscale 4x, autocontrast,
  sweep several binarization thresholds, whitelist digits, keep only numbers
  that repeat across thresholds, use the color profile to decide class.
- The judge uses detection precision/recall primarily; the number matters
  secondarily. It is better to say not_a_speed_limit than to hallucinate.

Return ONLY the Python file content, no markdown fences."""


def ask_k3(messages):
    r = litellm.completion(model=AUTHOR_MODEL, messages=messages, temperature=0.2)
    return r.choices[0].message.content


def extract_code(text):
    m = re.search(r"```(?:python)?\n(.*?)```", text, re.S)
    return m.group(1) if m else text


def error_summary(res):
    from collections import Counter
    c = Counter(e["kind"] for e in res["errors"])
    lines = [f"{k}: {v}" for k, v in c.most_common()]
    return "\n".join(lines)


def main():
    det_path = os.path.join(HERE, "detector_gen.py")
    messages = [{"role": "user", "content": AUTHOR_PROMPT}]
    best = None
    for rnd in range(1, K_ROUNDS + 1):
        print(f"--- round {rnd}: authoring with {AUTHOR_MODEL}")
        code = extract_code(ask_k3(messages))
        open(det_path, "w").write(code)
        try:
            res = score_detector.score(det_path, "dev")
        except Exception as e:
            print("detector crashed:", e)
            messages.append({"role": "assistant", "content": code})
            messages.append({"role": "user", "content": f"Your detector crashes on load: {e}. Fix it. Return the full corrected file."})
            continue
        print(f"dev: P={res['precision']} R={res['recall']} F1={res['f1']} errors={len(res['errors'])}")
        if best is None or res["f1"] > best["f1"]:
            best = {**res, "round": rnd, "code": code}
        if rnd < K_ROUNDS:
            messages.append({"role": "assistant", "content": code})
            fb = (f"Dev split results: precision={res['precision']}, recall={res['recall']}, "
                  f"F1={res['f1']}, number_accuracy={res['number_accuracy']}.\n"
                  f"Error classes:\n{error_summary(res)}\n"
                  f"Improve recall without losing precision. Return the full improved file.")
            messages.append({"role": "user", "content": fb})

    # freeze best and score held-out
    open(det_path, "w").write(best["code"])
    hold = score_detector.score(det_path, "holdout")
    print(f"\nBEST round {best['round']} | dev F1={best['f1']} | HOLDOUT: "
          f"P={hold['precision']} R={hold['recall']} F1={hold['f1']}")
    json.dump({"best_round": best["round"], "dev": {k: best[k] for k in ('precision','recall','f1')},
               "holdout": hold}, open(os.path.join(HERE, "data", "toolmaker_result.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
