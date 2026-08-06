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
