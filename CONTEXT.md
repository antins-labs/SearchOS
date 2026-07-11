# SearchOS

SearchOS 将开放域问题编译为 Coverage Map，并由 Orchestrator 调度 Agent 与 Access Skill，把带来源的事实写入 Evidence Graph。

## Language

**Access Skill**：针对特定来源或检索方法、向 Agent 返回结构化结果的可执行检索能力。
_Avoid_：插件、爬虫脚本

**Executor**：Access Skill 目录中实现 `execute(params, ctx)` 契约的 Python 文件。
_Avoid_：任意脚本、内嵌工具

**Skill Execution**：依据一份 Execution Policy，在隔离 worker 中完成的一次 Executor 调用。
_Avoid_：动态导入、受控环境

**Execution Policy**：一次 Skill Execution 被明确授予的网络、文件、资源与输出权限集合。
_Avoid_：沙箱配置、隐式权限

**Browser Automation**：仅 Bundled Skill 可按 Execution Policy 使用的 Playwright driver 能力；它不是通用子进程权限。
_Avoid_：shell 权限、任意命令权限

**Bundled Skill**：已经随仓库审入和发布、默认允许访问网络的 Access Skill。
_Avoid_：可信脚本

**Generated Skill**：由 Dynamic Builder 生成、仅允许访问生成任务目标主机的候选 Access Skill。
_Avoid_：自动可信 Skill

## Relationships

- 一个 **Access Skill** 恰好包含一个 **Executor**
- 每次 **Skill Execution** 恰好运行一个 **Executor**
- 每次 **Skill Execution** 恰好受一份 **Execution Policy** 约束
- **Bundled Skill** 与 **Generated Skill** 使用同一 Skill Execution 接口，但适用不同的 Execution Policy
- **Bundled Skill** 可使用受识别的 **Browser Automation**；**Generated Skill** 不可启动任何子进程
- **Generated Skill** 只有通过隔离 smoke test 后才能晋升为 **Bundled Skill** 候选

## Example dialogue

> **开发者：** “Dynamic Builder 已经生成 Executor，可以直接导入验证吗？”
> **领域专家：** “不能。它仍是 Generated Skill，必须使用目标主机受限的 Execution Policy 完成 Skill Execution；主进程永远不导入 Executor。”

## Flagged ambiguities

- “受控环境”过去既表示普通 `asyncio.wait_for`，也暗示安全隔离；现统一为 **Skill Execution**，且必须有显式 **Execution Policy**。
