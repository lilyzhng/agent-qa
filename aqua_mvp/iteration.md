# Aqua MVP — iteration log

Task (design doc 3.1.4, SLIFF mode 1): speed-limit signs mislabeled as `other_sign`
must be found and backfilled with fine-grained labels.

Setup:
- GT: `../traffic_signs/clean/eval_set_100.json` (53 positives incl. advisory and
  end-of-limit, 50 negatives). Human-verified over 5 review rounds.
- Input to agent: `data/corrupted_labels.json` — every instance relabeled
  `other_sign` (corrupt.py). The agent never reads the GT.
- Agent: OpenAI Agents SDK (`openai-agents`), model `gpt-4o-mini`.
  Tools: `list_items`, `view_sample` (returns ToolOutputImage), `submit_verdict`.
  One fresh agent run per item, max 6 turns.
- Scoring: eval.py — detection precision/recall/F1 on is_speed_limit,
  plus number accuracy on true positives.

Anti-cheat rule: the agent process loads only `data/corrupted_labels.json` and
crop images. GT is read only by eval.py.

Anti-cheat audit (2026-07-27): corrupted store contains 103 records, the only
label string present is `other_sign` (no `speed_limit`/`advisory`/`regulatory`
anywhere in the file). tools.py and tool_router.py contain no reference to the GT
path. Verified programmatically.

## Attempt 1 (baseline: single-pass classify)

Prompt: look at each crop, decide speed vs not-speed, read the number,
submit verdict. No OCR tool, no second judge pass, no zoom re-check.

Smoke test (5 items): 4/5 correct, missed #137 (faded gantry sign).

Full run (103 items): RUNNING — results appended below.

### Results

Full run (103 items, 102 verdicts; 1 item errored out and counts as no-prediction):

- detection: TP=53 FP=1 FN=1 TN=48
- **precision 0.981, recall 0.981, F1 0.981**
- number accuracy on TP: 53/53 = 1.000

### Error analysis

Only 2 errors (after GT fix):

1. **FN #137** (GT regulatory-45): faded gantry-mounted "45" partially cut off at
   the top of the crop. Genuinely hard; the sign is incomplete in frame.
2. **FP #302** (GT not_a_speed_limit, pred speed_limit_30): the bbox targets a
   15t weight sign, but the crop's padding includes the "30" speed circle
   mounted above it. Agent answered for the neighbor, not the target.
   Crop-context ambiguity, not a reading error.
3. ~~FP #71~~ — RESOLVED: Lily re-judged the crop on 2026-07-27. It IS an
   advisory 25. The agent was right and the GT was wrong; eval_set_100.json
   corrected. This removed one FP from every attempt.

### Next

Attempt 2 (prompt-only change): tell the agent (a) the target sign is the
centered sign in the crop; neighboring signs above/below belong to other
annotations, (b) a partially visible sign at the crop edge may still be a
speed sign — judge from visible evidence.

## Attempt 2 (framing rules in prompt)

Change: INSTRUCTIONS gained two framing rules — judge only the centered sign
(neighbors belong to other annotations), and partially visible signs at crop
edges still count as evidence. No tool or code-path changes otherwise.

### Results

103 items, 103 verdicts:

- detection: TP=53 FP=2 FN=1 TN=47
- **precision 0.964, recall 0.981, F1 0.972** (vs attempt 1: 0.981 / 0.981 / 0.981)
- number accuracy on TP: 52/52 = 1.000

### Error analysis

Not an improvement. The framing rules did not fix #302 (agent still answered
the neighbor's "30" circle — a prompt cannot disambiguate which sign the bbox
meant) and the "judge from partial evidence" rule added a hallucination:
FP #76 (a plain warning triangle, no digits) got "advisory_0". Prompt-only
fixes have hit their limit; the #302 class of error needs a better tool, not
better words.

### Next

