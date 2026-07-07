<div align="center">

[中文](README.zh.md) | **English** | [日本語](README.ja.md) | [한국어](README.ko.md)

</div>

<p align="center">
  <img src="assets/hero.svg" alt="SearchOS — from single-fact lookups to full-domain research, unified as citation-grounded relational schema completion" width="100%">
</p>

<h3 align="center">A multi-agent collaboration system for open-domain information seeking</h3>

<p align="center">
  <a href="https://antins-labs.github.io/SearchOS/"><img src="https://img.shields.io/badge/🌐_Website-searchos-2563EB?style=for-the-badge" alt="Website"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/langchain-ai/langgraph"><img src="https://img.shields.io/badge/Built_with-LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph"></a>
  <a href="https://github.com/Textualize/textual"><img src="https://img.shields.io/badge/TUI-Textual-0B0B0B?style=for-the-badge&logo=gnometerminal&logoColor=white" alt="Textual TUI"></a>
  <a href="LEGAL.md"><img src="https://img.shields.io/badge/License-MIT-0E9B9B?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <i>Schedule search the way an operating system schedules processes: compile an open-domain question
  into a normalized coverage map, dispatch its empty cells to pipelined-parallel sub-agents,
  write every piece of evidence — with its source — into a shared evidence graph, and synthesize
  a citation-grounded answer from <b>search state</b> — state that lives in the system, not in conversation history.</i>
</p>

<p align="center">
  <img src="assets/main.png" alt="SearchOS system overview: multi-agent collaboration + middleware + SOCM + skill system" width="95%">
</p>

<p align="center">
  <a href="https://youtu.be/DZNXxMcxnMQ">
    <img src="assets/searchos-demo.gif" alt="SearchOS demo: launch a real query from the terminal TUI → agents fill the table in parallel → switch to the web frontend for the synthesized answer" width="95%">
  </a>
</p>

<p align="center">
  🎬 <b><a href="https://youtu.be/DZNXxMcxnMQ">Full demo video (YouTube)</a></b>
</p>

> **▶️ Quick run:**
>
> ```bash
> pip install -e . && python -m searchos "Top-5 universities per subject in the 2025 QS rankings, with application deadlines"
> ```
>
> The first run launches a **setup wizard**: pick a model provider (vendor coding plans / pay-as-you-go APIs / local deployment), paste an API key, and you're up.
> Or run `python -m searchos` for the full-screen TUI to watch task dispatch, tool streams, and the coverage map grow in real time.
> You can also run `./web/start.sh` to bring up the REST/WS API (`:8000`) + web frontend (`:3000`) and launch searches from the browser with a live agent wall and coverage map.

## 📣 News

- **2026-07-07** — Web UI support: `./web/start.sh` brings up the REST/WS API (`:8000`) + web frontend (`:3000`) in one line — launch searches from the browser, watch the live agent wall and the coverage map fill in cell by cell, and read the synthesized answer with per-cell citations. 🌐
- **2026-07-05** — Open-source multi-provider support: `SF_PROVIDER` connects to 21 presets in one line — vendor Coding Plans (Zhipu / Kimi / MiniMax / Alibaba / Volcengine, Anthropic protocol), pay-as-you-go APIs (DeepSeek / OpenAI / OpenRouter / SiliconFlow / Gemini / xAI…), and local deployment (Ollama / vLLM); first-run CLI setup wizard + pluggable search backends (Serper / Tavily). High-frequency roles like extraction automatically fall to each vendor's lightweight tier to cut cost. 🔌
- **2026-07-02** — Direct answers for follow-up questions: follow-ups reuse the previous round's coverage map and skip re-searching when the answer is already in the table; chunked extraction for oversized skill payloads. 🧠
- **2026-06-25** — Interactive TUI command shell: `/skill` collapsible multi-select catalog, live mid-run steering, tool stream on screen; skill library restructured into core / catalog / runtime layers; split-tunnel egress — domestic sites go direct, overseas via proxy, one run reaches sources on both sides. 🖥️

