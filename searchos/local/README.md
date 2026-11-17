# 本地文档索引与读取

Local Index 的核心对象是解析后的文档、章节摘要、主题目录和来源引用。建索引把原文件转换成可导航、可定位的正文；读取根据目录和引用返回指定来源的窗口。

## 核心链路

建索引由 `indexing.py` 中的 `DocumentRecapPipeline.process()` 编排：

```text
原文件 → parsers/ 解析正文 → recap/ 生成章节与文档摘要
       → storage/ 发布正文、来源记录和文档导航
       → catalog/ 更新主题归属与主题摘要
```

流水线在阶段开始前检查原文和配置指纹，复用已保存的结果。Web 上传先执行本地解析，使正文可读；后台任务再执行摘要和主题归类。阶段执行和缓存复用的判断集中在 `indexing.py`。

Agent 通过 `reader/` 读取：

```text
local_catalog → 查询目录，取得 local:// 引用
local_open   → 解析引用、校验来源版本与产物，返回正文窗口或原件预览
local_find   → 在同一来源中查找文本，返回后续读取的位置
```

`refs.py` 共用引用编解码和位置规范化；`reader/session.py` 绑定每个 Agent 的资料库与选中文档快照。摘要状态、解析覆盖范围和原件预览能力由各自的数据字段表达。

## 按职责找代码

```text
local/
├── indexing.py          # 建索引编排与阶段缓存
├── models.py            # 文档、片段、位置、摘要与处理选项
├── refs.py              # local:// 引用、链接正则与位置规范化
├── errors.py            # 文档处理错误
├── messages.py          # 状态、错误和处理说明
├── recap/
│   ├── prompts.py       # 章节/文档摘要提示词（local-recap-v11）
│   └── service.py       # 分批、缓存与覆盖校验
├── catalog/
│   ├── prompts.py       # 主题归类与主题摘要提示词（local-catalog-v16）
│   └── service.py       # 主题归属、目录存储与刷新
├── utils/
│   ├── llm.py           # JSON 模型调用、message_text、token 估算
│   ├── text.py          # one_line 等文本规范化
│   └── visuals.py       # 原件 PDF/图片预览渲染
├── parsers/
│   ├── base.py, registry.py, ooxml.py  # 解析框架与 OOXML 共用检查
│   ├── formats/         # 各输入类型解析器（pdf/docx/…）
│   └── vision/          # 视觉渲染、转录与提示词（local-vision-v4）
├── storage/
│   ├── documents.py     # 解析正文、产物版本和文档导航
│   ├── sources.py       # 资料库身份与来源记录
│   └── files.py         # 原子写入、文件哈希和发布锁
├── reader/
│   ├── prompts.py       # 三个阅读工具说明与导航文案
│   ├── tools.py         # local_catalog / local_open / local_find
│   ├── session.py       # Agent 的资料库与文档范围
│   ├── catalog.py       # 目录读取、链接转换与查询
│   ├── sources.py       # 来源校验与正文窗口
│   └── office_preview.py # Office 原件的 PDF 预览
├── library/
│   ├── service.py       # 资料库清单、文档查询、大纲与引用解析
│   ├── ingest.py        # 原件保存、去重、上传解析与后台 enrich
│   ├── topics.py        # 人工主题编辑与知识图谱视图
│   └── qa.py            # LocalAnswer、引用流绑定与 answer_query
├── migrate_index.py     # 离线迁移旧索引
├── __init__.py          # 公共建索引入口
└── __main__.py          # 命令行入口
```

| 修改内容 | 主要位置 |
|---|---|
| 阶段顺序、缓存命中、是否执行摘要或归类 | `indexing.py` |
| 格式提取、原文位置 | `parsers/formats/` |
| 视觉渲染与转录提示词 | `parsers/vision/` |
| 摘要分批、片段覆盖与模型输出校验 | `recap/service.py` |
| 摘要提示词 | `recap/prompts.py` |
| 主题成员、人工归属、主题摘要刷新 | `catalog/service.py` |
| 主题提示词 | `catalog/prompts.py` |
| JSON 调用、token 估算、原文预览、one_line | `utils/` |
| 解析产物格式、generation、当前来源记录与文档导航 | `storage/documents.py` |
| 文档身份与原文版本记录 | `storage/sources.py` |
| 引用格式、短引用展开与位置合并 | `refs.py` |
| 目录查询结果和导航链接 | `reader/catalog.py` |
| 授权范围、来源校验与正文窗口输入 | `reader/session.py`、`reader/sources.py` |
| 工具参数和输出格式 | `reader/tools.py`、`reader/prompts.py` |
| 上传、资料库管理与应用问答 | `library/` |
| 用户可见的错误与处理说明 | `messages.py` |
| Web 后台索引、网络导入与主题刷新任务 | `web/api/local/` |

分类模型根据文件名和摘要选择主题，程序校验归属并更新目录。主题摘要模型仅返回摘要；主题名称由分类或人工编辑维护。片段覆盖、位置连续性和来源版本由程序校验。

前端的静态文案和带参数整句集中在 `web/frontend/src/lib/localCopy.ts`，状态展示与格式化集中在同目录的 `localPresentation.ts`。组件负责交互和布局。模型输出校验失败时返回简短说明，完整异常保存在日志中。

Local Search Agent 的通用阅读规则沿用 `searchos/agents/local_search/agent.md`，问答模式的任务与运行提示集中在 `searchos/agents/local_search/qa.py`。

## 入口与依赖

```python
from searchos.local import DocumentRecapPipeline, PipelineOptions
from searchos.local.library import LocalLibraryService
from searchos.local.reader import local_catalog, local_find, local_open
```

格式解析、摘要和存储共用 `models.py` 与 `refs.py`。存储直接使用这些共用定义；读取调用存储并执行范围校验；`indexing.py` 组合解析、摘要、存储和主题目录；`library/` 连接 Web 资料库功能。`reader/session.py` 集中保存唯一的阅读 ContextVar。跨模块的模型调用与预览辅助放在 `utils/`，提示词留在各所有者的 `prompts.py`。

内部调用直接导入职责所属文件，测试替换依赖时也定位实际实现。旧源码路径已移除。

CLI：`python -m searchos.local`。旧索引迁移：`python -m searchos.local.migrate_index`。

索引存储格式和 `local://` 编码保持兼容。提示词版本随输出约定更新，缓存指纹会触发对应阶段重新生成。
