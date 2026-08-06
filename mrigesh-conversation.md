# Conversation with Mrigesh

Meeting: QA agent development — tools, MCP server, and HPC deployment
Date: Aug 6, 2026
Participants: Lily Zhang, Mrigesh Kalvani
(Cleaned from Granola transcript. Names and terms corrected: Dagster, pydantic, Dillon, Tesseract, PaddleOCR, LakeFS, data-bae, LIAM. Raw transcript in git history.)

# Summary

- **Repo status:** Dillon patched Dagster to relax the pydantic pin. Lily branched off his branch and tests pass. His PR hasn't landed yet (testing to avoid breaking Dagster). Recommendation: stay in av and chain PRs if his ETA is ~1 week; reconsider moving out if ~1 month. Ask Dillon for the ETA.
- **Architecture agreed:** two-phase model. Offline discovery (current stage): OpenAI Agents SDK loop finds the best cheap deterministic tools against an expensive-LLM baseline. Online: freeze the validated tools, expose them as an MCP server (deterministic, no LLM inside the tools), agent harness on top.
- **Repo decision:** Aqua's MCP tools can live in the data-platform repo (fast CI, no av dependency needed, same pattern as MLTP's app and data-bae itself). An existing agent in that repo can auto-port the av PR into a new tool.
- **Data:** 2D sign labels + image crops live in "sensing segment stage gold" on LakeFS, not BQ. Krishna can register the asset for weekly BQ export. Image bytes in BQ only if small; otherwise store path pointers and resolve from LakeFS.
- **Sandbox/HPC:** everything from data-platform ships as Docker, sandboxed by default. Read access (BQ, LakeFS) easy; write-back (committing generated code) needs 3-4 approvals, impractical. So: run discovery locally with human in the loop, freeze and commit tools via review, deploy frozen tools in Docker.

# Next Steps

- Ask Dillon for a PR landing ETA
- Move MCP tools into the data-platform repo (Lily)
- Contact Krishna to register sensing segment stage gold for BQ export (Lily)
- Try the data-platform repo's agent to auto-port the av PR into a new tool

---

# Conversation

## 1. Should Aqua stay in av or move out? (Dagster/pydantic status)

**Lily:** Initially I was going to meet you about moving the code to another repo, but it seems resolved. Dillon patched Dagster, which relaxed the pydantic pin, and I just branched off his branch. It's working, that's why I showed the test result.

**Mrigesh:** Right. The unknown part is when his PR actually lands. It might take a while, because the hard part is testing the change. If they land it and it breaks something in Dagster, people will get pretty upset.

**Lily:** Should I still move out?

**Mrigesh:** At least it unblocks your development, you can keep working on the branch. We can ask Dillon for an ETA. Getting the requirements file to work is important, but landing the PR is also important.

**Lily:** So would you recommend I move out of av? Nobody is calling the agent yet, but I have some dependency on other tools in av.

**Mrigesh:** In that case, keep working in av and let's get a rough estimate from Dillon. If he says one month, you should probably reconsider. If he says next week, it should be okay. At least you can make a chain of PRs for your tooling.

## 2. How will Aqua be invoked? Copilot, script, or its own harness?

**Mrigesh:** I'd love to understand how it would be used. I don't know anything about the OpenAI Agents framework. Initially I thought the MCP would work with Copilot: I open code, talk to Aqua. Is that true, or will someone write a Python script to call Aqua?

**Lily:** It's very different. Copilot has its own harness that calls tools like grep, edit, etc. I'm building another harness for QA purposes. This harness has tools like zoom in, zoom out, inspect the data. I want to run it in a sandbox on HPC: the agent inspects BQ data plus the crops. Take traffic signs as the example. A sign is supposed to be a speed limit sign but is labeled "other sign". We need to look at the label and the sign itself and fix that. You'd also be able to invoke this agent from Copilot, but I haven't thought much about that.

**Mrigesh:** Let's drill into an example. In your doc, the first box says "user reports one issue". Where is the user reporting it, a web app?

