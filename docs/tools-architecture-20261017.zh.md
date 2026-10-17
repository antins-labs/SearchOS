# 工具目录重构

日期：2026-10-17。

## 问题与方案

`searchos/tools/` 原有 10 个 Python 文件。部分文件代表工具类别，部分保存共享上下文；`schema.py` 的 1500 行混合建表、行编辑、读取与证据投影，`tasks.py` 的 868 行混合任务队列、报告回收和证据操作。仅凭文件名难以判断应该在哪里修改。

按用户要求，每类工具形成一个目录（Module），目录内按职责组织实现。包入口集中声明该类工具的调用约定（Interface），实现直接依赖所属文件，不通过入口反向导入。共享上下文不是工具类别，保留在根目录，维持 ContextVar 的唯一实例。

```text
searchos/tools/
├── __init__.py
├── search_state.py          # 共享工作区、Agent、任务和来源上下文
├── schema/                 # 表格定义、行编辑、单元格读取与投影
│   ├── definitions.py
│   ├── entities.py
│   ├── evidence.py
│   └── assertions.py
├── tasks/                  # Frontier 队列、研究计划和任务报告
│   ├── queue.py
│   ├── reports.py
│   ├── evidence.py
│   └── plan.py
├── socm_read/               # Coverage、Evidence 与 Frontier 的只读视图
├── writer/                 # 提纲、章节与引用编辑
├── skills/                 # 技能发现、加载快照和执行
├── python/                 # 受限 Python 执行
└── simple_browser/         # 搜索、页面读取、视觉读取与后端
```

`schema`、`tasks`、`socm_read`、`writer` 和 `simple_browser` 保留原有领域入口。`research_plan` 归入 `tasks/plan.py`，技能目录与执行归入 `skills/`，`python_execution` 归入 `python/`；仓库内调用及本地测试同步更新，不新增旧文件转发层。

技能发现目前反向依赖执行模块：catalog 的加载工具调用 execution，而 execution 又读取 catalog 的权限与注册表。加载工具归入 execution，包入口负责组合工具，使依赖单向。Legacy typed-tool Adapter 仍有兼容用途，集中保留，不能因生产入口没有直接调用而删除。

浏览器的 `skill_pages.py` 与 `execution_pages.py` 共同负责技能结果转页面，合并为 `result_pages.py`。文件路径验证归入已有的 `searchos/skills/runtime/paths.py`，页面与执行共同使用，解除双向依赖。保留结果类别、来源地址、内容哈希、默认结果页和路径安全规则。

根目录 `tools/` 的辅助脚本与 `searchos/tools/` 用途不同，目前只有探针和评测查看器。此次不搬迁其命令入口。

## 行为约束

- 保持工具名称、说明、参数 schema、角色工具集和工具顺序。
- 建表后的 Explore 回放、证据投影前的来源核验、提交事务与冲突复核保持原顺序。
- 任务调度、追问唤醒、预算、取消与错误报告回收保持原语义。
- ContextVar 不复制；共享状态与调度器仍由现有运行时拥有。
- 本地测试目录继续忽略且保留；不混入工作区已有的其他修改。

## 实施结果

- 根目录 Python 文件由 10 个减至 2 个，七类工具均有目录入口。详细修改导航见 [工具目录](../searchos/tools/README.md)。
- `schema.py` 拆为 4 个职责文件；最大的定义文件为 620 行。`tasks.py` 拆为队列、报告和证据操作，研究计划归入同一目录；最大的队列文件为 480 行。
- `socm_read` 分为 Coverage、Evidence 和 Frontier 三种视图；Writer 的提纲操作保持在一个文件内，避免按工具逐个拆碎。
- 技能目录和执行去除双向依赖，Legacy Adapter 单独保留；两份结果页面合并为 186 行的 `result_pages.py`。删除一个仅转发清空单元格操作的函数，调用处直接使用 SOCM 实现。
- 迁移不依赖旧模块转发文件。原有 9 个已修改跟踪文件内容均与开始前一致；本地 `tests/` 继续忽略。

## 验证

- 迁移前后 34 个工具对象的名称、说明与参数 JSON schema 完全一致；Agent 装配、工具集合及顺序保持不变。
- 任务、SOCM 读取、Writer、Python 和研究计划的 36 个函数经 AST 对照，除导入路径外实现一致；schema 的 14 个保留函数仅调整共享实现引用及清空调用。
- 七个类别/页面入口在独立进程中导入，以及正序、逆序导入均通过。运行时 Context、工作区和 Agent ContextVar 保持对象身份一致。
- schema 相关回归：219 通过、1 跳过、1 项既有失败；该失败仍是旧用例未按现有契约提供来源与摘录。
- 技能和浏览器相关回归：158 通过、3 跳过；跳过项需要当前环境不支持的系统沙箱或本机端口。
- 迁移后五个测试仍在旧包入口替换私有依赖；修改其替换位置后，涉及的两个测试文件共 25 项通过。
- 完整回归执行时，上述五个测试尚未更新替换位置，结果为 1423 通过、19 失败、12 跳过；五项修正后已在 25 项复测中全部通过。其余 14 项失败与上一轮基线逐项一致，未发现新增功能回归。全量运行继续排除原有无法收集的 `test_preprocess_cache.py`；既有问题详见 [架构审查验证记录](architecture-review-20261016.zh.md#验证记录)。
- Ruff F 检查和 `git diff --check` 通过。本轮未重复执行依赖真实模型的根目录探针，也未运行与变更无关的前端测试。

完整回归命令：

```bash
SF_ASSISTANT_ROOT=/private/tmp/searchos-tools-final-assistant \
  .venv/bin/python -m pytest -c pyproject.toml --rootdir=. \
  --asyncio-mode=auto tests --ignore=tests/test_preprocess_cache.py -q
```