## ✨ Highlights

- 🗂️ **Search state as a system asset (SOCM)** — the task queue, evidence graph, and coverage map live in one persistent state shared by all agents; snapshot / restore / replay it, instead of losing facts in dozens of turns of conversation history.
- 🧩 **Coverage-map-driven, recall-first** — the question is modeled as normalized entity × attribute tables; dispatch always targets the empty cells until every schema cell has a sourced value.
- ⚡ **Pipelined-parallel sub-agents** — the search → open → find stages of multiple search agents overlap across agents, results are harvested asynchronously, and freed slots are reused immediately; total wall-clock approaches the slowest single chain rather than a serial sum.
- 🔗 **Every cell carries a citation** — the extraction middleware automatically writes (entity, attribute, value, source) into the evidence graph; answers anchor back to their sources cell by cell, fully traceable.
- 🛡️ **Sensor safety net, automatic loop breaking** — five kinds of loop / stall detection on every tool call; a reminder is injected first to correct course, and repeat offenders are re-dispatched from a different angle.
- 🧰 **Skill system + multi-provider out of the box** — access skills crack hard sites behind anti-bot walls / login gates, strategy skills bring methodology for rankings / multi-hop / disambiguation; `SF_PROVIDER` connects to any vendor's coding plan / API / local deployment in one line.