Attempt 3: revert to attempt-1 wording (keep only the center-target rule,
drop the over-eager edge rule), and make view_sample serve a tighter,
center-weighted crop so the neighbor sign is mostly out of frame.

## Attempt 3 (tight crop + simplified prompt)

Changes:
- tools.py view_sample: center-crops the pre-generated padded crop to the
  central 65% before serving, so the annotated sign dominates the frame and
  neighbors (like #302's "30" circle above the 15t target) fall out of view.
- tool_router.py INSTRUCTIONS: back to attempt-1 text plus one line —
  "judge the CENTERED sign; do not answer for signs at the frame edges."

### Results

103 items, 103 verdicts:

- detection: TP=39 FP=1 FN=14 TN=49
- **precision 0.975, recall 0.736, F1 0.839** (vs attempt 1: 0.981 / 0.981 / 0.981)
- number accuracy on TP: 38/39 = 0.974

### Error analysis

Big recall regression. The 65% center-crop fixed #302 (the only FP left is the
GT-questionable #71) but cut off 14 real speed signs. Failure pattern: small
advisory plaques mounted under big warning diamonds sit BELOW the crop center,
so the center-crop trimmed them out (#60, #92, #93, #168, #305, #306, #400);
same for stacked sign assemblies (#211, #215, #220, #256, #195). The padding in
the pre-generated crops was load-bearing for off-center targets.

### Next

Attempt 3 reverted. Attempt 1 config (full padded crop, plain instructions)
is the keeper: F1 0.972, with residuals #302 (1 real FP), #71 (GT disputed),
#137 (cut-off sign, legitimately hard). A crop that adapts to target size
rather than a fixed center window might beat it, but the fixed 0.6-pad crop
plus VLM is already at 3 errors / 103.

## Summary (3 attempts)

| Attempt | Change | Precision | Recall | F1 | Errors |
| :-- | :-- | --: | --: | --: | --: |
| 1 | baseline, full crop | 0.981 | 0.981 | **0.981** | 2 |
| 2 | prompt framing rules | 0.964 | 0.981 | 0.972 | 3 |
| 3 | 65% center crop | 0.975 | 0.736 | 0.839 | 15 |

Keeper: attempt 1. Residuals: #302 (1 FP, neighbor-sign ambiguity) and
#137 (FN, sign physically cut off in source image). #71 resolved as an agent
catch: GT was wrong, agent was right.

Lessons:
1. Number reading was never the bottleneck (100% accuracy on TPs in attempts
   1-2). Errors are about WHICH sign to judge, not what it says.
2. Prompt changes can't fix frame-level ambiguity; tool changes can, but a
   blunt center-crop costs more recall than it buys precision.
3. One GT error found by the agent (#71) — the eval loop doubles as a GT
   audit, same as the manual rounds.

## Attempt 4 (orchestrator, cheap tools, VLM gated)

Lily's steering: the agent should be an orchestrator, not a VLM classifier.
Perception belongs to cheap tools; the LLM picks tools and reasons over
structured evidence.

Changes:
- cheap_cv.py: tesseract OCR with a 5-threshold sweep + digit whitelist
  (numbers carry vote counts), unit hints (tonnes / meters / MPH), and a
  color profile (yellow / red / white / grey fractions). Free, local, ~1s.
- tools.py: new `analyze_sign` tool (wraps cheap_cv). `view_sample` kept but
  documented as gated and expensive.
- tool_router.py: the ESCALATION DECISION LIVES IN CODE, not in the LLM.
  If cheap evidence has a plausible speed number, the agent decides from
  evidence; if not, the prompt orders it to call view_sample before judging.
- Lesson folded in from smoke tests: "absence of OCR output is a reason to
  look, not a verdict" — silence defaulted to negative until gating was made
  deterministic.

### Results

103 items, 103 verdicts (8-way parallel, ~2 min wall clock):

- detection: TP=51 FP=8 FN=3 TN=41
- **precision 0.864, recall 0.944, F1 0.903** (vs attempt 1: 0.981 / 0.981 / 0.981)
- number accuracy on TP: 39/51 = 0.765

### Error analysis

Regression vs attempt 1. Root causes, in order of damage:
1. OCR ghost digits. The threshold sweep emits single-vote noise, mostly a
   phantom "5" (8 of the number errors are *_5). The agent trusted
   single-vote numbers.
2. Unit hints ignored: #73 (30m length limit) became end_of_speed_limit_30.
3. #302 FP for the fourth time: the neighbor's "30" is real evidence in the
   crop, cheap tools cannot tell which sign the bbox meant.
4. Two contradictory verdicts (is_speed_limit=true with
   fine_label=not_a_speed_limit) — the rubric lets the agent disagree with
   itself.

Verdict: orchestration structure is right, but the cheap tool's evidence is
too noisy to beat the VLM baseline. Next: de-noise the OCR evidence
(votes>=2 for candidates, drop phantom digits, weight vote share), tighten
the unit-hint rule, and make fine_label consistent with is_speed_limit in
submit_verdict itself.


## Attempt 5 (Kimi K2.5 orchestrator + de-noised evidence)

Changes: model swapped gpt-4o-mini -> Kimi K2.5 via OpenRouter (litellm
extension, images pass through). Evidence hardened: numbers need
trusted=votes>=2, unit hints are a hard veto, submit_verdict enforces
label/verdict consistency.

### Results

103 items, 103 verdicts:

- detection: TP=48 FP=2 FN=6 TN=47
- **precision 0.960, recall 0.889, F1 0.923** (vs attempt 1: 0.981 / 0.981 / 0.981)
- number accuracy on TP: 46/48 = 0.958

### Error analysis

Better than attempt 4 (0.903), still below attempt 1. The trusted=votes>=2
rule killed the phantom 5s (FP 8 -> 2) but also suppressed real numbers on
hard crops: 5 of 6 FNs are cases where the sign is real but the OCR never
reproduces the digit twice, and the code gate then withholds the VLM
escalation. Phantom-free but over-conservative.

Note: per the quantification goal (find issues, not fix), number accuracy is
secondary; the F1 gap is mostly a recall story.


## GT correction #2: #137 is not a speed limit at all

Lily spotted that #137 reads 43, not 45. Zooming the full frame: it is a pair
of M-43 route markers (EAST/WEST) with direction arrows — Michigan highway
shields, exactly Ben's mode-2 "numbered non-speed-limit" case. GT corrected
(regulatory-45 -> not_a_speed_limit). Attempt 1 recall becomes 1.000:
TP=52 FP=1 FN=0, precision 0.981, **F1 0.991**, one residual error (#302).

This is the second GT error caught through the agent loop (#71 was the
first). The eval set itself is being audited by the process.

## ATIF-style traces

tool_router.py now writes data/traces/<id>.json per item: reasoning summaries,
tool calls with arguments, tool outputs (incl. images), and the final
verdict. Debug path: open the trace, find the first step where the reasoning
diverges from the evidence.


## Attempt 6 (binary verdicts: is_speed_limit + is_numbered)

Per Lily: the task is to quantify mislabeled instances and attach the
is_numbered attribute, not to fix labels. fine_label dropped from the schema.

### Results

103 items, 102 verdicts:

- is_speed_limit: TP=49 FP=1 FN=4 TN=49 — **P 0.980, R 0.925, F1 0.951**
- is_numbered (GT: 62 numbered / 103, negatives hand-labeled by agent review):
  TP=60 FP=11 FN=2 TN=30 — **P 0.845, R 0.968, F1 0.902**

### Error analysis

Binary judgment beat attempt 5 as expected: no number reading required, so
recall recovered 0.889 -> 0.925. Remaining FNs are dark/faded signs.

is_numbered over-marks: 11 FPs on unnumbered signs (arrow boards, warnings).
The agent seems to treat arrow shafts and pictograms as digits. Needs a
stricter rule: a number must be readable, not inferred. One GT judgment call
noted: #193 (bus stop with route-number plate) marked numbered by reviewer;
the agent said no. Borderline.

## PaddleOCR integration (cheap tool upgrade)

tesseract replaced by PaddleOCR (PP-OCRv6) as the primary OCR, via subprocess
bridge into a separate py3.13 venv (paddlepaddle has no py3.14 wheel).
Tesseract sweep kept as fallback. A/B on the hard cases tesseract failed:
#164 "45 MPH" conf 1.0, #37 "SPEED LIMIT 40" all ~1.0, #302 reads BOTH the 30
and the 15t (first time the two-sign evidence is complete), #76 clean empty.
Conf >= 0.9 counts as 2 votes toward `trusted`.

## Attempt 7 (pure-code detector: 3-pass PaddleOCR + cross-pass rules, $0)

Question from Lily: can we build tools that make the two binary tasks very
accurate, without the LLM in the loop?

Tool built: `detector_ocr_rules.py` — no LLM, no network, deterministic.
Evidence = three cached PaddleOCR passes per crop (base, 4x+autocontrast,
8x), produced once by `scripts/batch_paddle_*.py` (8x ran 6-way parallel).
Splits regenerated to cover all 131 items (dev 92 / holdout 39, seeded).
Scorer: `scripts/score_binary.py` (both tasks, any split).

### Rules that mattered

- **Cross-pass agreement** is the precision engine: a bare plausible number
  counts only if >= 2 of 3 passes read it. Route-marker/hallucinated numbers
  ('55' shield #158, '130' plate #46, '11' on blank #134) appear in one pass
  only; real circles ('90', '40', '25') survive upscaling.
- **Upscale-only rescue**: on base-blind crops, a single high-conf number
  found at 4x/8x is real (#168 '65', #778 '25', #71 '25', #746 '40'). The
  reverse (base-only, lost on upscale) stays negative.
- Speed words (SPEED/LIMIT/MPH/km/h) + number => yes; physical units
  (30 m, 3,5t, A100m, 4.7 m) and context words (STOP/LANE/TURN/frei) => veto.
- Color/shape was tested and REJECTED: crops too small/faded — HSV red-ring
  frac is 0.0 on true circles and 0.3 on some negatives.

### Results (vs attempt 6 LLM agent: speed F1 0.951, numbered F1 0.902)

- dev (92):     is_speed_limit P 1.000 R 0.917 **F1 0.957** | is_numbered P 1.000 R 0.922 **F1 0.959**
- holdout (39): is_speed_limit P 0.950 R 0.905 **F1 0.927** | is_numbered P 1.000 R 1.000 **F1 1.000**
- all (131):    is_speed_limit P 0.984 R 0.913 **F1 0.947** | is_numbered P 1.000 R 0.944 **F1 0.971**

The $0 detector beats the LLM agent on is_numbered (+0.069) and matches it
on is_speed_limit (-0.004) with strictly better precision. It also runs in
milliseconds from cache vs minutes + API cost per run.

### Residual errors — all one failure mode

Every remaining FN (#50, #170, #171, #175, #178, #456) is a crop where no
OCR pass reads a usable number: dark/faded/tiny circles. The single FP
(#302) is the long-standing case of a real 30 circle next to a 15t plate
that GT calls not_a_speed_limit — same call the LLM agent makes; possible
GT judgment call.

### Implication for the design doc (3.1.4 tool table)

Cheap OCR rules get ~0.95/0.97 alone. The gap to ~1.0 is exactly the
OCR-blind residue — which is what the production online patch classifier
(fine-tuned on internal data, sees pixels not text) should cover. Proposed
composition: OCR-rules detector first (free, precise), escalate only
OCR-blind crops to the patch classifier / VLM judge. That is the 1+1>2
orchestration story with a measured boundary between the tools.
