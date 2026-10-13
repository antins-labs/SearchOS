# 本地文档解析与 Recap

本模块把 Markdown、纯文本或 PDF 转换为正文缓存和三级导航索引，并向独立的 Local
Search Agent 提供本地 `catalog/open/find` 工具。意图学习不在本阶段。

## 安装

扫描 PDF 需要额外的解析和页面渲染依赖：

```bash
pip install -e '.[local-docs]'
```

模块不内置特定厂商、模型或 API key。CLI 默认调用远程模型，并读取 SearchOS 已有
的 provider 连接、模型卡与角色绑定；首次使用且尚未配置时进入统一配置向导。一个
provider 连接可以由多张模型卡复用同一个 API key：`local_recap` 绑定文本模型，
`local_vision` 绑定支持图片输入的模型。只有一张模型卡时可以让两个角色共用；需要
不同模型时在设置页或配置向导中分别绑定。

使用 `SF_PROVIDER` 快速配置时，`local_recap` 复用 `synthesis` 档，`local_vision`
复用 `fast` 档。模型不支持图片输入时，扫描 PDF 的视觉转录会失败并留下明确告警，
此时应为 `local_vision` 手动绑定 VLM。使用 `--local-only` 时只提取正文，不加载模型
配置，也不发送文档片段或页面图片。密钥、原文和 Base64 图片不写日志。

## 使用

```bash
python -m searchos.local docs/README.zh.md \
  --source-root docs \
  --output-root local-index/default
```

PDF 提供三种处理模式：

- `auto`：默认。优先使用文本层，扫描页、乱码页和复杂视觉页面升级到 VLM。
- `text_only`：只提取文本层，不调用 VLM。
- `vision_all`：所有页面都通过 VLM 转录。

例如：

```bash
python -m searchos.local report.pdf \
  --source-root . \
  --output-root local-index/default \
  --pdf-mode auto
```

输出包括：

```text
local-index/default/
  INDEX.md                # 所有 subindex 的路径、Recap 和字符数
  subindexes/<topic>.md   # 可读 topic 文件名、文件 Recap 和字符数
  documents/<doc_id>.md   # segment 范围、Recap 和字符数
  texts/<doc_id>.md       # 正文、位置、哈希和授权路径
```

模型只能引用程序提供的 segment ID。Markdown 位置转换为真实行号，PDF 位置转换为
物理页序号；视觉转录失败的页面不会计入覆盖范围。文档索引只保留章节 Recap 和对应
的页码或行号范围。PDF 的物理页只是模型输入切片，
模型依据正文标题和连续语义将跨页内容归并为章节；章节边界落在同一页时，相邻章节
可以共享该页。每一级的字符数都由程序统计，固定写成 `(12345 chars)`；模型不能返回
或修改计数。处理元数据保存在正文缓存中，
告警通过 CLI 和程序返回值报告，不写入文档索引。内容哈希和生成指纹均未变化时，
状态为 `ready` 的结果直接复用；`partial` 或 `failed` 会在下次处理时重试。

### 自下而上的目录增量更新

每份新文档完成文件级 Recap 后，目录只更新与该文档有关的分支，不重做全库解析：

1. 分类模型根据文件名、文件 Recap 以及已有 topic 的 ID、名称和 Recap，选择一至三个
   已有 topic，或提出新的临时 topic。
2. 服务端先更新文档与 topic 的成员关系；空分类会建立“未分类”临时归属，避免丢失
   已完成的文件 Recap。
3. 对新增归属和移出归属涉及的每个 topic，模型读取该 topic 当前全部文件 Recap，
   同时更新 topic 名称和一句话 Recap。当前名称仍准确时保持稳定；成员变化使名称过宽、
   过窄或不准确时才修改。
4. 服务端按更新后的名称写入 `subindexes/<topic>.md`，清理旧 topic 文件，再一次性重写
   `INDEX.md`。未受影响的 topic 及其 Recap 保持不变。

因此“未分类”只是模型无法给出初始归属时的过渡节点，仍会进入 topic 更新阶段。目录更新
不改变 `document_id`、源版本、解析 generation 或 `local://` 引用；topic 文件名可以随
语义名称变化。

