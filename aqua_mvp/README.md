# Aqua MVP

Minimal agentic label-QA loop, following the design doc (`../design.md` 3.1.2 / 3.1.4).

- `corrupt.py` — turn curated GT into `data/corrupted_labels.json` (everything → `other_sign`)
- `tools.py` — agent tools: `list_items`, `view_sample`, `submit_verdict`
- `tool_router.py` — per-item agent run (OpenAI Agents SDK, gpt-4o-mini)
- `eval.py` — score predictions vs hidden GT (detection P/R/F1 + number accuracy)
- `iteration.md` — attempt log

Usage:

```bash
python3 -m venv .venv && .venv/bin/pip install openai-agents python-dotenv
.venv/bin/python corrupt.py
.venv/bin/python tool_router.py        # full run
.venv/bin/python eval.py
```

`.env` holds OPENAI_API_KEY (gitignored). GT at `../traffic_signs/clean/eval_set_100.json`
is read only by eval.py — the agent never sees it.
