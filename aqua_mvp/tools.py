"""Aqua MVP tools (design doc Table 3, minimal set).

The agent may ONLY touch data/corrupted_labels.json and the crop images.
It has no access to the GT file.
"""
import base64
import json
import os

from agents import function_tool
from agents.tool import ToolOutputImage

import cheap_cv

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
CROPS = os.path.join(HERE, "..", "traffic_signs", "review", "crops")


def _load_corrupted():
    return json.load(open(os.path.join(DATA, "corrupted_labels.json")))


@function_tool
def list_items() -> str:
    """List all instances in the label store: id, image, current label."""
    items = _load_corrupted()
    return json.dumps(items)


@function_tool
def analyze_sign(item_id: int) -> str:
    """Cheap local analysis of the sign crop: OCR numbers with vote counts
    (multi-threshold tesseract), unit hints (tonnes/meters), MPH presence,
    and a color profile (yellow/red/white/grey fractions). Free and fast.
    Always call this first."""
    return json.dumps(cheap_cv.analyze(item_id))


@function_tool
def view_sample(item_id: int) -> ToolOutputImage | str:
    """GATED, expensive: look at the crop with vision. Only call this when
    analyze_sign evidence is missing or contradictory. Do not call it as a
    default."""
    path = os.path.join(CROPS, f"crop_{item_id:03d}.png")
    if not os.path.exists(path):
        return json.dumps({"error": f"no crop for id {item_id}"})
    b64 = base64.b64encode(open(path, "rb").read()).decode()
    return ToolOutputImage(image_url=f"data:image/png;base64,{b64}")


# --- verdict collection (module-level sink, read by tool_router.py) ---
VERDICTS = {}


@function_tool
def submit_verdict(item_id: int, is_speed_limit: bool, is_numbered: bool) -> str:
    """File your verdict for one instance.

    item_id: the instance id.
    is_speed_limit: true if the sign is a speed-limit sign (regulatory,
      advisory, or end-of-limit all count).
    is_numbered: true if the sign carries ANY number, even when it is not a
      speed limit (route markers like M-43, exit numbers, weight 3.5t,
      length 30m, distance 70M). This is the SLIFF `is_numbered` attribute.
    We do NOT need the exact number, only whether digits are present.
    """
    if is_speed_limit:
        is_numbered = True  # a speed limit always carries a number
    VERDICTS[item_id] = {"is_speed_limit": is_speed_limit,
                         "is_numbered": is_numbered}
    return json.dumps({"recorded": item_id})
