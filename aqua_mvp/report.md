# Aqua MVP

**Lily Zhang** · Jul 29, 2026

**Goal:** Matching cheap detector with VLM agent performance.

**Context:** speed-limit signs mislabeled as `other_sign` must be found and backfilled with fine-grained labels (3.1.4), so:

- Can an agent use cheap tools reliable enough to do this accurately enough?
- Where is the boundary between when a free deterministic tool is good enough versus when we need a better model?

## 1. Getting the tests ready

Build a eval set.

*Figure 1. Fix wrong labels*

*Figure 2. Is_speed_limit: false, is_number: true*

*Figure 3. Is_speed_limit: false, is_number: true*

- **Ground truth**: `traffic_signs/clean/eval_set_100.json`, 103 crops, 53 positives (including advisory and end-of-limit signs) and 50 negatives
- **Corrupted input**: every instance relabeled to `other_sign` (`corrupt.py`). The agent never reads the GT. GT is read only by `eval.py`.
- **Agent scaffold**: OpenAI Agents SDK, one fresh run per item, max 6 turns. Tools: `list_items`, `view_sample` (returns the crop image), `submit_result`.
- **Scoring**: detection precision/recall/F1 on `is_speed_limit`. Attempt 6 added the second binary task, `is_numbered` — the job is to find mislabeled instances and attach attributes, not to fix labels.

The agent loop caught two GT errors: #71 (re-judged: it is an advisory 25, GT was wrong) and #137 (reads 43, not 45). The eval loop doubles as a GT audit.

## 2. The iterations

Two metrics per attempt, one per binary question. `is_speed_limit F1`: is this a speed-limit sign? Number column: attempts 1–5 report number-reading accuracy on true positives (the task was still "read the exact number"); attempts 6–7 report `is_numbered` F1 (does the sign carry any digits?) after the task went binary.

| # | Change | is_speed_limit F1 | Number (acc 1–5 / is_numbered F1 6–7) | Result |
| :-- | :-- | --: | --: | :-- |
| 1 | Baseline: single-pass VLM classify (gpt-4o-mini) | 0.981 → 0.991 after GT fix #2 | 1.000 | Keeper |
| 2 | Prompt framing rules | 0.972 | 1.000 | Regression |
| 3 | 65% center crop | 0.839 | 0.974 | Reverted |
| 4 | Orchestrator + cheap tools (tesseract OCR, color) | 0.903 | 0.765 | Regression |
| 5 | Kimi K2.5 orchestrator + de-noised evidence | 0.923 | 0.958 | Better, still < 1 |
| 6 | Binary results (is_speed_limit + is_numbered), PaddleOCR | 0.951 | 0.902 | New baseline |
| 7 | Code detector: 3-pass PaddleOCR + cross-pass rules, $0 | 0.947 (P 0.984) | 0.971 (P 1.000) | Winner |

**Attempts 1–3: the VLM baseline and its limits.**

- VLM baseline: look at each crop, decide speed vs not-speed, read the number (F1 0.981, perfect number reading).
- Prompt framing rules (attempt 2) didn't help: they couldn't fix #302, a crop where the target is a 15t weight sign but the padding includes a neighbor's "30" speed circle.
- A 65% center crop (attempt 3) fixed #302 but trimmed out 14 real speed signs mounted off-center.

**Attempts 4–5: orchestration over cheap tools.**

- Per my steering, the agent should orchestrate, not classify: perception belongs to cheap tools (tesseract OCR threshold sweep + color profile, free, local, ~1s), the LLM picks tools and reasons over structured evidence, and the escalation decision lives in code, not in the LLM. The structure was right but the evidence was too noisy.
- OCR ghost digits (a phantom 5 everywhere) dragged it to F1 0.903.
- Attempt 5 swapped the model to Kimi K2.5 and hardened the evidence (numbers need ≥2 votes, unit hints are a hard veto, result consistency enforced in `submit_result`): F1 0.923. Phantom-free but over-conservative — the vote threshold suppressed real numbers on hard crops.

**Attempt 6: binary results + PaddleOCR.**

Dropping `fine_label` for the two binary tasks recovered recall (0.889 → 0.925, F1 0.951). Tesseract was replaced by PaddleOCR (PP-OCRv6) via a subprocess bridge — on the hard cases tesseract failed, Paddle reads them at confidence ~1.0, including #302 where it reads BOTH the 30 and the 15t for the first time. `is_numbered` landed at F1 0.902, over-marking arrow boards and pictograms as digits.

**Attempt 7: delete the LLM.**

Question: can pure tools do both binary tasks? `detector_ocr_rules.py` runs three cached PaddleOCR passes per crop and applies deterministic rules. What mattered:

- **Cross-pass agreement is the key to precision.** A number counts only if ≥2 of 3 passes read it. Route-marker and hallucinated numbers appear in one pass only.
- **Upscale-only rescue.** On base-blind crops, a single high-conf number found at 4x/8x is real.
- **Exclusions.** Speed words + number ⇒ yes; physical units (30 m, 3,5t) and context words (STOP, LANE, TURN) ⇒ exclude.
- **Color/shape was tested and rejected** — crops too small and faded; HSV red-ring fraction is 0.0 on true circles and 0.3 on some negatives.

## 3. Cheap detector vs the VLM

| | is_speed_limit F1 | is_numbered F1 | Cost | Latency |
| :-- | --: | --: | :-- | :-- |
| Best LLM agent (attempt 6, Kimi K2.5 orchestrator line) | 0.951 | 0.902 | API $ per run | minutes |
| **OCR-rules detector (attempt 7, no LLM)** | **0.947** (P 0.984) | **0.971** (P 1.000) | **$0** | **milliseconds** |

Holdout (39 items): numbered F1 1.000, speed F1 0.927. The $0 detector beats the LLM agent on `is_numbered` (+0.069) and is at parity on `is_speed_limit` (−0.004) with strictly better precision.

## 4. Additional requirements (feedback, 2026-07-30)

- **Profile runtime and compute.** Add a section on the runtime and compute needed for 100 slices.
- **Workflow: ScaleX vs BigQuery** — which does the workflow run through? Does it contain crop?
- **TODO: check slice connection** — HulkUM does not have fine-grained labels.
- **Check out SAM3.** Online UM model can be a source of judge.