**Lily:** For example, a user reports that a traffic sign didn't get labeled properly: help me find all other cases and fix them. The Aqua agent loads everything including the auto labels, compares different sources, inspects the samples (crop, zoom, enhance), then either proposes the fix to the rework API or fixes it itself. I was thinking of a front end with a chat window where the user reports the issue and Aqua dispatches it.

**Mrigesh:** So figure 5 in the doc is that front end, but not the first step?

**Lily:** Right. At the start we should simplify: invoke it directly in the terminal. Ideally there's a front end, but that raises questions of where to host it and how to design it. The easiest way to get the skeleton working is the terminal.

**Mrigesh:** Agreed. Making and even hosting a front end is not hard, but I'm thinking of this project in incremental chunks: first the tools, then the interfaces.

## 3. Why an agent at all? The offline tool-discovery loop

**Mrigesh:** Is there a reason not to start by building just an MCP server? That way it won't be an agent, just a list of MCP tools used through the existing harness (Copilot). Once the tools work, if the existing harness isn't good enough, then invest in the OpenAI Agents framework running the same thing in a deterministic loop.

**Lily:** The MCP server works when you have known tools giving known outputs. The issue for the QA agent is we start from zero, we don't have any tools. What I'm doing now: I use another LLM (GPT-5 or Opus) as a baseline to fix everything, and measure its recall and precision. Then I run an agent loop to automatically discover a cheap alternative: without the expensive LLM, can you build deterministic tools like OCR detectors that match the performance? That discovery stage has to be an agent loop with reflection, it can't be me doing everything manually.

For example, in the results: at iteration 6 the agent switched from Tesseract to PaddleOCR because it realized the better OCR improves performance. From attempt 6 to 7 it added cross-pass agreement between two OCRs, and kept pushing to find the best solution.

**Mrigesh:** And this seven-attempt loop, you ran it with OpenAI Agents, not Copilot?

**Lily:** Exactly, I basically made an OpenAI agent.

**Mrigesh:** What are the UI screenshots in figure 4?

**Lily:** That's a front end I built for human label QA. The original labels have lots of noise (e.g. a "120" mislabeled as 75), so I went in and cleaned all the labels myself to get a clean GT. The agent doesn't need this UI, it's mainly to keep the human in the loop: quickly triage correct/wrong.

**Mrigesh:** Got it. So 4a is to hand-label and filter the misclassifications, and 4b takes the misclassifications and asks how to fix them automatically: OCR instead of an expensive VLM, two different OCRs with cross-pass agreement.

**Lily:** Basically it's auto-research. I set up a GT, a goal (cost control plus precision/recall), and the agent ran for a few hours to find the best solution.

## 4. Two-phase model: discovery loop now, frozen MCP tools later

