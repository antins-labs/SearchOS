---
name: codebase_search
description: 代码库搜索——精确文本 / 语义 / 符号 / AST 结构搜索的分流
trigger: 任务在已下载的本地代码库或可访问代码索引内进行检索
layer: strategy
success_rate: 0.0
status: seed
alpha: 1
beta: 1
---
## 目标
仓库内检索有四种互不可替代的搜索方式：精确文本、语义、符号、AST 结构。本 skill 给出每种方式的边界与组合方法。

## 适用场景
- "找出所有调用 foo 的地方"
- "这块功能在哪里实现"
- "所有未捕获异常的 try 块"
- "某个概念的代码位置（关键词不确定）"

## 规则（共 11 条）
1. **精确字符串用 ripgrep**：错误信息、字面量、长字符串首选 `rg "<exact>"`。
2. **正则用 `rg -P`**：跨语言注释/字符串 PCRE 更准；写正则前先尝试纯字符串。
3. **符号用 LSP / `symbol:` 索引**：函数 / 类 / 变量定义跳转用符号索引而不是 grep。
4. **语义搜索用于关键词不确定**：当目标概念有多种命名时切语义搜索（embeddings / Cursor / sourcegraph）。
5. **AST 搜索用于结构匹配**：找模式相同但字面不同的代码（如 `for x in Y: if x.z`），用 ast-grep 等结构工具。
6. **先粗后细**：先 `rg` 粗扫文件级命中，再进入文件用 LSP / 符号搜索精确定位。
7. **限定文件类型 / 路径**：`rg --type py path/`、排除 `node_modules / vendor / build` 等噪声目录。
8. **跨引用用 LSP "find references"**：比 grep 函数名更可靠，避免同名误命中。
9. **测试代码与生产代码分开搜**：`tests/` / `*_test.py` 单独命中可定位调用样例。
10. **历史上下文用 `git log -S` / `git log -G`**：找"这段代码什么时候加的、为什么加"。
11. **组合策略**：rg 命中 → 进文件 → LSP 找引用 → 必要时 AST 复核 → `git log` 补历史。

## 执行流程
1. 分类问题：is_pattern_structural / is_concept_fuzzy / is_exact_string / is_symbol。
2. 选对应工具。
3. 先粗扫 + 限路径 → 精确定位。
4. 历史上下文用 git 工具补全。

## 关联 skill
- `github_search` — 跨仓库阶段
- `general_query_construction` — 关键词不确定时回到 query 构造
