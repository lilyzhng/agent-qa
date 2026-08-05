# agent-qa

Agentic label-QA MVP (traffic signs). Per-item agent loop built on the OpenAI Agents SDK.

## Layout

- `aqua_mvp/` — the agent: tools, per-item router, detectors, eval. See `aqua_mvp/README.md`.
- `traffic_signs/clean/` — curated GT (`eval_set_100.json`, read only by eval, never by the agent).
- `traffic_signs/review/crops/` — 552 sign crops the agent views.
- `traffic_signs/review/*.json` — label rounds and candidates from curation.

Full-resolution source images (Mapillary MTSD, ~800M) are not in this repo; nothing in `aqua_mvp` needs them.

## Quickstart

```bash
cd aqua_mvp
python3 -m venv .venv && .venv/bin/pip install openai-agents python-dotenv
echo 'OPENAI_API_KEY=sk-...' > .env
.venv/bin/python corrupt.py       # build data/corrupted_labels.json from GT
.venv/bin/python tool_router.py   # full agent run
.venv/bin/python eval.py          # score vs hidden GT
```
