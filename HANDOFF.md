# Handoff: Aqua QA Agent → av (Bazel) integration

**For:** the next agent picking this up on Lily's work machine.
**State as of 2026-08-06.** This repo is the one-way transfer vehicle for the Aqua label-QA agent from Lily's personal machine into the work monorepo (`av`). Once the code lands in av, av is the source of truth — do not sync work-side changes back here. Archive this repo after the av PR merges.

## What this repo contains

- `aqua_mvp/` — the current agent generation (OpenAI Agents SDK, per-item tool-calling loop): `tools.py` (`list_items` / `view_sample` / `submit_verdict`), `tool_router.py` (the loop, currently gpt-4o-mini), `corrupt.py` (build corrupted labels from GT), `eval.py` (P/R/F1 + number accuracy vs hidden GT), detector scripts, `iteration.md` / `report.md` (attempt log + baseline numbers).
- `traffic_signs/clean/` — curated GT (`eval_set_100.json`); read ONLY by eval, never by the agent.
- `traffic_signs/review/crops/` — 552 sign crops the agent views. Public Mapillary MTSD data.
- Excluded on purpose: `.env` (recreate; only `OPENAI_API_KEY` locally), venvs, full-res images (~1.3G, nothing here reads them), older prototypes, work notes/design docs (those live in Lily's vault: `lily-memory/2026/DayJob/latitude/label_qa/`, esp. `design.md`).

## Work-environment context (learned via Slack threads, verify against current state)

- av is a Bazel monorepo. LLM access goes through the FordLLM proxy (`https://llm.bluel3.tools/v1` per Mrigesh's sketch) with LIAM JWT auth via `kits/openai` (`llm_proxy_auth.resolve_liam_jwt()`). Internal models served on internal clusters behind the same OpenAI-compatible protocol.
- **Dependency saga:** Dagster pins pydantic <2.10 repo-wide; stock `openai-agents` needs pydantic 2.11 APIs, `openai>=2.45`, `mcp>=1.19`, `websockets>=15` (repo: pydantic 2.9.2, openai 2.41.1, websockets 10.4). No openai-agents release fits the pin. Resolution: **patched wheel via wheel builder** (Alex K / Dillon K), with MCP and realtime/websocket support STRIPPED, pydantic relaxed to >=2.9.2. Streaming (SSE via openai client) is kept — it does not use the websockets package.
- Long-term fix: Dagster upgrade (medium project, ~1 month, #ml-platform-support / asmith's team). When it lands, drop the patched wheel for stock openai-agents. The wheel is a frozen bridge — do not chase upstream openai-agents releases on it.
- **VERIFIED WORKING:** `bazel build //kits/openai/agents:hello_world` runs end-to-end through the proxy (joke round-trip, Gemini). So: wheel resolves, LIAM auth passes, SDK loop runs.
- **VERIFIED 2026-08-06:** tool calling (`@function_tool` weather test) AND handoffs both work end-to-end through the proxy, against a GPT (ChatGPT) model. Proxy + wheel + SDK + tool loop all confirmed. Note for later: when Aqua switches to an internal-cluster model, re-run the one-line tool test with that `model=` — GPT passing proves the proxy path, not that model's tool-calling.

## Decisions already made (don't re-litigate)

1. **MCP: not now.** Design doc (`design.md:80`, `:250`) uses MCP as tool transport (shared BigQuery label server, Mrigesh's data-bae) — but that's Phase 2, via stock SDK post-Dagster-upgrade. Q3 path is in-process `@function_tool`s, which is what `aqua_mvp` already does. Design doc should be updated to mark MCP as post-upgrade.
2. **Realtime/websockets: never needed** (voice-agent infra; Aqua has no voice surface).
3. **Required SDK settings** (belong in `kits.openai.agents` client setup, verify they made it in): `set_default_openai_client(<LIAM client>)`, `set_default_openai_api("chat_completions")` (proxy has no Responses API), `set_tracing_disabled(True)` (tracing phones home to OpenAI).
4. First av PR scope: agent + single `py_binary`, FordLLM-only tested path (Vertex AI reachable via env override but out of scope). Env-var toggle (`LLM_BASE_URL`, `ACCESS_TOKEN`) kept.

## Next steps, in order

0. **[DONE 2026-08-06]** Function calling + handoffs verified end-to-end through the proxy with a GPT model. Deferred check: when Aqua later switches to an internal-cluster model, re-run this test with that `model=` first — if it fails tool calling (serving disabled / model not trained for it), stop and escalate before continuing.
1. Port `tools.py` + `tool_router.py` only. Swap auth: delete `.env`/`AsyncOpenAI` setup, use the `kits.openai` client per hello_world's pattern; change model string to the internal model.
2. Bazel-ify: `py_binary` + `BUILD` in the team dir, mirroring hello_world's `BUILD`; deps = patched openai-agents target + kits/openai.
3. Run ONE item end-to-end (agent views a crop, submits a verdict). That's the milestone.
4. Then `corrupt.py`, `eval.py`, detectors, and data. Smoke test with data on local disk via path flag; proper data home (repo test-data vs blob storage vs BigQuery) is a PR-review question.
5. PR with eval numbers: run the 100-item eval, compare internal model vs the gpt-4o-mini baseline in `report.md`.

## Phase: internal data via BigQuery / data-bae (next after the port)

The repo has NO SQL/data-pull functions — all tools read local JSON + crops (Mapillary stand-in). To test on internal traffic-sign data:

- Use **data-bae** (Mrigesh) as plain Python / raw queries, NOT its MCP-server packaging (MCP is stripped from the wheel). Ask Mrigesh for the direct access path.
- Build `data_source.py` adapter behind the existing tool interface, keeping local data as default (`--source=bigquery` flag) so the working loop never breaks:
  - `list_items(dataset_tag)` → SQL on autolabel/cache-label tables, emitting the same item shape tools.py uses today.
  - `view_sample(item_id)` → needs image fetch + bbox crop: labels reference full frames in blob storage; find where frames live and whether pre-cropped patches are cached.
  - Schema mapping internal taxonomy → Aqua's fields (class, bbox, sign value). This is the real work, not the SQL.
- Eval caveat: internal data may have no curated GT — first internal run is qualitative (verdicts sane on N items), not P/R/F1.
- Before writing code: verify BigQuery read permission with one manual SELECT from the workstation.

## Open questions (carry into work threads)

- **Headless auth:** how do batch/cluster jobs get a LIAM identity (no human SSO)? Ask Mrigesh — needed before any sandbox/cluster launch. (Sandbox launch does NOT need MCP; function tools run in-process. Only needs egress + creds to proxy/BigQuery/storage.)
- **kits/openai portability:** if the outside-av option ever revives, how thick is `resolve_liam_jwt()`? (Integration surface is process-shaped — nothing in av needs `import aqua` — so outside-av is viable except for this dependency.)
- **Dillon's pin-relax experiment:** relaxing pydantic pin without upgrading Dagster — did anyone run it? If it works, no wheel needed.
- **Dagster upgrade ticket:** confirm filed with Q3 QA-agent milestone as justification; it's the kill-switch for the patched wheel.
- Model-name format on the proxy (e.g. `google/gemini-1.5-flash` style) for the internal model — check what hello_world's model registry expects.

## Quickstart (local run, this repo, no work infra)

```bash
cd aqua_mvp
python3 -m venv .venv && .venv/bin/pip install openai-agents python-dotenv
echo 'OPENAI_API_KEY=sk-...' > .env
.venv/bin/python corrupt.py && .venv/bin/python tool_router.py && .venv/bin/python eval.py
```