> 📊 Leads on all headline F1 metrics on **WideSearch / GISA**, including **Set · F1 +13.4 over the next-best baseline** on enumeration questions (see [Evaluation](#-evaluation)).

## 🎥 Gallery

<table align="center">
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/YhJdc7Qhr1U" title="SearchOS-demo1 · Watch on YouTube">
        <img src="assets/gallery/demo1.jpg" alt="SearchOS-demo1" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo1</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/Qve7GX7yahs" title="SearchOS-demo2 · Watch on YouTube">
        <img src="assets/gallery/demo2.jpg" alt="SearchOS-demo2" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo2</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/IA_-sO2avTA" title="SearchOS-demo3 · Watch on YouTube">
        <img src="assets/gallery/demo3.jpg" alt="SearchOS-demo3" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo3</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/HxCLoauXoYg" title="SearchOS-demo4 · Watch on YouTube">
        <img src="assets/gallery/demo4.jpg" alt="SearchOS-demo4" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo4</b></sub>
    </td>
  </tr>
  <tr>
    <td colspan="2" align="center">
      <a href="https://youtu.be/-QmjRr_3B1s" title="SearchOS-demo5 · Watch on YouTube">
        <img src="assets/gallery/demo5.jpg" alt="SearchOS-demo5" width="50%">
      </a>
      <br><sub>▶️ <b>SearchOS-demo5</b></sub>
    </td>
  </tr>
</table>

<p align="center"><sub>Click a cover to watch on YouTube (more demos coming)</sub></p>

<!-- To add a video: copy a <td>…</td> block above and swap the youtu.be link, assets/gallery thumbnail, and title -->

## 💡 Why SearchOS

Pointing a general-purpose agent or deep-search agent at long-horizon search tasks commonly produces these failure modes:

* **Opaque process** — intermediate search results drown in dozens of turns of conversation history; facts get lost after context compression; mid-run you can neither see progress nor resume or replay.
* **Easy to loop** — no memory of what has already been checked: the same query gets re-issued with different phrasing, and the same entity's attributes are searched again in different subtasks.
* **Blurred roles** — sub-agents must search, read, remember, and summarize all at once; on long tasks something always slips: extracted fields use inconsistent conventions, sources get dropped.
* **Can't get in, can't search well** — anti-bot walls, login gates, and deep directories keep hard sites unreachable; ranking, multi-hop, and disambiguation questions aren't solved by simply searching more.

SearchOS answers each of the four failures with a mechanism-level fix:

* **Search state does not live in conversation history (SOCM)** — the task queue, evidence graph, and coverage map sit in one persistent state shared by all agents (`search_state.json`), snapshottable / restorable / replayable at any time; on the sub-agent side, a three-layer context (SOCM snapshot → episodic summaries per search segment → recent working memory) replaces full history, and the stable prefix is prompt-cache friendly.
* **Entity-centric modeling + sensors that break loops** — internally a normalized multi-table schema of primary keys + attributes (with foreign keys), so each entity's facts are fetched once and dispatch always targets the coverage map's empty cells; LoopSensor runs five loop checks on every tool call (no progress, search-without-read, duplicate queries, hard loops, zero state delta), first injecting a corrective reminder, and marking the agent `looped` for the orchestrator to re-dispatch from a different angle if it persists.
* **Search and extraction are separated** — sub-agents only need to find the right pages; after every page open, the extraction middleware uses a judge model to extract (entity, attribute, value, source, confidence) into the evidence graph, with unit normalization, excerpts anchored back to the original text, and content hashes retained — consistent conventions, traceable sources.
* **Crack hard sites with skills, search hard questions with methodology** — the first skill system purpose-built for search agents: site-level access skills solve "can't open" (anti-bot / login walls), strategy skills solve "don't know how to search" (rankings / multi-hop / disambiguation), routed and injected per query (counts, routing, and ablations in [Skill system](#-skill-system) below).

## 🧩 Framework

```
User query
   │
   ▼
┌─────────────────────────── Orchestrator (sole decision maker) ───────────────────┐
│   Explore scouting → create_schema builds the coverage map → enqueue_tasks       │
│   dispatch → check_agents polling → assess/adjust → enough coverage or budget    │
│   exhausted → synthesize                                                         │
└──────┬──────────────────────────┬─────────────────────────────┬─────────────────┘
       ▼                          ▼                             ▼
  explore_agent              search_agent × N              writer_agent
 (query typing / hub pages / (searches the web per         (consumes SOCM, writes
  candidate entities /        subtask, never writes         cited sections)
  search plan)                state directly)
       │                          │                             │
       └────────────┬─────────────┴─────────────────────────────┘
                    ▼
      Three middleware layers: Context → Sensor → Extraction
     (prompt assembly / budget & loop monitoring / judge-based auto extraction)
                    │
                    ▼
┌──────────── SOCM · Search-Oriented Context Management (shared search state) ─────┐
│  Frontier Memory   task queue: priority + blocked_by DAG, three task types in    │
│                    one shared pool                                               │
│  Evidence Graph    findings / sources / confidence, support-conflict edges       │
│  Coverage Map      entity × attribute, multi-table + foreign keys, per-column    │
│                    types / formats / validation                                  │
│  Strategy Memory   strategy & failure memory · Writer Outline · Budget           │
└───────────────────────────────────────────────────────────────────────────────────┘
```

A session loops through six steps:

1. **Explore** — a scout goes first: classifies the query type, locates hub pages, produces candidate entities and a search plan; it does not extract attribute values.
2. **Schema** — the Orchestrator builds a normalized coverage map by entity type (multiple tables + relations); every entity Explore found is seated as a seed row.
3. **Dispatch** — gaps are split into self-contained natural-language subtasks and dispatched to search agents in parallel by priority and dependency.
4. **Extract** — after every page open, the Extraction middleware automatically extracts (entity, attribute, value, source, confidence) into the evidence graph and lights up the coverage map.
5. **Assess** — subtasks are polled and harvested: new entities join the table, bad sources are blacklisted, conflicts go to arbitration, empty cells get targeted follow-ups.
6. **Synthesize** — once the coverage self-check passes, the answer is joined out of SOCM in the user's requested format, citation by citation.

### What the output looks like

Every cell carries a back-anchored source number, with the sources listed at the end — this is what "citation-grounded relational schema completion" looks like in the final product (excerpt from a real run; the query, in Chinese, was *survey Hong Kong's popular insurance products in recent years*):

```markdown
### Major insurers in Hong Kong
| Company     | English name   | 2024 APE rank | 2023 premiums  |
|-------------|----------------|---------------|----------------|
| 友邦保险     | AIA [6]        | #1 [6]        | HK$87.1B [6]   |
| 保诚         | Prudential [6] | #2 [6]        | HK$65.3B [6]   |
| 汇丰保险     | HSBC Life [6]  | #3 [6]        | HK$55.5B [6]   |
| 宏利         | Manulife [6]   | #4 [6]        | HK$49.8B [6]   |

### Sources
[6] https://www.ia.org.hk/tc/infocenter/press_releases/20250425.html, https://inews.hket.com/…
```

The full artifact (a replayable directory with the trajectory, page cache, and SOCM state) lives under `searchos_workspace/<timestamp>/`.

## 🚀 Installation

Requires Python ≥ 3.11:

```bash
pip install -e .            # base dependencies (incl. OpenAI/Anthropic dual-protocol clients; coding plans work out of the box)
pip install -e ".[eval]"    # evaluation: pandas / numpy / python-dotenv
pip install -e ".[all]"     # all optional backends: tavily / playwright / crawl4ai / langsmith
```

## ⚙️ Configuration

**The first run launches a setup wizard automatically**: when no usable model configuration is detected, `python -m searchos` walks you through picking a provider and entering an API key on the command line, then writes `.env` (re-run anytime with `python -m searchos --setup`).

You can also configure manually — copy [`.env.example`](.env.example) to `.env`, pick one `SF_PROVIDER` preset, and add the matching API key (bindings for all 12 model roles are generated automatically):

```bash
# Vendor Coding Plan (Anthropic-protocol subscription endpoints, great value)
SF_PROVIDER=zhipu-coding      # or kimi-coding / minimax-coding / qwen-coding / volcengine-coding
ZHIPU_API_KEY=xxx

# Or pay-as-you-go API (OpenAI protocol)
SF_PROVIDER=deepseek          # or moonshot / dashscope / openai / openrouter / siliconflow / gemini ...
DEEPSEEK_API_KEY=xxx

# Or local deployment
SF_PROVIDER=ollama            # or vllm
SF_MODEL=qwen3:32b

SF_JINA_API_KEY=...           # optional: Jina fetching (without it you use the unauthenticated quota, prone to 429)
```

All presets (each vendor's endpoints, model IDs, how to get keys, and known quirks) are in [`docs/providers.md`](docs/providers.md). Without `SF_PROVIDER`, the built-in gateway defaults in [`searchos/config/settings.py`](searchos/config/settings.py) apply (`OPENAI_API_KEY` + `SF_EXTRACTION_API_KEY`).

All configuration is centralized in `settings.py`; `SF_`-prefixed environment variables override it, with `__` separating nested fields (partial overrides **deep-merge** with defaults, changing only the fields you set). Models are bound by **role** (12 roles → model profiles), which makes ablations and cost reduction easy:

| Common settings | Description |
| --- | --- |
| `SF_MODEL` / `SF_FAST_MODEL` | Override the preset's main / lightweight-tier model |
| `SF_API_BASE` | Override the endpoint (e.g. switch to the international domain) |
| `SF_SEARCH_PROVIDER` | Search backend: `serper` \| `tavily` \| `ragflow` (inferred from available keys if unset) |
| `SF_BROWSER_BACKEND` | Fetch backend: `jina` \| `aiohttp` \| `crawl4ai` \| `search_engine` |
| `SF_ROLES__JUDGE=main` | Rebind a single role's model profile (advanced / ablation) |
| `SF_PROFILES__MAIN__TEMPERATURE=0.3` | Field-level override on one profile (advanced / ablation) |
| `SF_MAX_PARALLEL_AGENTS` | Sub-agent concurrency cap (default 8) |
| `SF_ENABLE_EXPLORE` / `SF_ENABLE_SKILLS` | Ablation switches: disable scouting / disable skills |
| `SF_SKIP_SYNTHESIS` | Evaluation mode: skip synthesis and export the table straight from the coverage map |

## 🧭 Quick start

| Command | What it does |
| --- | --- |
| `python -m searchos "<query>"` | Single query; results land in `searchos_workspace/<timestamp>/output/report.md` |
| `python -m searchos` | Full-screen Textual TUI: live panels, mid-run steering, multi-turn follow-ups, `/skill` skill management |
| `python -m eval.run --benchmark widesearch --range 1-50` | Run evaluations (see the next section) |

### Interactive TUI

`python -m searchos` opens the full-screen interface: a live dashboard on top (task dispatch, sub-agent status, coverage map growth) and the tool stream below. One input box routes by timing:

| When | What typing natural language does |
| --- | --- |
| Idle | Starts a new search run |
| **Mid-run** | **Live steering** — your text is injected into the running Orchestrator immediately, without interrupting sub-agents; use it to add constraints ("2024 data only"), correct course, or point at good sources |
| After a run | **Multi-turn follow-up** — reuses the previous round's coverage map and evidence: if the answer is already in the table it is answered directly (no new search); otherwise the existing table is extended incrementally, never rebuilt from scratch |

Slash commands work at any time (including mid-run):

| Command | Alias / shortcut | What it does |
| --- | --- | --- |
| `/new` | `/clear` · `Ctrl-N` | New topic: clears conversation history and the coverage map; the next question starts from a fresh workspace |
| `/effort [low\|medium\|high\|max]` | — | Effort tier: adjusts iteration cap, concurrency, per-agent search budget, wall-clock limit, and skill-routing top-k in one go; with no argument it opens an interactive picker; mid-run changes take effect next round |
| `/skill` | — | Skill management: no argument opens a grouped multi-select dialog; subcommands `list`, `only <names…>` (whitelist, fuzzy prefix match), `on` / `off <names…>`, `all` (reset to router control) for fine-grained control |
| `/verbose` | `/detail` · `Ctrl-T` | Toggle compact / detailed tool stream |
| `/stop` | `/cancel` · `Esc` | Interrupt the current run (Esc exits the program when idle) |
| `/help` | `/?` | Command help |
| `/quit` | `/exit` · `Ctrl-D` | Exit SearchOS |

The four `/effort` budget tiers at a glance (these modify global settings and take effect immediately for the current session; parallel sub-agents stay fixed at 8 across tiers):

| Tier | Orchestrator iterations | Searches per agent | Wall-clock cap | Routing top-k |
| --- | :---: | :---: | :---: | :---: |
| `low` | 25 | 10 | 10 min | 20 |
| `medium` (default) | 50 | 20 | 30 min | 40 |
| `high` | 100 | 35 | 60 min | 60 |
| `max` | 150 | 50 | 120 min | 80 |

Design doc: [docs/tui-textual-redesign.md](docs/tui-textual-redesign.md).

## 🧰 Skill system

Three categories of skills, all under [`searchos/skills/library/`](searchos/skills/library/):

| Category | Count | Description |
| --- | --- | --- |
| **access** | 248 | Site-level data access, named by domain (e.g. `en_wikipedia_org`); auto-routed on URL match, or invoked proactively by sub-agents as typed tools |
| **strategy** | 40+ | Reasoning methodology: `ranking_top_n`, `entity_disambiguation`, `multi_hop_bridge`…, optionally with anti-pattern checklists |
| **orchestrator** | a few | Orchestration-level methodology, injected wholesale as a playbook |

At runtime an LLM router pre-filters the access catalog to a query-relevant top-k (fail-open); each dispatched sub-agent carries at most 3 skills; pages that match no access skill fall back to the generic extraction middleware.

```bash
SEARCHOS_SKILL_ONLY=en_wikipedia_org,ranking_top_n   # whitelist
SEARCHOS_SKILL_LAYERS_DISABLED=access                # disable by layer
SEARCHOS_SKILLS_DISABLED=1                           # disable all
```

After a session, high-frequency domains can optionally be mined and baked into new access skills automatically (`SF_ENABLE_ACCESS_SKILL_GENERATION`, off by default).

## 📊 Evaluation

On **WideSearch** (wide-table retrieval) and **GISA** (open-domain information seeking), compared against 5 representative baselines (ReAct / Plan-and-Solve / A-MapReduce / Web2BigTable / Table-as-Search), **max@3** (best of three runs per case, ×100) headline scores:

| Benchmark | Metric | Best baseline | **SearchOS** |
| --- | --- | :---: | :---: |
| WideSearch | Item · F1 | 76.0 | **80.1** |
| WideSearch | Row · F1 | 54.5 | **55.6** |
| GISA | Table · F1 | 74.8 | **76.9** |
| GISA | Set · F1 | 63.1 | **76.5** |
| GISA | List · F1 | 67.1 | **68.1** |

SearchOS leads on all headline F1 metrics across both benchmarks, with gains driven primarily by **recall** — coverage-map-driven dispatch keeps filling empty cells until every schema cell has a sourced value; on enumerating complete sets, **Set · F1 beats the next-best baseline by +13.4**. Full breakdowns (Precision / Recall / EM, per question type) are in the paper.

## 🗂️ Project layout

```
searchos/
├── agents/        Orchestrator (prompt / catalog / scheduler / lifecycle) and the three sub-agent definitions
├── harness/       SearchSession main loop, three middleware layers, synthesis, trajectory & conversation logs
├── socm/          Shared search state: Frontier / Evidence Graph / Coverage Map / Strategy
├── tools/         Tools grouped by role: schema, tasks, writer, simple_browser …
├── skills/        Skill system: core contracts / catalog registry & routing / runtime execution / evolution / skill library
├── tui/           Textual full-screen interface (live dashboard, /skill management, follow-ups & steering)
├── config/        settings.py (pydantic-settings, SF_ prefix overrides) + model role bindings
└── cli.py         python -m searchos entry point

eval/              Evaluation framework: run.py entry, runner, benchmarks, scorers, reformat
datasets/          WideSearch / GISA / xbench / browsecomp / frames / webwalker
baselines/         Baselines for comparison (gpt-oss-simple-browser, etc.)
eval_results/      Evaluation output (one directory per case, with a fully replayable session)
searchos_workspace/ Session workspaces for interactive runs (timestamped directories)
```

## 🙏 Acknowledgements

SearchOS is built on [LangGraph](https://github.com/langchain-ai/langgraph) / [LangChain](https://github.com/langchain-ai/langchain) / [deepagents](https://github.com/langchain-ai/deepagents); the TUI is powered by [Textual](https://github.com/Textualize/textual). Evaluation data and official scorers come from the authors of [WideSearch](https://github.com/ByteDance-Seed/WideSearch), [GISA](https://github.com/RUC-NLPIR/GISA), xbench, and other benchmarks, who retain all rights (see the LICENSE files under `datasets/` and [LEGAL.md](LEGAL.md)).

## 📚 Citation

The paper (*SearchOS-v1*) is in preparation and its citation entry will replace this one upon release. Until then, if this project helps your research, please cite the repository:

```bibtex
@misc{searchos2026,
  title        = {SearchOS-v1: Towards Robust Open-Domain Information-Seeking Agents Collaboration},
  author       = {Zhang, Yuyao and Gao, Junjie and Wu, Zhengxian and Zhang, Jin and Ma, Shihan and Yao, Yao and Qi, Weiran and Xu, Xingzhong and Yang, Kai and Wen, Ji-Rong and Dou, Zhicheng},
  year         = {2026},
  howpublished = {\url{https://github.com/antins-labs/SearchOS}}
}
```

## 📄 License

MIT — see also [LEGAL.md](LEGAL.md).