### WebUI 图关系编辑与文档导航

知识库图支持直接维护现有分类关系。拖动文档到 topic 会把文档改归到该 topic；拖到
总索引会移除其全部 topic 关系。选中文档或 topic 后，分类边上的删除控件可以只移除
一条关系。手工关系编辑只修改本地 Markdown 目录，不调用模型，也不改变文档 ID、
原件版本或已有引用。topic 的语义名称和 Recap 仍由后续后台索引按成员自下而上更新。

单个文档节点可打开目录与 segment 视图。目录项来自文件级 Recap；Recap 尚未生成时，
使用解析 segment 生成临时目录。目录项保留到原始 segment 的映射，点击后定位并滚动到
第一个对应 segment。正文按需加载，每次最多返回 20,000 字符，用户可继续加载后续内容，
避免大文件一次性进入前端。

第三级导航使用 `local://<document_id>/sN?v=<版本前缀>` 短引用。完整 typed locator
与完整 SHA-256 保存在 `sources/`，不复制进模型可见的每条链接；读取时仍执行完整
版本、产物和位置映射校验。旧版内嵌 locator 的长引用保持只读兼容。

使用 `--no-catalog` 可以只生成文件索引，不更新 `INDEX.md` 和 subindex。

## Local Search Agent 工具

Local 工具默认关闭。由于工具结果会进入 Local Search Agent 的模型上下文，必须同时显式
启用工具和内容访问：

```bash
export SF_ENABLE_LOCAL_TOOLS=true
export SF_LOCAL_ALLOW_MODEL_ACCESS=true
export SF_LOCAL_INDEX_ROOT=./local-index/default
```

三个工具使用显式路径或 `ref_id`；只有资料库根目录配置按 Agent 隔离，不依赖隐式的
“当前页面”或数字链接：

- `local_catalog(path="", query="")`：读取所有层级的索引文件；无参数时打开
  `INDEX.md`，用 `path` 打开返回的 `catalog_path`，用 `query` 搜索索引。
- `local_open(ref_id, loc=0, max_chars=6000)`：只读取 `local://` 引用对应的原文。
  `loc` 是章节内 0-based 字符偏移，`max_chars` 限定为 1–20,000。
- `local_find(ref_id, pattern)`：在指定原文章节内查找，返回匹配的字符 `loc`。

典型调用顺序：

```text
local_catalog()
local_catalog(path="subindexes/<topic>.md")
local_catalog(path="documents/<document_id>.md")
local_find(ref_id="local://...#P1-3", pattern="keyword")
local_open(ref_id="local://...#P1-3", loc=1200, max_chars=6000)
```

工具拒绝索引根目录外的路径。打开正文前重新计算原文件哈希；不一致时返回
`STALE_INDEX`。只有带 `[LOCAL_SOURCE]` 标记的原文 `local_open/local_find` 结果进入
Evidence Intake，目录和 Recap 只用于导航。

Local Search Agent 与 Web Search Agent 完全隔离：前者只装载
`local_catalog/local_open/local_find`，后者只装载浏览器与 Access Skill 工具。纯 Web
任务不会携带本地工具定义或本地导航提示；混合任务由 Orchestrator 拆成两个 Agent
分别采集，结果统一进入 SOCM。

## Local 问答的执行流程

WebUI 的 Local 模式直接运行 Local Search Agent。Agent 自主选择
`local_catalog/local_find/local_open`，经过多轮工具调用后，在同一个 Agent 图中
生成最终答案。只有实际读取的原文窗口可支持回答中的引用。

Local 请求显式区分两种来源范围。`documents` 将读取权限锁定到用户选中的文档；
`library` 表示未预选文档，Agent 先使用 `local_catalog(query=...)` 按问题检索当前
知识库目录，再打开相关原文。库级问答不会依次预读全部文档，也不会越出当前
`library_id`；运行开始时仍固定库内可问答文档的版本快照。

