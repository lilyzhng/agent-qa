"""Aqua MVP agent runner.

For each corrupted instance the agent:
  1. reads the label store record (label is always `other_sign`)
  2. calls view_sample to look at the crop
  3. calls submit_verdict with its classification

The GT file is never loaded anywhere in this process except by eval.py.
"""
import asyncio
import json
import os
import sys

import cheap_cv

from agents import Agent, Runner, set_tracing_disabled
from agents.extensions.models.litellm_model import LitellmModel
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tools import list_items, view_sample, analyze_sign, submit_verdict, VERDICTS

HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))

MODEL = os.environ.get("AQUA_MODEL", "openrouter/moonshotai/kimi-k2.5")
_or_key = os.environ.get("OPENROUTER_API_KEY")
_model_obj = None
if _or_key:
    set_tracing_disabled(True)
    _model_obj = LitellmModel(model=MODEL, api_key=_or_key)

INSTRUCTIONS = """You are a label QA orchestrator for traffic signs. The label
store is suspected of mislabeling: many signs were filed under the catch-all
class `other_sign`. Your job is to find the speed-limit signs hiding there and
backfill their fine-grained labels.

You are an ORCHESTRATOR, not a perceiver. Decide from tool evidence, in order:
1. Always call analyze_sign first. It returns OCR numbers (with vote counts
   from a multi-threshold sweep), unit hints, MPH presence, and color
   fractions. This tool is free.
2. Decide from that evidence. You are answering TWO binary questions:
   does the sign have digits (is_numbered), and is it a speed limit
   (is_speed_limit). You do not need to read the exact number.
   - Numbers with unit_hint "tonnes" or "meters" are weight/length/distance
     limits. This is a HARD VETO: never call them speed limits, even when
     plausible_speed=true.
   - Yellow-dominant crop + number -> "advisory_<N>".
   - White or red-circle dominant + number -> "speed_limit_<N>".
   - Grey-dominant + number -> "end_of_speed_limit_<N>".
   - No usable number evidence -> "not_a_speed_limit".
3. Call view_sample when the cheap evidence cannot settle the case: no
   plausible number found, or two plausible numbers disagree, or the color
   signal conflicts with the numbers. Never conclude not_a_speed_limit from
   silence alone — absence of OCR output is a reason to look, not a verdict.
   view_sample is expensive; use it only on these hard cases.
4. Call submit_verdict with is_speed_limit and is_numbered. is_numbered is
   true whenever the sign carries ANY digits — route markers (M-43), exit
   numbers, weight limits (3.5t), length limits (30m), and distance plaques
   (70M) are numbered but are NOT speed limits. You do NOT need to read the
   exact number. The goal is to quantify mislabeled instances and attach the
   is_numbered attribute, not to fix labels.
"""


async def process_item(agent, rec, timeout=120):
    evidence = cheap_cv.analyze(rec["id"])
    has_number = any(n.get("plausible_speed") and n.get("trusted") for n in evidence.get("ocr", {}).get("numbers", []))
    if has_number:
        directive = "The cheap analysis above found a plausible speed number. Decide from this evidence; call view_sample only if it conflicts."
    else:
        directive = "The cheap analysis found NO plausible speed number. You MUST call view_sample to look at the crop before deciding."
    prompt = (
        f"Label store record: id={rec['id']}, image={rec['image']}, "
        f"current label=`{rec['label']}`.\n"
        f"Cheap analysis of the crop: {json.dumps(evidence)}\n"
        f"{directive}\n"
        f"Then you MUST call submit_verdict before finishing."
    )
    result = await asyncio.wait_for(Runner.run(agent, prompt, max_turns=8), timeout=timeout)

    # ATIF-style trace: full input list of the run (tool calls, outputs, messages)
    trace_dir = os.path.join(HERE, "data", "traces")
    os.makedirs(trace_dir, exist_ok=True)
    trace = {
        "item_id": rec["id"],
        "model": MODEL,
        "steps": result.to_input_list(),
        "verdict": VERDICTS.get(rec["id"]),
    }
    with open(os.path.join(trace_dir, f"{rec['id']:03d}.json"), "w") as f:
        json.dump(trace, f, default=str)


async def main(limit=None):
    items = json.load(open(os.path.join(HERE, "data", "corrupted_labels.json")))
    if limit:
        items = items[:limit]
    agent = Agent(
        name="aqua-label-qa",
        instructions=INSTRUCTIONS,
        tools=[list_items, analyze_sign, view_sample, submit_verdict],
        model=_model_obj or MODEL,
    )
    sem = asyncio.Semaphore(8)
    done = [0]

    async def worker(rec):
        async with sem:
            try:
                await process_item(agent, rec)
            except Exception as e:
                print(f"[{rec['id']}] agent error: {e}", flush=True)
            done[0] += 1
            if done[0] % 10 == 0:
                print(f"progress: {done[0]}/{len(items)}", flush=True)
            # incremental write: survive crashes mid-run
            pred_path = os.path.join(HERE, "data", "predictions.json")
            json.dump({str(k): v for k, v in VERDICTS.items()}, open(pred_path, "w"), indent=1)

    await asyncio.gather(*(worker(rec) for rec in items))

    out = {str(k): v for k, v in VERDICTS.items()}
    pred_path = os.path.join(HERE, "data", "predictions.json")
    json.dump(out, open(pred_path, "w"), indent=1)
    print(f"wrote {len(out)} verdicts -> {pred_path}")


if __name__ == "__main__":
    lim = int(sys.argv[1]) if len(sys.argv) > 1 else None
    asyncio.run(main(lim))
