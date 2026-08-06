# Aqua QA Agent: Next Steps (discussion doc)

Working doc for deciding what to do next. Correct anything wrong, add notes inline.
Facts below are marked: [verified] = seen working or confirmed by Lily, [inferred] = my read, may be wrong.

## Where we are

- [verified] Patched openai-agents wheel builds in av. `bazel build //kits/openai/agents:hello_world` runs through the FordLLM proxy.
- [verified] Tool calling and handoffs work end to end via the proxy, tested with a GPT model.
- [verified] agent-qa repo (this repo) holds the MVP: per-item tool loop, local Mapillary crops, local eval with GT.
- [verified] Traffic signs are one object class inside the general object-label tables in BQ. No dedicated sign table. We need a query function that filters by class.
- [inferred] data-bae (`great_gadsbq`, data-platform repo) is the existing BQ access layer. Its MCP packaging is unusable for now (MCP stripped from the wheel), but the underlying queries are reusable.
- [inferred] Frames or crops for `view_sample` live outside BQ (LakeFS or blob store). Unconfirmed.

## Candidate next steps (pick and order)

1. Port the agent loop into av: `tools.py` + `tool_router.py`, swap in the kits client, one crop to verdict on local data.
2. Write the BQ query function: find the object-label table, confirm the traffic-sign class enum, `SELECT ... WHERE class = <enum> LIMIT 10`.
3. Build `data_source.py` adapter so the agent runs on BQ items instead of local JSON.
4. Solve `view_sample` for internal data: where pixels live, how to crop.
5. First internal run: N items, qualitative check of verdicts (no curated GT yet).
6. av PR: agent + py_binary + eval numbers.

## Open questions for discussion

- Which step first: port the loop (1) or prove the data path (2)? They are independent.
- What model do we run Aqua on for the first internal test: GPT via proxy, or an internal model?
- Do we need GT on internal data for the Q3 milestone, or is qualitative review enough?
- Who owns the BQ query function: us, or reuse data-bae queries with Mrigesh?
- Where do sign crops come from for internal frames: pre-materialized somewhere, or crop on the fly?

## Notes from discussion

(fill in here)