为减少中小文档问答的模型往返，`documents` 范围先检查所选文件的全部主要解析正文是否适合一次
放入上下文。满足条件时，先批量执行原生 `local_open`，再把这些真实工具结果交给
同一个 Agent；通常第一轮模型调用即可回答，图表核对或进一步查找仍可使用工具。
该判断只依赖所选正文规模和模型上下文容量，不匹配问题关键词。

预读容量不超过 72,000 估算输入 tokens 和模型窗口的 75%，并为系统提示、来源元数据
及后续操作留余量；未知窗口沿用共用上下文管理的 100,000 默认值。所有原文窗口必须
完整容纳，且预读后至少保留一次工具调用额度。超过容量、窗口数量过多或来源位置重叠
时，直接使用按需阅读流程，不截取文件前部冒充全文。这里的容量只决定是否预读，
不会终止 Agent 的后续阅读。

预读保持原生工具的版本校验、位置映射、阅读记录和工具预算计数。长章节通过多个
原文窗口读全；部分读取失败时明确交给 Agent 继续处理，不标记为全文已读。默认回答
采用紧凑解读，用户要求详细分析或完整清单时仍充分展开。

Local QA 只设置工具调用预算，默认合计 48 次；并行工具调用共用计数，超出额度的
调用不执行。预算耗尽后，下一次模型请求关闭阅读工具，仅保留最终答案输出工具，
由当前 Agent 使用已有上下文回答，并说明未覆盖的范围。模型可以提前完成回答。

上下文管理复用其他 Agent 使用的 `ControlMiddleware`，本地直接问答选择其中的
`DynamicTrimMiddleware`：按模型窗口比例裁剪较早的消息，保留初始任务与有效的
近期工具调用、结果配对，不因上下文变长而终止阅读。该路径不依赖 schema 或
Evidence Graph；完整阅读记录保留在执行状态和持久化轨迹中。裁剪后仍允许再次
调用工具读取相同原文，引用继续绑定所选文档的版本和位置。

2026-09-13 已删除 Local QA 独立的单轮与累计输入 token 上限、模型调用次数上限、
总阅读字符限制及整轮超时，也删除额外的 `finalize` 调用与预留预算。输入估算和
模型调用次数仅作为运行统计。原生 `local_open` 每次读取的窗口限制保持不变。

工具预算耗尽后生成的回答在前端标记为“已基于已读内容回答 · 阅读受限”；模型
生成失败进入失败状态，不把固定提示作为成功答案。回归覆盖超过旧模型轮次、累计
输入与总阅读量限制后继续读取、共用上下文裁剪、重复阅读、并行工具预算和最终引用。

性能回放：2026-09-13 的论文解读任务实际耗时 66.3 秒，调用模型 12 次。论文含附录
共 38 页、137,803 字符。使用同一文件和本地模拟模型回放，完整预读后的模型调用
减少为 1 次，累计输入估算从 256,826 降为 64,022；本地准备与读取约 1.6 秒，引用
可正常定位原文。此耗时不包含真实模型生成，不作为端到端延迟承诺。

### 流式答案与原文引用

Local QA 通过 `local_answer(answer=...)` 提交最终 Markdown，运行时订阅模型的
增量消息，只发布该输出工具的答案字段。工具参数生成过程中即推送正文，工具返回
后直接结束 Agent 图，不再额外调用模型。规划文字、阅读工具参数和原文工具结果
不进入答案流；不支持流式输出或仍返回普通文本的模型保留整条回答兼容路径。

每个原文阅读窗口向模型提供 `[资料N]` 编号。服务端按实际阅读顺序绑定到规范的
本地引用，跨 chunk 的编号和链接在完整后才发布，其余正文即时发送。实时答案与
保存的最终答案共用引用绑定规则，前端显示文件名与位置，并打开相应原文。

模型漏写行内引用时，正文后提供明确的“已读原文入口”；这只是阅读导航，不代表
系统为具体结论自动补充了证据。历史答案也根据已有阅读记录显示该入口。前端不再
删除 `References`、`Sources` 等章节，避免已生成的引用被显示层过滤。
