# Search Agent 通用 Exec

Search Agent 沿用现有架构和工具装配入口。Browser 与 read_visual 保留原定义和参数。模型通过 list_skills 发现技能、load_skill 读取并固定版本，在通用 exec 内使用 SearchAnything 编排技能调用。

SearchOS 后端管理连接与线路，Search 根据工具失败回执调整检索计划。SearchAnything CLI 仅提供 run 子命令；独立连接诊断由管理页与技能创建角色使用。

```text
exec(argv=None, code=None, inputs=None, stdin="", timeout_s=60)
```

code 接收 Python 代码，argv 接收命令与参数列表，二选一。每次调用启动独立进程，同一任务复用工作目录。inputs 接收已返回的产物 ref 或已读取页面的 URL；SEARCHOS_INPUTS_FILE 提供只读文件映射。通用执行默认 60 秒、最高 300 秒；路径预算到期后等待当前工具轮结束，再要求 Agent 总结。

返回值包含执行状态、stdout/stderr 预览和产物引用。文本结果提供 page_url，可沿用 open(id_or_url=...)、open(loc=...) 和 find(pattern=...) 阅读。失败和取消保存已生成文件，相同调用 ID 复用执行回执。普通代码产物标记为 execution_result，原始来源仍通过页面或技能结果提供。

调用技能的父 Exec 自动返回 child_results：items 保存子调用的参数、状态、输出字符数和读取 URL；shown、total、truncated 表示本次列出的调用数与总数。child_results.page_url 指向完整索引，沿用 open/find 阅读。即使编排代码只打印空的筛选结果，Agent 仍可检查原始技能输出，或通过 inputs 交给下一次 Exec 重新处理。索引与中断日志不参与证据抽取，成功技能结果继续使用原有页面及来源身份。

load_skill 返回 command_prefix（例如 ["searchanything", "run", "sample", "--"]）。单次调用将前缀与文档中的命令参数合并后传给 exec(argv=...)；多步任务通过 exec(code=...) 编排：

```python
import json
import subprocess
from pathlib import Path

result = subprocess.run(
    ["searchanything", "run", skill_name, "--", "python", script, *arguments],
    capture_output=True, text=True, check=True,
)
Path("candidates.json").write_text(result.stdout)
```

SearchAnything 使用已加载的技能快照。一次 Exec 启动首个技能时使用一个技能预算单位，同一编排中的后续技能共用这一单位。每个子执行单独保存参数、状态和结果。抽取器逐份核对来源，停滞检测按整次编排的抽取结果判断进展。

父程序与技能拥有各自的任务工作目录。同一任务中的技能子调用共享技能工作目录并串行执行。同站点浏览器占用时由技能执行层等待，等待计入执行时限。

子调用的成功业务 JSON stdout 进入现有 Evidence Extraction；随后阅读同一保存页面时去重。普通代码输出通过保存页面供 Agent 按需阅读。

验证位于 tests/test_search_agent_exec.py，覆盖单一 Exec 注册、加载后按返回说明执行、代码执行、文件复用、只读输入、执行预算、取消与技能编排。固定小红书响应回放覆盖两次父 Exec 和十二次子调用。
