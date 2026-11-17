# 本地文档索引与读取

Local Index 的核心对象是解析后的文档、章节摘要、主题目录和来源引用。建索引把原文件转换成可导航、可定位的正文；读取根据目录和引用返回指定来源的窗口。

## 核心链路

建索引由 `indexing.py` 中的 `DocumentRecapPipeline.process()` 编排：

```text
原文件 → parsers/ 解析正文 → recap/ 生成章节与文档摘要
       → storage/ 发布正文、来源记录和文档导航
       → catalog.py 更新主题归属与主题摘要
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
├── catalog.py           # 主题归属、主题摘要和目录文件
├── models.py            # 文档、片段、位置、摘要与处理选项
├── refs.py              # local:// 引用与位置规范化
├── parsers/             # 各格式解析；vision.py 提供视觉转录和渲染
├── recap/               # 摘要分批与章节覆盖校验
├── prompts/             # 分类、摘要、转录、阅读工具和问答提示词
├── storage/
│   ├── documents.py     # 解析正文、产物版本和文档导航
│   ├── sources.py       # 资料库身份与来源记录
│   └── files.py         # 原子写入、文件哈希和发布锁
├── reader/
│   ├── tools.py         # 三个 Agent 阅读工具
│   ├── session.py       # Agent 的资料库与文档范围
│   ├── catalog.py       # 目录读取、链接转换与查询
│   ├── sources.py       # 来源校验、正文选择与阅读元数据
│   ├── visuals.py       # PDF 页面与图片区域预览
│   └── office_preview.py # Office 原件的 PDF 预览
├── library.py           # Web 资料库管理、上传、问答与引用解析
├── migrate_index.py     # 离线迁移旧索引
├── errors.py            # 文档处理错误
├── messages.py          # 状态、错误和处理说明
├── __init__.py          # 公共建索引入口
└── __main__.py          # 命令行入口
```

| 修改内容 | 主要位置 |
|---|---|
| 阶段顺序、缓存命中、是否执行摘要或归类 | `indexing.py` |
| 格式提取、原文位置、视觉转录 | `parsers/` |
| 摘要分批、片段覆盖与模型输出校验 | `recap/service.py` |
| 主题成员、人工归属、主题摘要刷新 | `catalog.py` |
| 解析产物格式、generation、当前来源记录与文档导航 | `storage/documents.py` |
| 文档身份与原文版本记录 | `storage/sources.py` |
| 引用格式、短引用展开与位置合并 | `refs.py` |
| 目录查询结果和导航链接 | `reader/catalog.py` |
| 授权范围、来源校验与正文窗口输入 | `reader/session.py`、`reader/sources.py` |
| 工具参数和输出格式 | `reader/tools.py` |
| 上传、资料库管理与应用问答 | `library.py` |
| 模型任务、输出约定与提示词版本 | `prompts/` |
| 用户可见的错误与处理说明 | `messages.py` |
| Web 后台索引、网络导入与主题刷新任务 | `web/api/local/` |

分类模型根据文件名和摘要选择主题，程序校验归属并更新目录。主题摘要模型仅返回摘要；主题名称由分类或人工编辑维护。片段覆盖、位置连续性和来源版本由程序校验。

前端的静态文案和带参数整句集中在 `web/frontend/src/lib/localCopy.ts`，状态展示与格式化集中在同目录的 `localPresentation.ts`。组件负责交互和布局。模型输出校验失败时返回简短说明，完整异常保存在日志中。

Local Search Agent 的通用阅读规则沿用 `searchos/agents/local_search/agent.md`，问答模式的任务与运行提示集中在 `prompts/qa.py`。

## 入口与依赖

```python
from searchos.local import DocumentRecapPipeline, PipelineOptions
from searchos.local.library import LocalLibraryService
from searchos.local.reader import local_catalog, local_find, local_open
```

格式解析、摘要和存储共用 `models.py` 与 `refs.py`。存储直接使用这些共用定义；读取调用存储并执行范围校验；`indexing.py` 组合解析、摘要、存储和主题目录；`library.py` 连接 Web 资料库功能。`reader/session.py` 集中保存唯一的阅读 ContextVar。

内部调用直接导入职责所属文件，测试替换依赖时也定位实际实现。旧源码路径已移除。

CLI：`python -m searchos.local`。旧索引迁移：`python -m searchos.local.migrate_index`。

索引存储格式和 `local://` 编码保持兼容。提示词版本随输出约定更新，缓存指纹会触发对应阶段重新生成。
