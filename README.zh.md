<div align="center">

**中文** | [English](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

</div>

<p align="center">
  <img src="assets/hero.svg" alt="SearchOS — 从单点事实到全域调研，统一为带引用的关系型 schema 补全" width="100%">
</p>

<h3 align="center">面向开放域信息检索的多智能体协作系统</h3>

<p align="center">
  <a href="https://antins-labs.github.io/SearchOS/"><img src="https://img.shields.io/badge/🌐_Website-searchos-2563EB?style=for-the-badge" alt="Website"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/langchain-ai/langgraph"><img src="https://img.shields.io/badge/Built_with-LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph"></a>
  <a href="https://github.com/Textualize/textual"><img src="https://img.shields.io/badge/TUI-Textual-0B0B0B?style=for-the-badge&logo=gnometerminal&logoColor=white" alt="Textual TUI"></a>
  <a href="LEGAL.md"><img src="https://img.shields.io/badge/License-MIT-0E9B9B?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <i>像操作系统调度进程一样调度搜索：把开放域问题编译成规范化的覆盖表，
  把空格子调度给流水线并行的子智能体，把每条证据连同出处写进共享的证据图，
  最后从<b>搜索状态</b>合成带引用的答案 —— 状态在系统里，不在对话历史里。</i>
</p>

<p align="center">
  <img src="assets/main.png" alt="SearchOS 系统总览：多智能体协作 + 中间件 + SOCM + 技能系统" width="95%">
</p>

<p align="center">
  <a href="https://youtu.be/DZNXxMcxnMQ">
    <img src="assets/searchos-demo.gif" alt="SearchOS Demo：终端 TUI 发起真实查询 → 多智能体并行填表 → 切换到 Web 前端合成答案" width="95%">
  </a>
</p>

<p align="center">
  🎬 <b><a href="https://youtu.be/DZNXxMcxnMQ">完整 Demo 视频（YouTube）</a></b>
</p>

> **▶️ 快速运行：**
>
> ```bash
> pip install -e . && python -m searchos "2025 年 QS 学科排名各学科前五的大学及其申请截止日期"
> ```
>
> 首次运行自动进入**配置向导**：选模型厂商（各家 coding plan / 按量 API / 本地部署）、填 API key 即可跑通。
> 或直接 `python -m searchos` 进入全屏 TUI，实时看任务分派、工具流与覆盖表增长。
> 也可以 `./web/start.sh` 一键拉起 REST/WS API（`:8000`）+ Web 前端（`:3000`），在浏览器里发起搜索、实时看智能体墙与覆盖表。

## 📣 News

- **2026-07-07** — Web UI 支持：`./web/start.sh` 一键拉起 REST/WS API（`:8000`）+ Web 前端（`:3000`），在浏览器里发起搜索，实时看智能体墙与覆盖表逐格填充，合成答案逐格带引用。🌐
- **2026-07-05** — 开源多厂商适配：`SF_PROVIDER` 一键接入 21 个预设——各家 Coding Plan（智谱/Kimi/MiniMax/阿里/火山，Anthropic 协议）、按量 API（DeepSeek/OpenAI/OpenRouter/硅基流动/Gemini/xAI…）与本地部署（Ollama/vLLM）；首跑命令行配置向导 + 可插拔搜索后端（Serper/Tavily）。抽取等高频角色自动落到各厂商轻量档降本。🔌
- **2026-07-02** — 多轮追问直答：追问沿用上一轮覆盖表，能直接回答的不再重复检索；超长 skill 载荷分段抽取上线。🧠
- **2026-06-25** — 交互式 TUI 指令外壳：`/skill` 目录折叠多选、运行中实时插话（steering）、工具流上屏，技能库按 core / catalog / runtime 三层重构；split-tunnel 出口——国内站点直连、境外走代理，一次运行通中外数据源。🖥️

## ✨ 核心亮点

- 🗂️ **搜索状态即系统资产（SOCM）** — 任务队列、证据图、覆盖表沉淀进一份所有智能体共享的持久化状态，可快照 / 恢复 / 复盘，不再淹没在几十轮对话历史里。
- 🧩 **覆盖表驱动、召回优先** — 把问题建模成 entity × attribute 的规范化多表，分派永远对着「空格子」，直到每个 schema 单元都有带出处的取值。
- ⚡ **流水线并行的子智能体** — 多个 search agent 的 search → open → find 阶段跨 agent 重叠、异步回收、空出的 slot 即时复用；总墙钟趋近最慢单链，而非串行相加。
- 🔗 **每个单元格都带引用** — 抽取中间件自动把 (entity, attribute, value, source) 写进证据图，答案逐格回锚来源、可溯可查。
- 🛡️ **传感器兜底、自动断循环** — 每次工具调用做五类循环 / 停滞检测，先注入提醒纠偏，屡教不改换角度重派。
- 🧰 **技能系统 + 多厂商开箱** — access 技能啃反爬 / 登录墙的难站点，strategy 方法论搜排名 / 多跳 / 消歧；`SF_PROVIDER` 一键接入各家 coding plan / API / 本地部署。

> 📊 在 **WideSearch / GISA** 上全部 headline F1 领先，其中枚举型 **Set · F1 领先次优基线 +13.4**（详见 [评测](#-评测)）。

## 🎥 Gallery

<table align="center">
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/YhJdc7Qhr1U" title="SearchOS-demo1 · 在 YouTube 观看">
        <img src="assets/gallery/demo1.jpg" alt="SearchOS-demo1" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo1</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/Qve7GX7yahs" title="SearchOS-demo2 · 在 YouTube 观看">
        <img src="assets/gallery/demo2.jpg" alt="SearchOS-demo2" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo2</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/IA_-sO2avTA" title="SearchOS-demo3 · 在 YouTube 观看">
        <img src="assets/gallery/demo3.jpg" alt="SearchOS-demo3" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo3</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/HxCLoauXoYg" title="SearchOS-demo4 · 在 YouTube 观看">
        <img src="assets/gallery/demo4.jpg" alt="SearchOS-demo4" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo4</b></sub>
    </td>
  </tr>
  <tr>
    <td colspan="2" align="center">
      <a href="https://youtu.be/-QmjRr_3B1s" title="SearchOS-demo5 · 在 YouTube 观看">
        <img src="assets/gallery/demo5.jpg" alt="SearchOS-demo5" width="50%">
      </a>
      <br><sub>▶️ <b>SearchOS-demo5</b></sub>
    </td>
  </tr>
</table>

<p align="center"><sub>点击封面在 YouTube 观看（更多演示陆续上传）</sub></p>

<!-- 新增视频：复制上面的 <td>…</td> 块，替换 youtu.be 链接、assets/gallery 缩略图与标题即可 -->

## 💡 Why SearchOS

把通用Agent/Deep Search Agent直接用在长程搜索任务上，常常出现以下失败模式：

* **过程不透明** — 中间搜索结果淹没在几十轮对话历史里，上下文压缩后事实就容易丢；跑到一半既看不见进度，也无法恢复和复盘。
* **容易“死循环”** — 不记得哪些已经查过：同一条 query 换个说法反复发，同一个实体的属性在不同子任务里重复搜。
* **分工含混** — 子智能体既要搜、又要读、又要记、还要汇总，任务一长就顾此失彼：抽出来的字段口径不一、来源丢失。
* **搜不进、也不会搜** — 反爬、登录墙、深层目录让难啃的站点打不开；排名、多跳、消歧这类复杂问题，光靠多搜几次解决不了。

SearchOS 对这四类失败逐条给出机制层面的解法：

* **搜索状态不走对话历史（SOCM）** — 任务队列、证据图、覆盖表放进一份所有智能体共享的持久化状态（`search_state.json`），随时快照、恢复、复盘；子智能体侧用三层上下文（SOCM 快照 → 搜索分段情景摘要 → 近期工作记忆）替代完整历史，稳定前缀对 prompt cache 友好。
* **按实体建模 + 传感器断循环** — 内部是主键 + 属性的规范化多表（带外键），同一实体的事实只查一次，分派永远对着覆盖表的空格子；LoopSensor 在每次工具调用上做五种循环检测（无进展、只搜不读、query 重复、硬循环、状态零增量），先注入提醒纠偏，屡教不改则标记 `looped` 交回编排层换角度重派。
* **搜和抽分开** — 子智能体只管找到对的页面；每次页面打开后由抽取中间件用 judge 模型自动抽取 (entity, attribute, value, source, confidence) 写入证据图，值做单位归一、摘录回锚原文并留存 hash，口径一致、来源可溯。
* **难啃的站点用技能啃，复杂的问题用方法论搜** — 首创搜索智能体专属技能系统：site-level 的 access 技能解决反爬 / 登录墙下"打不开"，strategy 检索方法论解决排名 / 多跳 / 消歧这类"不会搜"，按 query 路由注入（数量、路由与消融见下方 [技能系统](#-技能系统)）。

## 🧩 Framework

```
用户 query
   │
   ▼
┌─────────────────────────── Orchestrator（唯一决策者）────────────────────────────┐
│   Explore 侦察 → create_schema 建覆盖表 → enqueue_tasks 分派 → check_agents      │
│   轮询 → 评估/调整 → 覆盖足够或预算耗尽 → 合成                                   │
└──────┬──────────────────────────┬─────────────────────────────┬─────────────────┘
       ▼                          ▼                             ▼
  explore_agent              search_agent × N              writer_agent
 （query 分类 / hub 页 /    （按子任务搜索网页，          （消费 SOCM 写
   候选实体 / 搜索计划）      不直接写状态）                带引用的章节）
       │                          │                             │
       └────────────┬─────────────┴─────────────────────────────┘
                    ▼
      三层中间件：Context → Sensor → Extraction
     （prompt 组装 / 预算与循环监控 / judge 自动抽取证据）
                    │
                    ▼
┌──────────── SOCM · Search-Oriented Context Management（共享搜索状态）────────────┐
│  Frontier Memory   任务队列：priority + blocked_by DAG，三类任务共享一个池       │
│  Evidence Graph    证据图：finding / source / confidence，support-conflict 边     │
│  Coverage Map      覆盖表：entity × attribute，多表 + 外键，列级类型/格式/校验    │
│  Strategy Memory   策略与失败记忆   ·   Writer Outline   ·   Budget               │
└───────────────────────────────────────────────────────────────────────────────────┘
```

一次会话循环执行六步：

1. **Explore** — 侦察兵先行：判定 query 类型、定位 hub 页、产出候选实体与搜索计划，不抽取具体属性值。
2. **Schema** — Orchestrator 按实体类型建规范化覆盖表（多表 + 关系），Explore 发现的实体全部落座为种子行。
3. **Dispatch** — 把缺口拆成自包含的自然语言子任务，按优先级与依赖并行分派 search agents。
4. **Extract** — 每次页面打开后，Extraction 中间件自动抽取 (entity, attribute, value, source, confidence) 写入证据图并点亮覆盖表。
5. **Assess** — 轮询回收子任务：新实体入表、坏源记黑名单、冲突派仲裁、空格子定向补漏。
6. **Synthesize** — 覆盖率自审通过后，从 SOCM join 出用户要的格式，逐条带引用。

### 输出长什么样

每个单元格都带回锚的来源编号，文末列出对应出处 —— 这就是"带引用的关系型 schema 补全"落到产物上的样子（节选自一次真实运行，query：*梳理香港近几年的热门保险*）：

```markdown
### 香港主要保险公司
| 公司       | 英文名          | 2024 APE 排名 | 2023 保费规模   |
|-----------|----------------|--------------|---------------|
| 友邦保险   | AIA [6]        | 第 1 名 [6]   | 871 亿港元 [6] |
| 保诚       | Prudential [6] | 第 2 名 [6]   | 653 亿港元 [6] |
| 汇丰保险   | HSBC Life [6]  | 第 3 名 [6]   | 555 亿港元 [6] |
| 宏利       | Manulife [6]   | 第 4 名 [6]   | 498 亿港元 [6] |

### 信息来源
[6] https://www.ia.org.hk/tc/infocenter/press_releases/20250425.html, https://inews.hket.com/…
```

完整产物（带 trajectory、pages 缓存与 SOCM 状态的可复盘目录）见 `searchos_workspace/<时间戳>/`。

## 🚀 安装

要求 Python ≥ 3.11：

```bash
pip install -e .            # 基础依赖（含 OpenAI/Anthropic 双协议客户端，coding plan 开箱即用）
pip install -e ".[eval]"    # 评测：pandas / numpy / python-dotenv
pip install -e ".[all]"     # 全部可选后端：tavily / playwright / crawl4ai / langsmith
```

## ⚙️ 配置

**首次运行自动进入配置向导**：检测不到可用模型配置时，`python -m searchos` 会在命令行引导你选厂商、填 API key 并写入 `.env`（之后可随时 `python -m searchos --setup` 重新配置）。

也可以手动配置——复制 [`.env.example`](.env.example) 为 `.env`，选一个 `SF_PROVIDER` 预设 + 填对应 API key 即可跑通（12 个模型角色自动生成绑定）：

```bash
# 用厂商 Coding Plan（Anthropic 协议订阅端点，性价比高）
SF_PROVIDER=zhipu-coding      # 或 kimi-coding / minimax-coding / qwen-coding / volcengine-coding
ZHIPU_API_KEY=xxx

# 或按量 API（OpenAI 协议）
SF_PROVIDER=deepseek          # 或 moonshot / dashscope / openai / openrouter / siliconflow / gemini ...
DEEPSEEK_API_KEY=xxx

# 或本地部署
SF_PROVIDER=ollama            # 或 vllm
SF_MODEL=qwen3:32b

SF_JINA_API_KEY=...           # 可选：Jina 抓取（不填走未认证配额，易 429）
```

全部预设（含各厂商端点、模型 id、Key 获取方式与已知怪癖）见 [`docs/providers.md`](docs/providers.md)。不设 `SF_PROVIDER` 时沿用 [`searchos/config/settings.py`](searchos/config/settings.py) 内置的网关默认值（`OPENAI_API_KEY` + `SF_EXTRACTION_API_KEY`）。

所有配置集中在 `settings.py`，`SF_` 前缀环境变量覆盖，嵌套字段用 `__` 分隔（部分覆写与默认值**深合并**，只改你写的字段）。模型按**角色**绑定（12 个角色 → 模型 profile），便于消融与降本：

| 常用配置 | 说明 |
| --- | --- |
| `SF_MODEL` / `SF_FAST_MODEL` | 覆盖预设的主力 / 轻量档模型 |
| `SF_API_BASE` | 覆盖端点（如切国际站域名） |
| `SF_SEARCH_PROVIDER` | 搜索后端：`serper` \| `tavily` \| `ragflow`（不设则按已有 key 推断） |
| `SF_BROWSER_BACKEND` | 抓取后端：`jina` \| `aiohttp` \| `crawl4ai` \| `search_engine` |
| `SF_ROLES__JUDGE=main` | 单独改绑某个角色的模型 profile（高级 / 消融） |
| `SF_PROFILES__MAIN__TEMPERATURE=0.3` | 单 profile 字段级覆写（高级 / 消融） |
| `SF_MAX_PARALLEL_AGENTS` | 子智能体并发上限（默认 8） |
| `SF_ENABLE_EXPLORE` / `SF_ENABLE_SKILLS` | 消融开关：关侦察 / 关技能 |
| `SF_SKIP_SYNTHESIS` | 评测模式：跳过合成，直接从覆盖表导表 |

## 🧭 快速上手

| 命令 | 作用 |
| --- | --- |
| `python -m searchos "<query>"` | 单条查询，结果写入 `searchos_workspace/<时间戳>/output/report.md` |
| `python -m searchos` | 全屏 Textual TUI：实时面板、运行中插话、多轮追问、`/skill` 技能管理 |
| `python -m eval.run --benchmark widesearch --range 1-50` | 跑评测（见下节） |

### 交互式 TUI

`python -m searchos` 进入全屏界面：上方是实时 dashboard（任务分派、子智能体状态、覆盖表增长），下方是工具流。同一个输入框根据时机自动分流：

| 时机 | 输入自然语言的效果 |
| --- | --- |
| 空闲时 | 开始一次新的搜索运行 |
| **运行中** | **实时插话（steering）**——文字即刻注入运行中的 Orchestrator，子智能体不中断；用来补充约束（"只要 2024 年的数据"）、纠偏或提示好的数据源 |
| 运行结束后 | **多轮追问**——沿用上一轮覆盖表与证据：答案已在表中则直接作答（不再检索），否则在现有表上增量扩展，不从零重建 |

斜杠指令任何时候可用（运行中也生效）：

| 指令 | 别名 / 快捷键 | 作用 |
| --- | --- | --- |
| `/new` | `/clear` · `Ctrl-N` | 开新话题：清空对话历史与覆盖表，下一问从全新工作区开始 |
| `/effort [low\|medium\|high\|max]` | — | 投入档位：一次性调整迭代上限、并发数、每代理搜索预算、墙钟时限、技能路由 top-k；无参数弹出交互选择器，运行中修改下一轮生效 |
| `/skill` | — | 技能管理：无参数打开分组勾选弹窗；子命令 `list`（列出）、`only <名字…>`（白名单，前缀模糊匹配）、`on` / `off <名字…>`（启停）、`all`（重置交回路由）精细控制启用集 |
| `/verbose` | `/detail` · `Ctrl-T` | 切换精简 / 详细工具流 |
| `/stop` | `/cancel` · `Esc` | 中断当前运行（空闲时 Esc 退出程序） |
| `/help` | `/?` | 指令帮助 |
| `/quit` | `/exit` · `Ctrl-D` | 退出 SearchOS |

`/effort` 四档预算一览（修改的是全局 settings，对当前会话即时生效；并行子代理数固定为 8，不随档位变化）：

| 档位 | 编排迭代 | 每代理搜索 | 墙钟上限 | 路由 top-k |
| --- | :---: | :---: | :---: | :---: |
| `low` | 25 | 10 | 10 min | 20 |
| `medium`（默认） | 50 | 20 | 30 min | 40 |
| `high` | 100 | 35 | 60 min | 60 |
| `max` | 150 | 50 | 120 min | 80 |

设计文档见 [docs/tui-textual-redesign.md](docs/tui-textual-redesign.md)。

## 🧰 技能系统

三类技能，统一放在 [`searchos/skills/library/`](searchos/skills/library/)：

| 类别 | 数量 | 说明 |
| --- | --- | --- |
| **access** | 248 | 站点级数据获取，按域名命名（如 `en_wikipedia_org`）；URL 命中自动路由，或作为 typed 工具由子智能体主动调用 |
| **strategy** | 40+ | 推理方法论：`ranking_top_n`、`entity_disambiguation`、`multi_hop_bridge`…，可附反模式清单 |
| **orchestrator** | 若干 | 编排层方法论，整包注入 playbook |

运行时由 LLM router 对 access 目录做 query 相关的 top-k 预筛（fail-open），分派子智能体时最多携带 3 个技能；未命中任何 access 技能的页面回退到通用抽取中间件。

```bash
SEARCHOS_SKILL_ONLY=en_wikipedia_org,ranking_top_n   # 白名单
SEARCHOS_SKILL_LAYERS_DISABLED=access                # 按层关闭
SEARCHOS_SKILLS_DISABLED=1                           # 全部关闭
```

会话结束后可选自动挖掘高频域名、烘焙新的 access 技能（`SF_ENABLE_ACCESS_SKILL_GENERATION`，默认关）。

## 📊 评测

在 **WideSearch**（宽表检索）与 **GISA**（开放信息检索）上，与 5 个代表性基线（ReAct / Plan-and-Solve / A-MapReduce / Web2BigTable / Table-as-Search）对比，**max@3**（每题跑 3 次取最好，×100）headline 成绩：

| Benchmark | 指标 | 最强基线 | **SearchOS** |
| --- | --- | :---: | :---: |
| WideSearch | Item · F1 | 76.0 | **80.1** |
| WideSearch | Row · F1 | 54.5 | **55.6** |
| GISA | Table · F1 | 74.8 | **76.9** |
| GISA | Set · F1 | 63.1 | **76.5** |
| GISA | List · F1 | 67.1 | **68.1** |

SearchOS 在两个基准的全部 headline F1 上均领先，增益主要来自**召回** —— 覆盖表驱动的分派持续补齐空格子，直到每个 schema 单元都有带出处的取值；其中枚举完整集合的 **Set · F1 领先次优基线 +13.4**。完整分项对比（Precision / Recall / EM、逐题型）见论文。

## 🗂️ 项目结构

```
searchos/
├── agents/        Orchestrator（prompt / catalog / scheduler / lifecycle）与三类子智能体定义
├── harness/       SearchSession 主循环、三层中间件、合成、轨迹与对话日志
├── socm/          共享搜索状态：Frontier / Evidence Graph / Coverage Map / Strategy
├── tools/         按角色分组的工具：schema、tasks、writer、simple_browser …
├── skills/        技能系统：core 契约 / catalog 注册与路由 / runtime 执行 / evolution 进化 / library 技能库
├── tui/           Textual 全屏交互界面（实时 dashboard、/skill 管理、追问插话）
├── config/        settings.py（pydantic-settings，SF_ 前缀覆盖）+ 模型角色绑定
└── cli.py         python -m searchos 入口

eval/              评测框架：run.py 入口、runner、benchmarks、scorers、reformat
datasets/          WideSearch / GISA / xbench / browsecomp / frames / webwalker
baselines/         对照基线（gpt-oss-simple-browser 等）
eval_results/      评测输出（每题一目录，含完整可复盘 session）
searchos_workspace/ 交互运行的会话工作区（时间戳目录）
```

## 🙏 Acknowledgements

SearchOS 构建于 [LangGraph](https://github.com/langchain-ai/langgraph) / [LangChain](https://github.com/langchain-ai/langchain) / [deepagents](https://github.com/langchain-ai/deepagents) 之上，TUI 基于 [Textual](https://github.com/Textualize/textual)。评测数据与官方评分器来自 [WideSearch](https://github.com/ByteDance-Seed/WideSearch)、[GISA](https://github.com/RUC-NLPIR/GISA)、xbench 等 benchmark 的原作者，版权归其所有（见 `datasets/` 各子目录 LICENSE 与 [LEGAL.md](LEGAL.md)）。

## 📚 Citation

论文（*SearchOS-v1*）整理中，正式发布后将在此更新论文引用；在此之前如果本项目对你的研究有帮助，可以先引用本仓库：

```bibtex
@misc{searchos2026,
  title        = {SearchOS-v1: Towards Robust Open-Domain Information-Seeking Agents Collaboration},
  author       = {Zhang, Yuyao and Gao, Junjie and Wu, Zhengxian and Zhang, Jin and Ma, Shihan and Yao, Yao and Qi, Weiran and Xu, Xingzhong and Yang, Kai and Wen, Ji-Rong and Dou, Zhicheng},
  year         = {2026},
  howpublished = {\url{https://github.com/antins-labs/SearchOS}}
}
```

## 📄 License

MIT，另见 [LEGAL.md](LEGAL.md)。
