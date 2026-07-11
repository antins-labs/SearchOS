<div align="center">

**中文** | [English](../README.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

</div>

<p align="center">
  <img src="../assets/hero.svg" alt="SearchOS — 从单点事实到全域调研，统一为带引用的关系型 schema 补全" width="100%">
</p>

<h3 align="center">面向开放域信息检索的多智能体协作系统</h3>

<p align="center">
  <a href="https://antins-labs.github.io/SearchOS/"><img src="https://img.shields.io/badge/🌐_Website-searchos-2563EB?style=for-the-badge" alt="Website"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.11+"></a>
  <a href="https://github.com/langchain-ai/langgraph"><img src="https://img.shields.io/badge/Built_with-LangGraph-1C3C3C?style=for-the-badge&logo=langchain&logoColor=white" alt="LangGraph"></a>
  <a href="https://github.com/Textualize/textual"><img src="https://img.shields.io/badge/TUI-Textual-0B0B0B?style=for-the-badge&logo=gnometerminal&logoColor=white" alt="Textual TUI"></a>
  <a href="../LEGAL.md"><img src="https://img.shields.io/badge/License-MIT-0E9B9B?style=for-the-badge" alt="License: MIT"></a>
</p>

<p align="center">
  <i>像操作系统调度进程一样调度搜索：把开放域问题编译成规范化的覆盖表，
  把空格子调度给流水线并行的子智能体，把每条证据连同出处写进共享的证据图，
  最后从<b>搜索状态</b>合成带引用的答案 —— 状态在系统里，不在对话历史里。</i>
</p>

<p align="center">
  <img src="../assets/main.png" alt="SearchOS 系统总览：多智能体协作 + 中间件 + SOCM + 技能系统" width="95%">
</p>

<p align="center">
  <a href="https://youtu.be/DZNXxMcxnMQ">
    <img src="../assets/searchos-demo.gif" alt="SearchOS Demo：终端 TUI 发起真实查询 → 多智能体并行填表 → 切换到 Web 前端合成答案" width="95%">
  </a>
</p>

<p align="center">
  🎬 <b><a href="https://youtu.be/DZNXxMcxnMQ">完整 Demo 视频（YouTube）</a></b>
</p>

> **▶️ 快速运行：**
>
> ```bash
> ./install.sh && source .venv/bin/activate && searchos "2025 年 QS 学科排名各学科前五的大学及其申请截止日期"
> ```
>
> 首次运行自动进入**配置向导**：选模型厂商（各家 coding plan / 按量 API / 本地部署）、填 API key 即可跑通。
> 或直接运行 `searchos` 进入全屏 TUI，实时看任务分派、工具流与覆盖表增长。
> 也可以 `./web/start.sh` 一键拉起 REST/WS API（`:8000`）+ Web 前端（`:3000`），在浏览器里发起搜索、实时看智能体墙与覆盖表。

## 📣 News

- **2026-07-11** — **更快开始，更广搜索，全程可见。** 全新一键安装器让 SearchOS 快速就绪；并行 Explore waves 分批探索开放网络，实时进度与按实体分组的证据让每一次发现都清晰可追。Skill 现已在强化隔离的工作进程中运行。 ⚡
- **2026-07-10** — **研究，从画出结构开始。** 描绘问题，SearchOS 把它变成可探索、可完善、可导出的引用级研究成果。 🧩
- **2026-07-09** — **离开多久，都能原样回来。** 对话、进度、证据与实时动态完整保留，打开即可继续。 ⏪
- **2026-07-08** — **所有设置，一个地方。** 模型、服务商、搜索、技能与预算，汇聚在一个简单而完整的控制中心。 ⚙️
- **2026-07-07** — **SearchOS，正式开源。** 多智能体搜索、结构化研究、TUI 与 Web UI，第一次完整走到所有人面前。 🚀

## ✨ 核心亮点

- 🗂️ **搜索状态即系统资产** — SOCM（Search-Oriented Context Management）把任务队列、证据图、覆盖表放进一份全体共享的持久化状态，可快照 / 恢复 / 复盘，不再淹没在对话历史里。
- 🧩 **覆盖表驱动、召回优先** — 问题建模成 entity × attribute 的规范化多表，分派永远对着空格子，直到每格都有带出处的取值。
- ⚡ **流水线并行的子智能体** — search → open → find 阶段跨 agent 重叠，总墙钟趋近最慢单链，而非串行相加。
- 🔗 **每格都带引用** — 抽取中间件自动把 (entity, attribute, value, source) 写进证据图，答案逐格可溯源。
- 🛡️ **传感器兜底** — 每次工具调用做五类循环 / 停滞检测，先提醒纠偏，无效则换角度重派。
- 🧰 **技能 + 多厂商开箱即用** — access 技能啃反爬 / 登录墙难站，strategy 方法论搜排名 / 多跳 / 消歧；`SF_PROVIDER` 一行接入任意厂商。

> 📊 在 **WideSearch / GISA** 上全部 headline F1 领先，其中枚举型 **Set · F1 领先次优基线 +13.4**（详见 [评测](#-评测)）。

## 🎥 Gallery

<table align="center">
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/dfzu9aeK0Cs" title="SearchOS-Web Demo · 在 YouTube 观看">
        <img src="../assets/gallery/web-demo.jpg" alt="SearchOS-Web Demo" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-Web Demo</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/bS07neJm6FA" title="SearchOS-Web Demo 2 · 在 YouTube 观看">
        <img src="https://img.youtube.com/vi/bS07neJm6FA/hqdefault.jpg" alt="SearchOS-Web Demo 2" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-Web Demo 2</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/YhJdc7Qhr1U" title="SearchOS-demo1 · 在 YouTube 观看">
        <img src="../assets/gallery/demo1.jpg" alt="SearchOS-demo1" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo1</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/Qve7GX7yahs" title="SearchOS-demo2 · 在 YouTube 观看">
        <img src="../assets/gallery/demo2.jpg" alt="SearchOS-demo2" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo2</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <a href="https://youtu.be/IA_-sO2avTA" title="SearchOS-demo3 · 在 YouTube 观看">
        <img src="../assets/gallery/demo3.jpg" alt="SearchOS-demo3" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo3</b></sub>
    </td>
    <td width="50%" align="center">
      <a href="https://youtu.be/HxCLoauXoYg" title="SearchOS-demo4 · 在 YouTube 观看">
        <img src="../assets/gallery/demo4.jpg" alt="SearchOS-demo4" width="100%">
      </a>
      <sub>▶️ <b>SearchOS-demo4</b></sub>
    </td>
  </tr>
  <tr>
    <td colspan="2" align="center">
      <a href="https://youtu.be/-QmjRr_3B1s" title="SearchOS-demo5 · 在 YouTube 观看">
        <img src="../assets/gallery/demo5.jpg" alt="SearchOS-demo5" width="50%">
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

* **搜索状态在系统里，不在对话历史里** — SOCM 把任务队列、证据图、覆盖表放进一份共享的持久化状态（`search_state.json`），随时快照 / 恢复 / 复盘；子智能体用三层上下文（SOCM 快照 → 情景摘要 → 近期工作记忆）替代完整历史，稳定前缀对 prompt cache 友好。
* **按实体建模 + 传感器断循环** — 主键 + 属性的规范化多表（带外键），同一事实只查一次，分派永远对着空格子；LoopSensor 每次工具调用做五种循环检测，先提醒纠偏，无效则标记 `looped` 换角度重派。
* **搜和抽分开** — 子智能体只管找对页面；每次页面打开后由 judge 模型抽取 (entity, attribute, value, source, confidence) 写入证据图，值做单位归一、摘录回锚原文——口径一致、来源可溯。
* **难站用技能啃，难题用方法论搜** — 首创搜索智能体专属技能系统：access 技能解决反爬 / 登录墙"打不开"，strategy 方法论解决排名 / 多跳 / 消歧"不会搜"，按 query 路由注入（详见 [技能系统](#-技能系统)）。

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
./install.sh                # 推荐：Python + Access Skill + Chromium + Web 前端
source .venv/bin/activate

pip install -e .            # 手动：仅基础运行依赖
pip install -e ".[access]"  # 手动：仓库内 Access Skill 依赖
pip install -e ".[eval]"    # 手动：评测依赖
pip install -e ".[all]"     # 手动：全部可选运行依赖
```

一键安装要求 Node.js ≥ 20.9；可用 `./install.sh --core` 跳过 Access Skill 和浏览器运行时，或用 `./install.sh --all --dev` 准备完整开发环境。详见[安装指南](installation.md)。

如果 `python -m searchos` 正常、但 `searchos` 的错误堆栈指向其他仓库，请重新执行 `source .venv/bin/activate && hash -r`；详见安装指南中的[同名命令排查](installation.md#searchos-命令指向其他仓库)。

## ⚙️ 配置

**首次运行自动进入配置向导**：检测不到可用模型配置时，`searchos` 会引导你选厂商、填 API key 并写入 `.env`（之后可随时用 `searchos --setup` 重新配置）。Web Settings 与 TUI 的 `/model`、`/search`、`/config` 共用同一份 `web_settings.json` overlay，因此 CLI、TUI 与 Web 的配置保持一致。

也可以手动配置——复制 [`.env.example`](../.env.example) 为 `.env`，选一个 `SF_PROVIDER` 预设 + 填对应 API key 即可跑通（11 个模型角色自动生成绑定）：

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

全部预设（含各厂商端点、模型 id、Key 获取方式与已知怪癖）见 [`docs/providers.md`](../docs/providers.md)。不设 `SF_PROVIDER` 时沿用 [`searchos/config/settings.py`](../searchos/config/settings.py) 内置的网关默认值（`OPENAI_API_KEY` + `SF_EXTRACTION_API_KEY`）。

所有配置集中在 `settings.py`，`SF_` 前缀环境变量覆盖，嵌套字段用 `__` 分隔（部分覆写与默认值**深合并**，只改你写的字段）。模型按**角色**绑定（11 个角色 → 模型 profile），便于混用厂商、限速、消融与降本：

| 常用配置 | 说明 |
| --- | --- |
| `SF_MODEL` / `SF_FAST_MODEL` | 覆盖预设的主力 / 轻量档模型 |
| `SF_API_BASE` | 覆盖端点（如切国际站域名） |
| `SF_SEARCH_PROVIDER` | 搜索后端：`serper` \| `tavily` \| `ragflow`（不设则按已有 key 推断） |
| `SF_BROWSER_BACKEND` | 抓取后端：`jina` \| `aiohttp` \| `crawl4ai` \| `search_engine` |
| `SF_ROLES__JUDGE=main` | 单独改绑某个角色的模型 profile（高级 / 消融） |
| `SF_PROFILES__MAIN__TEMPERATURE=0.3` | 单 profile 字段级覆写（高级 / 消融） |
| `SF_PROFILES__MAIN__RPM=60` / `...__TPM=100000` | 单 profile 滑动窗口请求/Token 限速；`0` 表示关闭 |
| `SF_MAX_PARALLEL_AGENTS` | 子智能体并发上限（默认 8） |
| `SF_ENABLE_EXPLORE_BATCH` / `SF_EXPLORE_MIN_WAVES` / `SF_EXPLORE_MAX_WAVES` | 并行 Explore 及自适应 wave 范围（默认 2–3） |
| `SF_ENABLE_EXPLORE` / `SF_ENABLE_SKILLS` | 消融开关：关闭 Explore / 关闭 Skill |
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
| `/resume [session-id]` | `/load` | 恢复历史会话及其对话、轨迹、覆盖表与证据；不带 id 时打开选择器 |
| `/effort [low\|medium\|high\|max]` | — | 投入档位：一次性调整迭代上限、并发数、每代理搜索预算、墙钟时限、技能路由 top-k；无参数弹出交互选择器，运行中修改下一轮生效 |
| `/skill` | — | 技能管理：无参数打开分组勾选弹窗；子命令 `list`（列出）、`only <名字…>`（白名单，前缀模糊匹配）、`on` / `off <名字…>`（启停）、`all`（重置交回路由）精细控制启用集 |
| `/model` | — | 打开共享模型设置：Provider 连接、模型卡、角色绑定与 profile 限速 |
| `/search [auto\|serper\|tavily\|ragflow]` | — | 查看或切换共享搜索后端 |
| `/config [key value]` | `/set` | 打开共享设置面板，或快速修改支持的运行默认值 |
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

设计文档见 [docs/tui-textual-redesign.md](../docs/tui-textual-redesign.md)。

## 🧰 技能系统

三类技能，统一放在 [`searchos/skills/library/`](../searchos/skills/library/)：

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

在 **WideSearch**（宽表检索）与 **GISA**（开放信息检索）上，与 2 个单智能体基线（ReAct / Plan-and-Solve）和 3 个多智能体系统（Table-as-Search / A-MapReduce / Web2BigTable）对比。所有成绩均为 **max@3**（每题跑 3 次取最好，×100），**加粗**为每行最优；*Item* 逐格独立计分，*Row* 要求整行全对。

| Benchmark | 指标 | ReAct | Plan-and-Solve | Table-as-Search | A-MapReduce | Web2BigTable | **SearchOS** |
| --- | --- | :---: | :---: | :---: | :---: | :---: | :---: |
| WideSearch | Item · Precision | 82.9 | 83.8 | 82.4 | 83.1 | 78.3 | **83.9** |
| | Item · Recall | 70.2 | 72.9 | 73.5 | 74.2 | 73.4 | **79.7** |
| | Item · F1 | 72.9 | 75.2 | 75.4 | 76.0 | 73.8 | **80.3** |
| | Row · Precision | 58.0 | 58.7 | 57.1 | 56.9 | 57.5 | **59.0** |
| | Row · Recall | 48.8 | 50.2 | 51.6 | 49.8 | 54.0 | **55.8** |
| | Row · F1 | 50.9 | 52.2 | 52.7 | 51.4 | 54.5 | **56.5** |
| GISA | Table · Item · F1 | 74.8 | 71.2 | 73.4 | 72.5 | 68.1 | **76.9** |
| | Table · Row · F1 | 58.1 | 50.7 | 54.1 | 52.1 | 45.3 | **59.7** |
| | Set · F1 | 61.6 | 63.1 | 60.9 | 62.5 | 56.7 | **76.5** |
| | List · F1 | 67.1 | 53.8 | 54.2 | 57.4 | 65.5 | **68.1** |
| | Item · EM | 0.0 | 16.7 | 16.7 | 33.3 | **50.0** | **50.0** |

SearchOS 在两个基准的全部 F1 上均领先，增益主要来自**召回** —— 覆盖表驱动的分派持续补齐空格子，直到每个 schema 单元都有带出处的取值；其中枚举完整集合的 **Set · F1 领先次优基线 +13.4**。

## 🗂️ 项目结构

```
searchos/
├── agents/        Orchestrator 与 Explore、Search、可选 Writer agent 定义
├── harness/       SearchSession、Context/Sensor/Evidence Intake、修复规划、合成与遥测
├── socm/          共享搜索状态：Frontier / Evidence Graph / Coverage Map / Strategy
├── tools/         按角色分组的工具：schema、tasks、writer、simple_browser …
├── skills/        契约/manifest、路由、隔离 runtime、creation/evolution 与技能库
├── tui/           Textual 界面：实时面板、恢复、设置、Skill、追问与 steering
├── config/        Provider、模型卡/角色、限速、effort、环境变量与共享设置 overlay
└── cli.py         `searchos` / `python -m searchos` 入口

web/api/           FastAPI REST/WS：运行、历史资产、快照/分支、修复、设置与 Skill jobs
web/frontend/      Next.js 研究工作台：composer、实时运行、证据、版本、用量与历史库

eval/              评测框架：run.py 入口、runner、benchmarks、scorers、reformat
datasets/          WideSearch / GISA / xbench / browsecomp / frames / webwalker
baselines/         对照基线（gpt-oss-simple-browser 等）
eval_results/      评测输出（每题一目录，含完整可复盘 session）
searchos_workspace/ 交互运行的会话工作区（时间戳目录）
```

## 🙏 Acknowledgements

SearchOS 由核心贡献者 **Yuyao Zhang** 与 **Junjie Gao**（蚂蚁集团）设计并构建，并由导师 **Ji-Rong Wen** 与 **Zhicheng Dou**（中国人民大学）指导。我们也感谢蚂蚁保的大力支持，并特别感谢本项目的发起者和领导者 **Kai Yang** 与 **Xingzhong Xu**。

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

MIT，另见 [LEGAL.md](../LEGAL.md)。
