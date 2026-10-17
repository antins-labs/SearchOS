# Web 后端目录

`main.py` 组装应用与生命周期，`deps.py` 保存配置路径和共享会话入口，`state_stream.py` 负责状态增量。领域实现按用途归入子目录。

| 目录 | 职责 |
|---|---|
| `routes/` | HTTP 请求处理、校验结果转换与路由注册 |
| `research/` | 研究请求与响应契约；供路由和 Assistant 调度共同使用 |
| `settings/` | Web 设置写入和设置视图；配置模型与运行时应用仍由 `searchos.config` 管理 |
| `skills/` | 技能目录、包浏览、创建作业和草稿 |
| `local/` | 本地索引、网络导入和主题摘要后台作业 |
| `assistant/` | 设备访问、计划调度、通知与持久化 |

新增功能先归入负责该领域的目录。路由使用明确的限定导入，例如 `api.skills.creation`；`api.routes.skills` 专门负责 HTTP 入口。搜索数据契约从 `api.research.contracts` 导入，避免仅为读取类型而加载整份路由。

仓库相对路径以 `api.deps._REPO_ROOT` 为基准，不依赖实现文件的目录层数。设置存储与作业实例应通过所属模块访问，测试替换同一个模块对象，避免额外创建运行时单例。

当前研究启动和部分历史快照逻辑仍在 `routes/search.py`、`routes/history.py`；Assistant 运行层保留相应调用。后续迁移需要同时明确会话生命周期，不能只搬动函数。审查依据和验证结果见 [架构审查](../../docs/architecture-review-20261016.zh.md)。