**Lily:** So maybe two things. Offline: the QA discovery stage where we find the best tools (the stage I'm showing now). Once we settle that, online: expose the tools as MCP. What do you think?

**Mrigesh:** Yeah. And the benefit is that when the agent makes a new tool, say an OCR tool, it comes into the repo and gets code review.

**Lily:** Same here: any tool generated by this agent loop gets committed as Python code and reviewed. Everything follows the Agents SDK schema, so it's deterministic and you have more control. And the loop isn't fixed steps. It's a few primitives the agent can use. Think of a CLI agent: its primitives are grep and glob. For QA, the primitives are view sample, compare sources, crop, zoom in, load labels, propose, judge. Agents have limited context windows. If you give them hundreds of tools they get lost using the wrong tool, which is Copilot's issue right now with so many tools and skills. Restricting the agent to QA-related tools makes accuracy much higher.

**Mrigesh:** Makes sense. It's like a third-party auto-research optimizing two things: minimize cost, maximize detection metrics.

## 5. Which repo? Why data-bae lives outside av

**Mrigesh:** I'm still thinking about whether there's a reason to be in av. What you need from av is tools like the LakeFS reader to pull data.

**Lily:** Why did you put data-bae outside av in the first place?

**Mrigesh:** Within av, development is very slow. In our repo, CI takes two minutes. In av, CI takes an hour if you're lucky, and CI plus Bueller is two hours best case. Most offboard teams do 5-10 PRs a day per person because the loop is smaller. And you can still use data-bae inside av, there's no reason you can't use it anywhere, since it's an MCP server.

**Lily:** So maybe I can do the same: start my own repo, build the Aqua QA agent there, expose it as MCP.

**Mrigesh:** The catch: if you need av code, you're back to copying code. The good thing about data-bae is it has zero dependency on av, only on the BigQuery stuff.

**Lily:** Right now the only av thing I need is the LIAM client you showed me.

**Mrigesh:** That part we can easily move.

**Lily:** Can I push the code into the data-platform repo?

**Mrigesh:** For sure, no objection. We just added apps for several teams, e.g. MLTP has their Streamlit app inside this repo now. If every one of your MCP tools has no av dependency, you're good. All my MCP tools only depend on BigQuery and data things, nothing on av. Also, Alex has a similar PR up adding the same kind of thing (also waiting on the pydantic update). And here's the good news: the data-platform repo has agents set up correctly. If you literally tell the agent to take your existing av PR and port it over as a new tool, following the repo's tool conventions, it should just work. I'm pretty confident it would make exactly the right thing.

## 6. Where does the LLM live? (data-bae architecture)

**Mrigesh:** The difference is where the agentic logic lives. In data-bae, the only part with an LLM is the harness. Everything in the MCP is deterministic tools: a discovery tool to find the best tables/columns for a question, a tool that gives stats and expected values for columns, caching, and so on. No LLM in the MCP server itself. The agent decides: what tools are available, let me check more tables, let me run a query and look at the output.

**Lily:** So the tools have no LLM, only the loop around the tools has the LLM. That's very helpful. Same will be true for Aqua.

## 7. Getting traffic-sign data: LakeFS to BQ export

**Lily:** Second question. I need a data source to fetch traffic-sign datasets from BQ. I found BQ only contains 3D. There's data from the onboard team on LakeFS called **sensing segment stage gold** that contains the 2D sign labels, which is what I want, plus the image crops. I want to stay on BQ since it's much lighter for the agent to interact with, but this table doesn't exist on BQ. Can I push this data to BQ?

**Mrigesh:** Should be pretty easy. There's a registry where you put which assets to sync to BQ, and every week it makes an export for that asset. **Krishna is the guy.** Right now BQ has about four assets from LakeFS: human label, pseudo, the HULK cuboids, log slices, and some auto-label thing. Except for human label, none of them have labeled signs, and none have crops.

**Lily:** Is it legitimate to ask Krishna to also push the image bytes to BQ?

**Mrigesh:** Depends how big. If you know the slice ID and exact path, you can store the path pointer instead of the bytes, and your image-reading tool resolves the path from LakeFS. If the bytes aren't very expensive, it's fine to put them in BQ. But if you're getting every frame in HD, that's terabytes per week, and then pointers are better.

**Lily:** Makes sense. I'll check how big the data is. Maybe I can fetch all the image crops locally: QA repeatedly checks image labels, so pointer-resolution every time doesn't make sense, there should be a caching mechanism. Then when we run the agent on HPC the data is already there, so it's fast.

## 8. Running the agent in a sandbox on HPC

**Lily:** Last question: how do I run this agent in a sandbox on HPC?

**Mrigesh:** If you go through data-platform, everything is sandboxed by default because what it builds for you is a Docker image, whether you run locally or on HPC. The annoying part is permissions: the sandbox has very limited access, and adding access is painful. BigQuery is easy to grant. But as soon as you need write access from the sandbox it becomes hard. If the tool needs to write back, like committing a generated tool, you'd need three or four different approvals to write to GitHub.

**Lily:** So the agent should do the discovery with a human in the loop, and freeze the tools when we deploy?

**Mrigesh:** Yes, that's why I proposed it that way. Do discovery locally: it has all the permissions you have, and it's still somewhat sandboxed (you can put it in Docker so it won't delete everything). When it makes code, you commit that code: "here's the tool we made." Then the frozen tools deploy via Docker.

**Lily:** That makes a lot of sense.

## 9. Wrap-up

**Lily:** This is super helpful. When do you sign off today?

**Mrigesh:** I'll be around for an hour, then on and off before the break. And like I said: take that agents file, tell the data-platform agent "move this code over so the same demo runs in the repo's agent loop," and it should make exactly the right thing.

**Lily:** That's actually a very good idea. Thank you, Mrigesh. Really enjoyed the conversation, I'm learning a lot.

**Mrigesh:** Same here. Catch you around.

---

# Discussion

## Everything discussed with Mrigesh

| # | Topic | Mrigesh's take | Status / decision | Action owner |
|---|-------|----------------|-------------------|--------------|
| 1 | Stay in av or move out | Stay in av on Dillon's branch, chain PRs. Reconsider only if his PR ETA is ~1 month | Open, blocked on Dillon's ETA | Lily asks Dillon |
| 2 | How Aqua is invoked | Incremental: terminal first, front end later. Copilot invocation possible but not now | Decided: terminal first | - |
| 3 | Why an agent loop (vs plain MCP tools) | Accepted Lily's rationale: no tools exist yet, discovery loop finds cheap deterministic tools vs GPT-5/Opus baseline | Decided: keep discovery loop | - |
| 4 | Two-phase model | Endorsed: offline discovery now, freeze validated tools as MCP server later. Generated tools get committed + code reviewed | Decided | - |
| 5 | Which repo for Aqua's MCP tools | data-platform repo, like data-bae and MLTP's app. Fast CI (2 min vs 1-2 hr in av). Works if tools have no av dependency. Only av need is the LIAM client, which is easy to move | Decided: data-platform | Lily |
| 6 | Auto-porting the av PR | data-platform repo's agent can port the av PR into a repo-convention tool automatically | To try | Lily |
| 7 | Where the LLM lives | data-bae pattern: MCP tools fully deterministic, LLM only in the harness loop | Decided: same for Aqua | - |
| 8 | Getting 2D sign data into BQ | Labels + crops are in sensing segment stage gold on LakeFS. Krishna registers assets for weekly BQ export. Bytes in BQ if small, else path pointers resolved from LakeFS | Open: contact Krishna, size the crops | Lily |
| 9 | Crop caching | Lily: fetch crops locally / cache rather than resolve pointers every time. Mrigesh: pointers fine, tool resolves path | Open: decide after sizing | Lily |
| 10 | Sandbox on HPC | Docker by default, already sandboxed. Read access easy, write-back needs 3-4 approvals | Understood, constraint accepted | - |
| 11 | Discovery vs deployment permissions | Discovery locally with human in the loop (full permissions), freeze + commit tools, deploy frozen tools in Docker | Decided | - |

## Conversation 1: How is Aqua invoked? (table row 2)

The question bundles two different products. "Who is the agent loop?" has exactly two answers:

**Option A: Aqua's own loop (OpenAI Agents SDK harness)**
- Aqua is a program. You run it: terminal, cron, HPC job, with a dataset tag
- It churns through items with its restricted QA tools and writes verdicts
- Nobody talks to it. This is what "invoke via terminal" meant in the meeting, and what aqua_mvp already is
- This is the batch door. The Q3 milestone (QA a whole dataset tag, thousands of items, deterministic, on HPC) needs this loop

**Option B: An existing chat harness's loop (Copilot at work, Claude Code at home)**
- Aqua stops being an agent and becomes a toolbox: MCP tools (view_sample, load_labels, propose_fix) that Copilot's LLM drives while a human chats
- This is what Mrigesh meant by "the agent won't actually be an agent, it'll just be a list of MCP tools"
- Key unlock: this IS the frontend. The design doc's chat window where a user reports a sign issue already exists: Copilot is a chat window on every engineer's machine that consumes MCP servers. Zero frontend work
- Wrong tool for batch: sprawling toolset, no determinism guarantees (Lily's own argument from the meeting)

**Resolution: not either/or. Two doors into the same tools**
- Copilot + MCP tools = interactive door: seeded issue triage, demos, stakeholders poking at it
- SDK loop as CLI = batch door: the Q3 deliverable. Same tool implementations underneath (two-phase model)
- Current state: Claude Code as discovery-stage harness is fine, discovery is local and human-in-the-loop anyway (row 11)
- Recommendation: ship the MCP server + Copilot door first. Smaller (tools only, no loop porting), works in data-platform today without the wheel, gives Mrigesh and others something to touch. Batch loop reuses the same tools after
- Open: does the Q3 milestone wording require the batch run, or does the interactive door count?

## Conversation 2: av or data-platform? (table rows 1 and 5)

- Reasons to stay in av: closer to existing information and features (online team, PAD team). But honestly nothing is needed from them: data comes from BQ, and the agent can be pointed at av tools when needed
- Dillon's ETA (followed up): he will try his best to land next week, but it looks like it will take a long time
- Key technical point: the whole pydantic/wheel saga is an av-only constraint. data-platform has no Dagster pin. data-bae itself runs as an MCP server there on modern deps. In data-platform, stock openai-agents likely works, MCP included, no patched wheel
- To confirm with one command in the data-platform env: pip install openai-agents
- Lily's lean: put everything under data-platform. Faster than waiting on av

## Conversation 3: Specialized agent vs Copilot directly (research-backed)

Mrigesh asked: what is the difference between invoking the Aqua agent vs just doing it with Copilot? Lily answered: Aqua's tools are QA-specific, Copilot's harness has so much other information that the agent gets confused. Research verdict: **legit and empirically supported, but it is one of four reasons, and not the strongest one for Aqua.**

**The tool-confusion claim is true, with numbers**
- ~50 tools: 84-95% selection accuracy. ~200 tools: 41-83%. ~740 tools: 0-20%
- Berkeley Function Calling: 43% -> 2% going from 4 to 51 tools
- Production rule of thumb: degradation starts past ~15-20 active tools. Plus position bias and tool hallucination
- Anthropic's tool-writing guidance: be selective, small high-leverage toolsets

**What Lily is building = a harness**
- Agent = model + harness. Harness = the loop (prompt -> LLM -> execute tools -> feed back -> repeat), tool registry, system prompt, state, stopping conditions, permissions
- Copilot/Claude Code are general harnesses for software engineering. aqua_mvp is a purpose-built QA harness: same loop, QA-only tools, own eval
- The harness is a known performance lever: same model scores very differently in different harnesses

**Standard industry pattern**
- Literature splits coding agents into specialized (SWE-agent, AutoCodeRover, RepairAgent) vs general platforms (Claude Code, Copilot, Cursor)
- Narrow-scope agents win when you need repeatability and precision. Generalists "mix intents and misuse tools" on high-precision tasks

**The complete answer to Mrigesh, four differences ranked for Aqua**
1. Determinism and repeatability: batch QA over thousands of items must behave the same every run. Copilot has no such contract
2. Evaluability: fixed P/R/F1 eval vs hidden GT is how attempt 6 -> 7 was proven. You cannot regression-test "chat with Copilot"
3. Cost and control: own loop controls model, token budget, per-item ceiling
4. Tool focus (Lily's original answer): true but most attackable alone, since scoped per-session MCP tools partially fix Copilot confusion. Hence two doors: Copilot + scoped MCP tools for interactive, specialized harness for batch/eval

**Caveat:** some benchmarks show general agents beating specialized ones on unseen requirements. Keep Aqua's scope truly narrow (label QA, not data quality in general), let the interactive door handle open-ended cases.

Sources: [tool-count degradation study](https://arxiv.org/html/2605.24660v1), [Anthropic: writing effective tools for agents](https://www.anthropic.com/engineering/writing-tools-for-agents), [Databricks: what is an agent harness](https://www.databricks.com/blog/ai-harness), [Addy Osmani: agent harness engineering](https://addyosmani.com/blog/agent-harness-engineering/), [tool selection at scale](https://tianpan.co/blog/2026-04-09-tool-selection-problem-agent-tool-routing-at-scale)

## Conversation 4: Does MCP-first conflict with building our own harness later?

Question: if we build an MCP server and Copilot invokes it, we have no harness at all. If a specialized harness beats a general one, do the two paths conflict? Can we still build the specialized harness later?

**Answer: no conflict. Harness and tools are different layers, MCP is just packaging for the tool layer.**

Three-layer structure:
1. **Tool logic**: plain Python functions (view_sample, load_labels, paddle_ocr_detect, propose_fix). All real work lives here. Knows nothing about MCP or the SDK
2. **MCP server**: thin adapter exposing those functions. What Copilot drives. Exactly how data-bae is built: deterministic tools, zero agentic logic inside
3. **Specialized harness**: the OpenAI Agents SDK loop, added later, consuming the SAME tool logic. Either import the functions as @function_tools (what aqua_mvp does today) or connect to our own MCP server as a client (the SDK is MCP-native, which is why the design doc chose it)

Consequences:
- MCP-first = "tools first, harness second", not "MCP instead of harness". Nothing gets thrown away
- The discovery harness (SDK loop, local) keeps running in the meantime. Only the production batch harness is deferred
- When Q3 forces the batch harness, it is a small PR: loop + system prompt + eval around already-reviewed tools
- Sequencing is forced by constraints anyway: batch harness needs the SDK (wheel-blocked in av, stock in data-platform), MCP server needs neither and ships the interactive door now

**One real trade-off**: chat-harness tools want verbose self-explanatory returns, batch-loop tools want lean token-efficient returns. Keep layer 1 structured and lean, let the MCP adapter add friendly framing. Do not bake chat verbosity into layer 1

**Decision: build order = tool library -> MCP door (Copilot) -> batch harness (SDK loop)**

## Conversation 5: Online tool generation, storage, and permissions (research-backed)

Plan agreed: MVP = freeze the 7-iteration tools -> build MCP -> user-invokable. Agent loop stays offline for tool discovery, comes online later. Question: how does industry handle online tool generation and the write-permission conflict? Is the open-loop design (agent logs feedback to SQL, tools created offline) the right one?

**Q1: When do people allow online tool generation? Essentially never in production**
- Voyager-style continuous self-generation only works with deterministic automated verification (games, sandboxes)
- SkillsBench: self-generated skills average -1.3pp vs NO skills. Curated skills: +16.2pp. Uncurated self-evolution = "skill debt"
- Production pattern = offline discovery -> validated versioned frozen tools -> online serving
- Closest match to Aqua: Amazon fulfillment-center alarm triage (arXiv 2607.08010). Tool-making pipeline compiles repeated steps into validated versioned tools before deployment. Runtime agent calls frozen tools, falls back to raw reasoning when no tool fits, and fallback events are logged as the feedback signal for the next offline tool-making round. p50 latency -42%, error rate -53%, revert = config change
- Verdict: the open-loop design is the industry norm, not a compromise. Online agent orchestrates + logs gaps (SQL feedback table), offline loop turns gaps into tools, review gate, redeploy

**Q2: How is the write-permission conflict handled? Scoped bot identity, not "no write"**
- Converged model: agent gets its own GitHub App bot identity, short-lived repo-scoped tokens, write ONLY to its own branches (GitHub Copilot agent: only `copilot/*` branches), branch protection on main with no bypass, agent opens PRs but can NEVER approve or merge, CI + human (not the requester) signs off
- Key insight: this makes the handoff trustworthy, not the agent. Platform enforces the boundary, not the prompt
- Human review stays mandatory: AI-coauthored PRs carry ~1.7x more issues, security issues 1.5-2x more common

**Aqua roadmap consequence**
- V1 (now): frozen tools + MCP MVP. Gaps go to a feedback table, agent never touches git. Discovery stays local (full permissions, human in loop)
- V2 (when feedback volume justifies): agent authors draft PRs under a scoped bot identity from the backlog, humans review. Ask platform team about a bot identity only when hand-processing the backlog gets annoying
- Framing for Mrigesh: online agent has orchestration autonomy but not authorship autonomy. Tool use online, tool birth offline behind review

Sources: [Amazon tool-making pipeline](https://arxiv.org/html/2607.08010v1), [SoK: Agentic Skills](https://arxiv.org/pdf/2602.20867), [Voyager](https://voyager.minedojo.org/), [agent GitHub identity + branch protection](https://savas.me/2026/04/27/my-coding-agent-needed-its-own-github-identity/), [Copilot coding agent security model](https://learn.microsoft.com/en-us/training/modules/github-copilot-code-agent/2-security-risks-limitations-copilot-code-agent), [Meta GitHub agent cookbook](https://dev.meta.ai/docs/getting-started/cookbook/github-agent)

## Conversation 6: Deep-read of the Amazon tool-making paper (arXiv 2607.08010)

Correction to Figure 1 reading: data collector -> tool maker -> reflector -> testing -> deploy is the OFFLINE pipeline. There is no online toolmaking in the paper. Online = agent runtime + a monitoring loop that sends flagged tools back through the offline pipeline (shadow deploy -> manual review -> promote). Confirms Conversation 5 from the primary source: tools are never born online.

**Domain**: alarm triage in Amazon fulfillment centers, not QA. SOP decision tree (44 decision + 19 action nodes), agents check metrics, find root cause, act. Structurally identical to label QA: repeated per-item procedural checks against production data ending in a verdict. Their SOP node = our failure mode.

**Offline pipeline mechanics (worth stealing)**
1. Data-collector sub-agent runs baseline codegen on ~3 sampled cases against live MCP, captures execution traces (real schemas, not imagined)
2. Tool-maker LLM synthesizes candidate from SOP text + tree position + traces
3. Test vs full labeled set (100-200 cases per node). Pass@1 = correct on every case
4. Reflector diagnoses failures, up to 3 repair rounds, best candidate wins
5. Versioned deploy. Runtime falls back to raw codegen only on tool exception
= Lily's 7-attempt loop formalized: eval set = labeled cases, iteration log = reflector, cross-pass agreement = repair criterion

**Online codegen vs offline tools, measured**
- Latency -42% p50 (further -62% calling tools directly), tokens -58%, turns -45%
- Errors: 2.8 -> 1.8% (Qwen3 32B), 1.7 -> 0.8% (GLM-4.5-Air), up to 53% relative
- 5,000+ production alarms, zero rollbacks
- Online codegen's only pro: flexibility on unseen cases, kept as fallback
- Offline cons: needs labeled cases per check, feedback loop stays semi-automated ("cannot yet guarantee every failure caught without human review")

**Two Aqua-relevant findings**
- Spec quality is the bottleneck (paper's Section 4.3 title). Verbatim: "Two undeployed Opus runs confirm the cause: augmenting the training data raises pass@1 to 96.6%, and clarifying the ambiguous SOP raises it to 99.9%" (from 94.5%). Spec clarity beat data augmentation (99.9 vs 96.6, Table 2). Note: the paper compares spec vs data, NOT spec vs model upgrades. "Write each failure mode like an SOP node" is our inference by analogy (spec ambiguity compiles into tool bugs), not the paper's claim
- Shadow deployment as promotion gate: new tool versions run parallel to production, discrepancies reviewed before promotion. Copy for Aqua v2 detector updates

(discussion continues below)

